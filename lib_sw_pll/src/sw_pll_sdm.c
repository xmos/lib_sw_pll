// Copyright 2022-2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#ifdef __XS3A__

#include "sw_pll.h"

void sw_pll_sdm_controller_init(sw_pll_state_t * const sw_pll,
                                const sw_pll_15q16_t Kp,
                                const sw_pll_15q16_t Ki,
                                const sw_pll_15q16_t Kii,
                                const size_t loop_rate_count,
                                const int32_t ctrl_mid_point)
{
    // Setup sw_pll with supplied user paramaters
    sw_pll_lut_reset(sw_pll, Kp, Ki, Kii, 0);
    // override windup limits
    sw_pll->pi_state.i_windup_limit = SW_PLL_SDM_UPPER_LIMIT - SW_PLL_SDM_LOWER_LIMIT;
    sw_pll->pi_state.ii_windup_limit = SW_PLL_SDM_UPPER_LIMIT - SW_PLL_SDM_LOWER_LIMIT;
    sw_pll->sdm_state.ctrl_mid_point = ctrl_mid_point;
    sw_pll->pi_state.iir_y = 0;
    sw_pll->sdm_state.current_ctrl_val = ctrl_mid_point;

    sw_pll_reset_pi_state(sw_pll);

    // Setup general controller state
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;

    sw_pll->loop_rate_count = loop_rate_count;
    sw_pll->loop_counter = 0;
    sw_pll->first_loop = 1;
}

void sw_pll_sdm_init(   sw_pll_state_t * const sw_pll,
                    const sw_pll_15q16_t Kp,
                    const sw_pll_15q16_t Ki,
                    const sw_pll_15q16_t Kii,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const uint32_t app_pll_ctl_reg_val,
                    const uint32_t app_pll_div_reg_val,
                    const uint32_t app_pll_frac_reg_val,
                    const int32_t ctrl_mid_point,
                    const unsigned ppm_range)
{
    // Get PLL started and running at nominal
    sw_pll_app_pll_init(get_local_tile_id(),
                    app_pll_ctl_reg_val,
                    app_pll_div_reg_val,
                    (uint16_t)(app_pll_frac_reg_val & 0xffff));

    // Setup SDM controller state
    sw_pll_sdm_controller_init( sw_pll,
                                Kp,
                                Ki,
                                Kii,
                                loop_rate_count,
                                ctrl_mid_point);

    // Setup PFD state
    sw_pll_pfd_init(&(sw_pll->pfd_state), loop_rate_count, pll_ratio, ref_clk_expected_inc, ppm_range);
}


void sw_pll_init_sigma_delta(sw_pll_sdm_state_t *sdm_state){
    sdm_state->ds_x1 = 0;
    sdm_state->ds_x2 = 0;
    sdm_state->ds_x3 = 0;
}


__attribute__((always_inline))
int32_t sw_pll_sdm_post_control_proc(sw_pll_state_t * const sw_pll, int32_t error)
{
    // Filter some noise into DCO to reduce jitter
    // First order IIR, make A=0.125
    // y = y + A(x-y)
    sw_pll->pi_state.iir_y += ((error - sw_pll->pi_state.iir_y)>>3);

    int32_t dco_ctl = sw_pll->sdm_state.ctrl_mid_point + sw_pll->pi_state.iir_y;

    if(dco_ctl > SW_PLL_SDM_UPPER_LIMIT){
        dco_ctl = SW_PLL_SDM_UPPER_LIMIT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_HIGH;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
    } else if (dco_ctl < SW_PLL_SDM_LOWER_LIMIT){
        dco_ctl = SW_PLL_SDM_LOWER_LIMIT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
    } else {
        if(sw_pll->lock_counter){
            sw_pll->lock_counter--;
        } else {
            sw_pll->lock_status = SW_PLL_LOCKED;
        }
    }

    return dco_ctl;
}



__attribute__((always_inline))
inline sw_pll_lock_status_t sw_pll_sdm_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error)
{
    int32_t ctrl_error = sw_pll_do_pi_ctrl(sw_pll, error);
    sw_pll->sdm_state.current_ctrl_val = sw_pll_sdm_post_control_proc(sw_pll, ctrl_error);

    return sw_pll->lock_status;
}


bool sw_pll_sdm_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_clk_pt)
{
    bool control_done = true;

    if (++sw_pll->loop_counter == sw_pll->loop_rate_count)
    {
        sw_pll->loop_counter = 0;

        if (sw_pll->first_loop) // First loop around so ensure state is clear
        {
            sw_pll->pfd_state.mclk_pt_last = mclk_pt;  // load last mclk measurement with sensible data
            sw_pll->pi_state.iir_y = 0;
            sw_pll_reset_pi_state(sw_pll);
            sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
            sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;

            sw_pll->first_loop = 0;
            // Do not set current_ctrl_val as last setting probably the best. At power on we set to nominal (midway in settings)

        }
        else
        {
            sw_pll_calc_error_from_port_timers(&(sw_pll->pfd_state), &(sw_pll->first_loop), mclk_pt, ref_clk_pt);
            sw_pll_sdm_do_control_from_error(sw_pll, -sw_pll->pfd_state.mclk_diff);
            
            // Save for next iteration to calc diff
            sw_pll->pfd_state.mclk_pt_last = mclk_pt;
        }
    } else {
        control_done = false;
    }

    return control_done;
}

#endif // __XS3A__
