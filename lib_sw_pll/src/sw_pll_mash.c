// Copyright 2022-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#if defined(__VX4B__)

#include <inttypes.h>

#include "sw_pll.h"


void sw_pll_mash_controller_init(sw_pll_state_t * const sw_pll,
                                const sw_pll_15q16_t Kp,
                                const sw_pll_15q16_t Ki,
                                const sw_pll_15q16_t Kii,
                                const size_t loop_rate_count,
                                const int32_t nominal_mash_val)
{
    // Setup sw_pll with supplied user paramaters
    sw_pll_lut_reset(sw_pll, Kp, Ki, Kii, 0);
    // override windup limits
    sw_pll->pi_state.i_windup_limit = SW_PLL_SDM_UPPER_LIMIT - SW_PLL_SDM_LOWER_LIMIT;
    sw_pll->pi_state.ii_windup_limit = SW_PLL_SDM_UPPER_LIMIT - SW_PLL_SDM_LOWER_LIMIT;
    sw_pll->mash_state.nominal_mash_val = (int32_t)nominal_mash_val;

    sw_pll_reset_pi_state(sw_pll);



    // Setup general controller state
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;

    sw_pll->loop_rate_count = loop_rate_count;
    sw_pll->loop_counter = 0;
    sw_pll->first_loop = 1;
}

sw_pll_result_t sw_pll_mash_init(   sw_pll_state_t * const sw_pll,
                        const sw_pll_15q16_t Kp,
                        const sw_pll_15q16_t Ki,
                        const sw_pll_15q16_t Kii,
                        const size_t loop_rate_count,
                        const size_t pll_ratio,
                        const uint32_t ref_clk_expected_inc,
                        const uint32_t app_pll_ctl_reg_val,
                        const uint32_t app_pll_div_reg_val,
                        const unsigned nominal_mash_val,
                        const unsigned ppm_range,
                        const sw_pll_tile_mask_t tile_mask)
{
    // Get PLL started and running at nominal
    sw_pll_result_t error = sw_pll_app_pll_mash_init(get_local_tile_id(),
                    app_pll_ctl_reg_val,
                    app_pll_div_reg_val,
                    (int32_t)nominal_mash_val,
                    tile_mask);


    if (error != SW_PLL_SUCCESS)
    {
        return error;
    }


    // // Setup sw_pll with supplied user paramaters
    // sw_pll_lut_reset(sw_pll, Kp, Ki, Kii, num_lut_entries);

    // Setup general controller state
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;

    sw_pll->loop_rate_count = loop_rate_count;
    sw_pll->loop_counter = 0;
    sw_pll->first_loop = 1;


    sw_pll_reset_pi_state(sw_pll);

        // Setup SDM controller state
    sw_pll_mash_controller_init(sw_pll,
                                Kp,
                                Ki,
                                Kii,
                                loop_rate_count,
                                nominal_mash_val);

    // Setup PFD state
    sw_pll_pfd_init(&(sw_pll->pfd_state), loop_rate_count, pll_ratio, ref_clk_expected_inc, ppm_range);

    return SW_PLL_SUCCESS;
}


__attribute__((always_inline))
inline sw_pll_lock_status_t sw_pll_mash_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error)
{
    int32_t total_error = sw_pll_do_pi_ctrl(sw_pll, error);
    int32_t requested_dco_ctl = sw_pll->mash_state.nominal_mash_val - total_error;
    int32_t dco_ctl = requested_dco_ctl;

    if(dco_ctl > SW_PLL_MASH_UPPER_LIMIT){
        dco_ctl = SW_PLL_MASH_UPPER_LIMIT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_HIGH;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
    } else if (dco_ctl < SW_PLL_MASH_LOWER_LIMIT){
        dco_ctl = SW_PLL_MASH_LOWER_LIMIT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
    } else {
        if(sw_pll->lock_counter){
            sw_pll->lock_counter--;
        } else {
            sw_pll->lock_status = SW_PLL_LOCKED;
        }
    }

    xsystem_switch_reg_value_t frac_reg_val = VX_FRAC_N_MASH_ENABLE_SET(VX_FRAC_N_MASH_MOD_SET(0, dco_ctl), 1);
    sswitch_write_reg_no_ack(get_local_tile_id(), VX_SSB_CSR_PLL1_FRACN_MASH_NUM, frac_reg_val);
    // printf("0x%x\n", frac_reg_val);
    // printf("md: %d\n", sw_pll->pfd_state.mclk_diff);
        
    return sw_pll->lock_status;
}

sw_pll_lock_status_t sw_pll_mash_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_clk_pt)
{
    if (++sw_pll->loop_counter == sw_pll->loop_rate_count)
    {
        sw_pll->loop_counter = 0;

        if (sw_pll->first_loop) // First loop around so ensure state is clear
        {
            sw_pll->pfd_state.mclk_pt_last = mclk_pt;  // load last mclk measurement with sensible data
            sw_pll_reset_pi_state(sw_pll);
            sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
            sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;

            sw_pll->first_loop = 0;

            // Do not set PLL frac as last setting probably the best. At power on we set to nominal (midway in table)
        }
        else
        {
            sw_pll_calc_error_from_port_timers(&sw_pll->pfd_state, &sw_pll->first_loop, mclk_pt, ref_clk_pt);
            sw_pll_mash_do_control_from_error(sw_pll, sw_pll->pfd_state.mclk_diff);

            // Save for next iteration to calc diff
            sw_pll->pfd_state.mclk_pt_last = mclk_pt;

        }
    }

    return sw_pll->lock_status;
}

#endif // if defined(__VX4B__)
