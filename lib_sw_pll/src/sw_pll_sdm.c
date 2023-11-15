// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"
#include "sw_pll_pfd.h"
#include <xcore/assert.h>

#define SW_PLL_LOCK_COUNT   10 // The number of consecutive lock positive reports of the control loop before declaring we are finally locked

// Implement a delay in 100MHz timer ticks without using a timer resource
static void blocking_delay(const uint32_t delay_ticks){
    uint32_t time_delay = get_reference_time() + delay_ticks;
    while(TIMER_TIMEAFTER(time_delay, get_reference_time()));
}


__attribute__((always_inline))
static inline uint16_t lookup_pll_frac(sw_pll_state_t * const sw_pll, const int32_t total_error)
{
    const int set = (sw_pll->nominal_lut_idx - total_error); //Notice negative term for error
    unsigned int frac_index = 0;

    if (set < 0) 
    {
        frac_index = 0;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    }
    else if (set >= sw_pll->num_lut_entries) 
    {
        frac_index = sw_pll->num_lut_entries - 1;
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

    return sw_pll->lut_table_base[frac_index];
}


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
    sw_pll_reset(sw_pll, Kp, Ki, 0); // TODO work out windup limit

    sw_pll->loop_rate_count = loop_rate_count;
    sw_pll->current_reg_val = app_pll_div_reg_val;

    // Setup LUT params
    // sw_pll->lut_table_base = lut_table_base;
    // sw_pll->num_lut_entries = num_lut_entries;
    // sw_pll->nominal_lut_idx = nominal_lut_idx;

    // Setup general state
    sw_pll->mclk_diff = 0;
    sw_pll->ref_clk_pt_last = 0;
    sw_pll->ref_clk_expected_inc = ref_clk_expected_inc * loop_rate_count;
    if(sw_pll->ref_clk_expected_inc) // Avoid div 0 error if ref_clk compensation not used
    {
        sw_pll->ref_clk_scaling_numerator = (1ULL << SW_PLL_PRE_DIV_BITS) / sw_pll->ref_clk_expected_inc + 1; //+1 helps with rounding accuracy
    }
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
    sw_pll->mclk_pt_last = 0;
    sw_pll->mclk_expected_pt_inc = loop_rate_count * pll_ratio;
    // Set max PPM deviation before we chose to reset the PLL state. Nominally twice the normal range.
    sw_pll->mclk_max_diff = (uint64_t)(((uint64_t)ppm_range * 2ULL * (uint64_t)pll_ratio * (uint64_t)loop_rate_count) / 1000000); 
    sw_pll->loop_counter = 0;    
    sw_pll->first_loop = 1;

    // Check we can actually support the numbers used in the maths we use
    const float calc_max = (float)0xffffffffffffffffULL / 1.1; // Add 10% headroom from ULL MAX
    const float max = (float)sw_pll->ref_clk_expected_inc 
                    * (float)sw_pll->ref_clk_scaling_numerator 
                    * (float)sw_pll->mclk_expected_pt_inc;
    // If you have hit this assert then you need to reduce loop_rate_count or possibly the PLL ratio and or MCLK frequency
    xassert(max < calc_max);
}


__attribute__((always_inline))
inline sw_pll_lock_status_t sw_pll_sdm_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error)
{
    sw_pll->error_accum += error; // Integral error.
    sw_pll->error_accum = sw_pll->error_accum > sw_pll->i_windup_limit ? sw_pll->i_windup_limit : sw_pll->error_accum;
    sw_pll->error_accum = sw_pll->error_accum < -sw_pll->i_windup_limit ? -sw_pll->i_windup_limit : sw_pll->error_accum;

    // Use long long maths to avoid overflow if ever we had a large error accum term
    int64_t error_p = ((int64_t)sw_pll->Kp * (int64_t)error);
    int64_t error_i = ((int64_t)sw_pll->Ki * (int64_t)sw_pll->error_accum);

    // Convert back to 32b since we are handling LUTs of around a hundred entries
    int32_t total_error = (int32_t)((error_p + error_i) >> SW_PLL_NUM_FRAC_BITS);
    sw_pll->current_reg_val = lookup_pll_frac(sw_pll, total_error);

    write_sswitch_reg_no_ack(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, (0x80000000 | sw_pll->current_reg_val));

    return sw_pll->lock_status;
}

sw_pll_lock_status_t sw_pll_sdm_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_clk_pt)
{
    if (++sw_pll->loop_counter == sw_pll->loop_rate_count)
    {
        sw_pll->loop_counter = 0;

        if (sw_pll->first_loop) // First loop around so ensure state is clear
        {
            sw_pll->mclk_pt_last = mclk_pt;  // load last mclk measurement with sensible data
            sw_pll->error_accum = 0;
            sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
            sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;

            sw_pll->first_loop = 0;

            // Do not set PLL frac as last setting probably the best. At power on we set to nominal (midway in table)
        }
        else
        {
            sw_pll_calc_error_from_port_timers(sw_pll, mclk_pt, ref_clk_pt);
            sw_pll_sdm_do_control_from_error(sw_pll, sw_pll->mclk_diff);

            // Save for next iteration to calc diff
            sw_pll->mclk_pt_last = mclk_pt;

        }
    }

    return sw_pll->lock_status;
}
