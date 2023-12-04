// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <xscope.h>
#include <xs1.h>
#include <platform.h>

#include <xcore/select.h>

#include "sw_pll.h"
#include "resource_setup.h"

#define MCLK_FREQUENCY              24576000
#define REF_FREQUENCY               96000
#define PLL_RATIO                   (MCLK_FREQUENCY / REF_FREQUENCY)
#define CONTROL_LOOP_COUNT          512

#include "register_setup.h"

void sdm_task(chanend_t c_sdm_control){
    printf("sdm_task\n");

    const uint32_t sdm_interval = XS1_TIMER_HZ / SW_PLL_SDM_RATE; // in 10ns ticks = 1MHz

    sw_pll_sdm_state_t sdm_state;
    sw_pll_init_sigma_delta(&sdm_state);

    tileref_t this_tile = get_local_tile_id();

    hwtimer_t tmr = hwtimer_alloc();
    int32_t trigger_time = hwtimer_get_time(tmr) + sdm_interval;
    bool running = true;
    int32_t sdm_in = 0; // Zero is an invalid number and the SDM will not write the frac reg until 
                        // the first control value has been received. This avoids issues with 
                        // channel lockup if two tasks (eg. init and SDM) try to write at the same 
                        // time. 

    while(running){
        // Poll for new SDM control value
        SELECT_RES(
            CASE_THEN(c_sdm_control, ctrl_update),
            DEFAULT_THEN(default_handler)
        )
        {
            ctrl_update:
            {
                sdm_in = chan_in_word(c_sdm_control);
            }
            break;

            default_handler:
            {
                // Do nothing & fall-through
            }
            break;
        }

        // Wait until the timer value has been reached
        // This implements a timing barrier and keeps
        // the loop rate constant.
        hwtimer_wait_until(tmr, trigger_time);
        trigger_time += sdm_interval;

        // Do not write to the frac reg until we get out first
        // control value. This will avoid the writing of the
        // frac reg from two different threads which may cause
        // a channel deadlock.
        if(sdm_in){
            sw_pll_do_sigma_delta(&sdm_state, this_tile, sdm_in);
        }
    }
}

void sw_pll_send_ctrl_to_sdm_task(chanend_t c_sdm_control, int32_t dco_ctl){
    chan_out_word(c_sdm_control, dco_ctl);
}

void sw_pll_sdm_test(chanend_t c_sdm_control){

    // Declare mclk and refclk resources and connect up
    port_t p_mclk = PORT_MCLK_IN;
    xclock_t clk_mclk = XS1_CLKBLK_1;
    port_t p_clock_counter = PORT_I2S_LRCLK;
    xclock_t clk_ref_clk = XS1_CLKBLK_2;
    port_t p_ref_clk_timing = XS1_PORT_32A;
    setup_ref_and_mclk_ports_and_clocks(p_mclk, clk_mclk, p_clock_counter, clk_ref_clk, p_ref_clk_timing);

    // Make a test output to observe the recovered mclk divided down to the refclk frequency
    xclock_t clk_recovered_ref_clk = XS1_CLKBLK_3;
    port_t p_recovered_ref_clk = PORT_I2S_DAC_DATA;
    setup_recovered_ref_clock_output(p_recovered_ref_clk, clk_recovered_ref_clk, p_mclk, PLL_RATIO);
    
    sw_pll_state_t sw_pll;
    sw_pll_sdm_init(&sw_pll,
                SW_PLL_15Q16(0.0),
                SW_PLL_15Q16(32.0),
                SW_PLL_15Q16(0.25),
                CONTROL_LOOP_COUNT,
                PLL_RATIO,
                0, /* No jitter compensation needed */
                APP_PLL_CTL_REG,
                APP_PLL_DIV_REG,
                APP_PLL_FRAC_REG,
                SW_PLL_SDM_CTRL_MID,
                3000 /*PPM_RANGE FOR PFD*/);

    sw_pll_lock_status_t lock_status = SW_PLL_LOCKED;

    uint32_t max_time = 0;
    while(1)
    {
        port_in(p_ref_clk_timing);   // This blocks each time round the loop until it can sample input (rising edges of word clock). So we know the count will be +1 each time.
        uint16_t mclk_pt =  port_get_trigger_time(p_clock_counter);// Get the port timer val from p_clock_counter (which is running from MCLK). So this is basically a 16 bit free running counter running from MCLK.
        
        uint32_t t0 = get_reference_time();
        bool ctrl_done = sw_pll_sdm_do_control(&sw_pll, mclk_pt, 0);
        uint32_t t1 = get_reference_time();

        if(ctrl_done){
            sw_pll_send_ctrl_to_sdm_task(c_sdm_control, sw_pll.sdm_state.current_ctrl_val);
        }

        if(t1 - t0 > max_time){
            max_time = t1 - t0;
            printf("Max ticks taken: %lu\n", max_time);
        }

        if(sw_pll.lock_status != lock_status){
            lock_status = sw_pll.lock_status;
            const char msg[3][16] = {"UNLOCKED LOW\0", "LOCKED\0", "UNLOCKED HIGH\0"};
            printf("%s\n", msg[lock_status+1]);
        }
    }
}
