// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

#define SW_PLL_LOCK_COUNT   10 // The number of consecutive lock positive reports of the control loop before declaring we are finally locked

// Implement a delay in 100MHz timer ticks without using a timer resource
static void blocking_delay(uint32_t delay_ticks){
    uint32_t time_delay = get_reference_time() + delay_ticks;
    while(TIMER_TIMEAFTER(time_delay, get_reference_time()));
}


// Set secondary (App) PLL control register safely to work around chip bug.
static void sw_pll_app_pll_init(unsigned tileid, uint32_t app_pll_ctl_reg_val, uint32_t app_pll_div_reg_val, uint16_t frac_val_nominal)
{
    // Disable the PLL 
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, (app_pll_ctl_reg_val & 0xF7FFFFFF));
    // Enable the PLL to invoke a reset on the appPLL.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);
    // Must write the CTL register twice so that the F and R divider values are captured using a running clock.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);
    // Now disable and re-enable the PLL so we get the full 5us reset time with the correct F and R values.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, (app_pll_ctl_reg_val & 0xF7FFFFFF));
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);

    // Write the fractional-n register and set to nominal
    // We set the top bit to enable the frac-n block.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, (0x80000000 | frac_val_nominal));
    // And then write the clock divider register to enable the output
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM, app_pll_div_reg_val);

    // Wait for PLL to lock.
    blocking_delay(10 * XS1_TIMER_KHZ);
}

