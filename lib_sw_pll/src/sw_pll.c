// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

#define SW_PLL_LOCK_COUNT   10 // The number of consecutive lock positive reports of the control loop before declaring we are finally locked

void setup_ref_and_mclk_ports_and_clocks(port_t p_mclk, xclock_t clk_mclk, port_t p_ref_clk_in, xclock_t clk_word_clk, port_t p_ref_clk_count)
{
    // Create clock from mclk port and use it to clock the p_ref_clk port.
    clock_enable(clk_mclk);
    port_enable(p_mclk);
    clock_set_source_port(clk_mclk, p_mclk);

    // Clock p_ref_clk from MCLK
    port_enable(p_ref_clk_in);
    port_set_clock(p_ref_clk_in, clk_mclk);

    clock_start(clk_mclk);

    // Create clock from ref_clock_port and use it to clock the p_ref_clk_count port.
    clock_enable(clk_word_clk);
    clock_set_source_port(clk_word_clk, p_ref_clk_in);
    port_enable(p_ref_clk_count);
    port_set_clock(p_ref_clk_count, clk_word_clk);

    clock_start(clk_word_clk);
}

// Implement a delay in ticks without using a timer resource
static void blocking_delay(uint32_t delay_ticks){
    uint32_t time_delay = get_reference_time() + delay_ticks;
    while(TIMER_TIMEAFTER(time_delay, get_reference_time()));
}


// Set secondary (App) PLL control register safely to work around chip bug.
static void sw_pll_app_pll_init(unsigned tileid, uint32_t app_pll_ctl_reg_val, uint32_t div_val, uint16_t frac_val_nominal)
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
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM, div_val);

    // Wait for PLL to lock.
    blocking_delay(10 * XS1_TIMER_KHZ);
}

static uint16_t lookup_pll_frac(sw_pll_state_t *sw_pll, int32_t total_error)
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

void sw_pll_reset(sw_pll_state_t *sw_pll)
{
    sw_pll->first_loop = 1;
}

void sw_pll_init(   sw_pll_state_t *sw_pll,
                    sw_pll_15q16_t Kp,
                    sw_pll_15q16_t Ki,
                    size_t loop_rate_count,
                    size_t pll_ratio,
                    int16_t *lut_table_base,
                    size_t num_lut_entries,
                    uint32_t app_pll_ctl_reg_val,
                    uint32_t div_val,
                    unsigned nominal_lut_idx,
                    unsigned ppm_range)
{
    // Get PLL started and running at nominal
    sw_pll_app_pll_init(get_local_tile_id(),
                    app_pll_ctl_reg_val,
                    div_val,
                    lut_table_base[nominal_lut_idx]);

    // Setup user paramaters
    sw_pll->Kp = Kp;
    sw_pll->Ki = Ki;
    sw_pll->i_windup_limit = (num_lut_entries / Ki) >> 16; // Set to twice the max total error input to LUT
    sw_pll->ii_windup_limit = 0; //(num_lut_entries / Kii) >> 16; // Set to twice the max total error input to LUT
    sw_pll->loop_rate_count = loop_rate_count;

    // Setup LUT params
    sw_pll->lut_table_base = lut_table_base;
    sw_pll->num_lut_entries = num_lut_entries;
    sw_pll->nominal_lut_idx = nominal_lut_idx;

    // Setup general state
    sw_pll->error_accum = 0;
    sw_pll->lock_status = SW_PLL_UNLOCKED_LOW;
    sw_pll->lock_counter = SW_PLL_LOCK_COUNT;
    sw_pll->mclk_pt_last = 0;
    sw_pll->mclk_expected_pt_inc = (loop_rate_count * pll_ratio) % 65536; // Port timers are 16b counters
    // Set max PPM deviation before we chose to reset the PLL state. Nominally twice the normal range.
    sw_pll->mclk_max_diff = (uint64_t)(((uint64_t)ppm_range * 2ULL * (uint64_t)pll_ratio * (uint64_t)loop_rate_count) / 1000000); 
    sw_pll->loop_counter = 0;    
    sw_pll->first_loop = 1;
}

int sw_pll_do_control(sw_pll_state_t *sw_pll, uint16_t mclk_pt)
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
            // printstr("PLL STATE RESET\n");
        }
        else
        {
            uint16_t mclk_expected_pt = sw_pll->mclk_pt_last + sw_pll->mclk_expected_pt_inc; // 

            // This uses casting trickery to work out the difference between the timer values accounting for wrap at 65536
            int16_t mclk_diff = PORT_TIMEAFTER(mclk_pt, mclk_expected_pt) ? -(int16_t)(mclk_expected_pt - mclk_pt) : (int16_t)(mclk_pt - mclk_expected_pt);

            // Check to see if something has gone very wrong, for example ref clock stop/start. If so, reset state and keep trying
            if(MAGNITUDE(mclk_diff) > sw_pll->mclk_max_diff)
            {
                printf("diff: %d max: %d\n", mclk_diff, sw_pll->mclk_max_diff);
                sw_pll->first_loop = 1;
            }

            sw_pll->error_accum += mclk_diff; // Integral error.
            sw_pll->error_accum = sw_pll->error_accum > sw_pll->i_windup_limit ? sw_pll->i_windup_limit : sw_pll->error_accum;
            sw_pll->error_accum = sw_pll->error_accum < -sw_pll->i_windup_limit ? -sw_pll->i_windup_limit : sw_pll->error_accum;
            
            // Use long long maths to avoid overflow if ever we had a large error accum term
            int64_t error_p = ((int64_t)sw_pll->Kp * (int64_t)mclk_diff);
            int64_t error_i = ((int64_t)sw_pll->Ki * (int64_t)sw_pll->error_accum);

            // Convert back to 32b since we are handling LUTs of around a hundred entries
            int32_t error = (int32_t)((error_p + error_i) >> 16);

            uint16_t pll_reg = lookup_pll_frac(sw_pll, error);

            sw_pll->mclk_pt_last = mclk_pt;

            // Debug only. Note this takes a long time to print so may cause missing of a ref clock loop which will send ctrl unstable
            // printf("%d %4d, E%5ld, F%3d, %s\n",
            //        ref_clk_pt & 0x1ff, mclk_diff, error, frac_index, sw_pll->locked ? "LOCKED" : "UNLOCKED");
            write_sswitch_reg_no_ack(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, (0x80000000 | pll_reg));

        }
    }

    return sw_pll->lock_status;
}
