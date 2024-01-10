// Copyright 2022-2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#ifdef __XS3A__

#include "sw_pll.h"


__attribute__((always_inline))
static inline uint16_t lookup_pll_frac(sw_pll_state_t * const sw_pll, const int32_t total_error)
{
    const int set = (sw_pll->lut_state.nominal_lut_idx - total_error); //Notice negative term for error
    unsigned int frac_index = 0;

    if (set < 0) 
    {
        frac_index = 0;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    }
    else if (set >= sw_pll->lut_state.num_lut_entries) 
    {
        frac_index = sw_pll->lut_state.num_lut_entries - 1;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_HIGH;
    }
    else 
    {
        frac_index = set;
        if(sw_pll->lock_counter){
            sw_pll->lock_counter--;
            // Keep last unlocked status
        }
        else
        {
           sw_pll->lock_status = SW_PLL_LOCKED; 
        }
    }

    return sw_pll->lut_state.lut_table_base[frac_index];
}

void sw_pll_lut_init(   sw_pll_state_t * const sw_pll,
                        const sw_pll_15q16_t Kp,
                        const sw_pll_15q16_t Ki,
                        const sw_pll_15q16_t Kii,
                        const size_t loop_rate_count,
                        const size_t pll_ratio,
                        const uint32_t ref_clk_expected_inc,
                        const int16_t * const lut_table_base,
                        const size_t num_lut_entries,
                        const uint32_t app_pll_ctl_reg_val,
                        const uint32_t app_pll_div_reg_val,
                        const unsigned nominal_lut_idx,
                        const unsigned ppm_range)
{
    // Get PLL started and running at nominal
    sw_pll_app_pll_init(get_local_tile_id(),
                    app_pll_ctl_reg_val,
                    app_pll_div_reg_val,
                    lut_table_base[nominal_lut_idx]);

    // Setup sw_pll with supplied user paramaters
    sw_pll_lut_reset(sw_pll, Kp, Ki, Kii, num_lut_entries);

    // Setup general controller state
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;

    sw_pll->loop_rate_count = loop_rate_count;    
    sw_pll->loop_counter = 0;
    sw_pll->first_loop = 1;

    sw_pll_reset_pi_state(sw_pll);

    // Setup LUT params
    sw_pll->lut_state.current_reg_val = app_pll_div_reg_val;
    sw_pll->lut_state.lut_table_base = lut_table_base;
    sw_pll->lut_state.num_lut_entries = num_lut_entries;
    sw_pll->lut_state.nominal_lut_idx = nominal_lut_idx;

    // Setup PFD state
    sw_pll_pfd_init(&(sw_pll->pfd_state), loop_rate_count, pll_ratio, ref_clk_expected_inc, ppm_range);
}


__attribute__((always_inline))
inline sw_pll_lock_status_t sw_pll_lut_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error)
{
    int32_t total_error = sw_pll_do_pi_ctrl(sw_pll, error);
    sw_pll->lut_state.current_reg_val = lookup_pll_frac(sw_pll, total_error);

    write_sswitch_reg_no_ack(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, (0x80000000 | sw_pll->lut_state.current_reg_val));

    return sw_pll->lock_status;
}

sw_pll_lock_status_t sw_pll_lut_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_clk_pt)
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
            sw_pll_lut_do_control_from_error(sw_pll, sw_pll->pfd_state.mclk_diff);

            // Save for next iteration to calc diff
            sw_pll->pfd_state.mclk_pt_last = mclk_pt;

        }
    }

    return sw_pll->lock_status;
}

#endif // __XS3A__