static inline uint16_t lookup_pll_frac(sw_pll_state_t *sw_pll, int32_t total_error)
{
    int set = (sw_pll->nominal_lut_idx - total_error); //Notice negative term for error
    unsigned int frac_index = 0;

    if (set < 0) 
    {
        frac_index = 0;
        sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
        sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    }
    else if (set > sw_pll->num_lut_entries) 
    {
        frac_index = sw_pll->num_lut_entries;
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


void sw_pll_init(   sw_pll_state_t *sw_pll,
                    sw_pll_15q16_t Kp,
                    sw_pll_15q16_t Ki,
                    sw_pll_15q16_t Kii,
                    size_t loop_rate_count,
                    size_t pll_ratio,
                    uint32_t ref_clk_expected_inc,
                    int16_t *lut_table_base,
                    size_t num_lut_entries,
                    uint32_t app_pll_ctl_reg_val,
                    uint32_t app_pll_div_reg_val,
                    unsigned nominal_lut_idx,
                    unsigned ppm_range)
{
    // Get PLL started and running at nominal
    sw_pll_app_pll_init(get_local_tile_id(),
                    app_pll_ctl_reg_val,
                    app_pll_div_reg_val,
                    lut_table_base[nominal_lut_idx]);

    // Setup user paramaters
    sw_pll->current_reg_val = app_pll_div_reg_val;
    sw_pll->Kp = Kp;
    sw_pll->Ki = Ki;
    sw_pll->Kii = Kii;
    if(Ki){
        sw_pll->i_windup_limit = ((num_lut_entries << SW_PLL_NUM_FRAC_BITS) / Ki); // Set to twice the max total error input to LUT
    }else{
        sw_pll->i_windup_limit = 0;
    }
    if(Kii){
        sw_pll->ii_windup_limit = ((num_lut_entries << SW_PLL_NUM_FRAC_BITS) / Kii); // Set to twice the max total error input to LUT
    }else{
        sw_pll->ii_windup_limit = 0;
    }
    sw_pll->loop_rate_count = loop_rate_count;

    // Setup LUT params
    sw_pll->lut_table_base = lut_table_base;
    sw_pll->num_lut_entries = num_lut_entries;
    sw_pll->nominal_lut_idx = nominal_lut_idx;

    // Setup general state
    sw_pll->mclk_diff = 0;
    sw_pll->ref_clk_pt_last = 0;
    sw_pll->ref_clk_expected_inc = ref_clk_expected_inc * loop_rate_count;
    sw_pll->error_accum = 0;
    sw_pll->error_accum_accum = 0;
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
    sw_pll->mclk_pt_last = 0;
    sw_pll->mclk_expected_pt_inc = loop_rate_count * pll_ratio;
    // Set max PPM deviation before we chose to reset the PLL state. Nominally twice the normal range.
    sw_pll->mclk_max_diff = (uint64_t)(((uint64_t)ppm_range * 2ULL * (uint64_t)pll_ratio * (uint64_t)loop_rate_count) / 1000000); 
    sw_pll->loop_counter = 0;    
    sw_pll->first_loop = 1;
}


sw_pll_lock_status_t sw_pll_do_control(sw_pll_state_t *sw_pll, uint16_t mclk_pt, uint16_t ref_clk_pt)
{
    if (++sw_pll->loop_counter == sw_pll->loop_rate_count)
    {
        sw_pll->loop_counter = 0;

        if (sw_pll->first_loop) // First loop around so ensure state is clear
        {
            sw_pll->mclk_pt_last = mclk_pt;  // load last mclk measurement with sensible data
            sw_pll->error_accum = 0;
            sw_pll->error_accum_accum = 0;
            sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
            sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;

            sw_pll->first_loop = 0;

            // Do not set PLL frac as last setting probably the best. At power on we set to nominal (midway in table)
        }
        else
        {
            uint16_t mclk_expected_pt = 0;
            // See if we are using variable loop period sampling, if so, compensate for it
            if(sw_pll->ref_clk_expected_inc)
            {
                uint16_t ref_clk_expected_pt = sw_pll->ref_clk_pt_last + sw_pll->ref_clk_expected_inc;
                // This uses casting trickery to work out the difference between the timer values accounting for wrap at 65536
                int16_t ref_clk_diff = PORT_TIMEAFTER(ref_clk_pt, ref_clk_expected_pt) ? -(int16_t)(ref_clk_expected_pt - ref_clk_pt) : (int16_t)(ref_clk_pt - ref_clk_expected_pt);
                sw_pll->ref_clk_pt_last = ref_clk_pt;

                // This allows for wrapping of the timer when CONTROL_LOOP_COUNT is high
                uint32_t mclk_expected_pt_inc = sw_pll->mclk_expected_pt_inc * (sw_pll->ref_clk_expected_inc + ref_clk_diff) / sw_pll->ref_clk_expected_inc;
                mclk_expected_pt = sw_pll->mclk_pt_last + mclk_expected_pt_inc;
            }
            else // we are assuming mclk_pt is sampled precisely and needs no compoensation
            {
                mclk_expected_pt = sw_pll->mclk_pt_last + sw_pll->mclk_expected_pt_inc;
            }

            // This uses casting trickery to work out the difference between the timer values accounting for wrap at 65536
            sw_pll->mclk_diff = PORT_TIMEAFTER(mclk_pt, mclk_expected_pt) ? -(int16_t)(mclk_expected_pt - mclk_pt) : (int16_t)(mclk_pt - mclk_expected_pt);

            // Check to see if something has gone very wrong, for example ref clock stop/start. If so, reset state and keep trying
            if(MAGNITUDE(sw_pll->mclk_diff) > sw_pll->mclk_max_diff)
            {
                sw_pll->first_loop = 1;
            }

            sw_pll->error_accum += sw_pll->mclk_diff; // Integral error.
            sw_pll->error_accum = sw_pll->error_accum > sw_pll->i_windup_limit ? sw_pll->i_windup_limit : sw_pll->error_accum;
            sw_pll->error_accum = sw_pll->error_accum < -sw_pll->i_windup_limit ? -sw_pll->i_windup_limit : sw_pll->error_accum;
            
            sw_pll->error_accum_accum += sw_pll->error_accum; // Double integral error.
            sw_pll->error_accum_accum = sw_pll->error_accum_accum > sw_pll->ii_windup_limit ? sw_pll->ii_windup_limit : sw_pll->error_accum_accum;
            sw_pll->error_accum_accum = sw_pll->error_accum_accum < -sw_pll->ii_windup_limit ? -sw_pll->ii_windup_limit : sw_pll->error_accum_accum;

            // Use long long maths to avoid overflow if ever we had a large error accum term
            int64_t error_p = ((int64_t)sw_pll->Kp * (int64_t)sw_pll->mclk_diff);
            int64_t error_i = ((int64_t)sw_pll->Ki * (int64_t)sw_pll->error_accum);
            int64_t error_ii = ((int64_t)sw_pll->Kii * (int64_t)sw_pll->error_accum_accum);

            // Convert back to 32b since we are handling LUTs of around a hundred entries
            int32_t error = (int32_t)((error_p + error_i + error_ii) >> SW_PLL_NUM_FRAC_BITS);
            sw_pll->current_reg_val = lookup_pll_frac(sw_pll, error);

            sw_pll->mclk_pt_last = mclk_pt;

            write_sswitch_reg_no_ack(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, (0x80000000 | sw_pll->current_reg_val));
        }
    }

    return sw_pll->lock_status;
}
