// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"
#include <xcore/assert.h>

void sw_pll_sdm_init(   sw_pll_state_t * const sw_pll,
                    const sw_pll_15q16_t Kp,
                    const sw_pll_15q16_t Ki,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const uint32_t app_pll_ctl_reg_val,
                    const uint32_t app_pll_div_reg_val,
                    const uint32_t app_pll_frac_reg_val,
                    const unsigned ppm_range)
{
    // Get PLL started and running at nominal
    sw_pll_app_pll_init(get_local_tile_id(),
                    app_pll_ctl_reg_val,
                    app_pll_div_reg_val,
                    (uint16_t)(app_pll_frac_reg_val & 0xffff));

    // Setup sw_pll with supplied user paramaters
    sw_pll_reset(sw_pll, Kp, Ki, 65535); // TODO work out windup limit - this overflows at 65536
    sw_pll->pi_state.iir_y = 0;

    // Setup general controller state
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;

    sw_pll->loop_rate_count = loop_rate_count;
    sw_pll->loop_counter = 0;
    sw_pll->first_loop = 1;

    // Setup PFD state
    sw_pll_pfd_init(&(sw_pll->pfd_state), loop_rate_count, pll_ratio, ref_clk_expected_inc, ppm_range);
}


void init_sigma_delta(sw_pll_sdm_state_t *sdm_state){
    sdm_state->ds_x1 = 0;
    sdm_state->ds_x2 = 0;
    sdm_state->ds_x3 = 0;
}


__attribute__((always_inline))
int32_t sw_pll_sdm_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error)
{
    sw_pll->pi_state.error_accum += error; // Integral error.
    sw_pll->pi_state.error_accum = sw_pll->pi_state.error_accum > sw_pll->pi_state.i_windup_limit ? sw_pll->pi_state.i_windup_limit : sw_pll->pi_state.error_accum;
    sw_pll->pi_state.error_accum = sw_pll->pi_state.error_accum < -sw_pll->pi_state.i_windup_limit ? -sw_pll->pi_state.i_windup_limit : sw_pll->pi_state.error_accum;

    // Use long long maths to avoid overflow if ever we had a large error accum term
    int64_t error_p = ((int64_t)sw_pll->pi_state.Kp * (int64_t)error);
    int64_t error_i = ((int64_t)sw_pll->pi_state.Ki * (int64_t)sw_pll->pi_state.error_accum);

    // Convert back to 32b since we are handling LUTs of around a hundred entries
    int32_t total_error = (int32_t)((error_p + error_i) >> SW_PLL_NUM_FRAC_BITS);

    return total_error;
}

__attribute__((always_inline))
int32_t sw_pll_sdm_post_control_proc(sw_pll_state_t * const sw_pll, int32_t error)
{
    // Filter some noise into DCO to reduce jitter
    // First order IIR, make A=0.125
    // y = y + A(x-y)
    sw_pll->pi_state.iir_y += ((error - sw_pll->pi_state.iir_y)>>3);

    int32_t dco_ctl = SW_PLL_SDM_MID_POINT - error;

    return dco_ctl;
}


void sw_pll_send_ctrl_to_sdm_task(chanend_t c_sdm_control, int32_t dco_ctl){
    chan_out_word(c_sdm_control, dco_ctl);
}

sw_pll_lock_status_t sw_pll_sdm_do_control(sw_pll_state_t * const sw_pll, chanend_t c_sdm_control, const uint16_t mclk_pt, const uint16_t ref_clk_pt)
{
    if (++sw_pll->loop_counter == sw_pll->loop_rate_count)
    {
        sw_pll->loop_counter = 0;

        if (sw_pll->first_loop) // First loop around so ensure state is clear
        {
            sw_pll->pfd_state.mclk_pt_last = mclk_pt;  // load last mclk measurement with sensible data
            sw_pll->pi_state.error_accum = 0;
            sw_pll->pi_state.iir_y = 0;
            sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
            sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;

            sw_pll->first_loop = 0;

            // Do not set PLL frac as last setting probably the best. At power on we set to nominal (midway in settings)
        }
        else
        {
            sw_pll_calc_error_from_port_timers(&(sw_pll->pfd_state), &(sw_pll->first_loop), mclk_pt, ref_clk_pt);
            int32_t error = sw_pll_sdm_do_control_from_error(sw_pll, sw_pll->pfd_state.mclk_diff);
            int32_t dco_ctl = sw_pll_sdm_post_control_proc(sw_pll, error);

            sw_pll_send_ctrl_to_sdm_task(c_sdm_control, dco_ctl);

            // Save for next iteration to calc diff
            sw_pll->pfd_state.mclk_pt_last = mclk_pt;

        }
    }

    // printchar('+');

    return sw_pll->lock_status;
}
