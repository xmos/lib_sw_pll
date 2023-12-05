// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <stdio.h>
#include <stdlib.h>
#include <xscope.h>
#include <xs1.h>

#include "sw_pll.h"
#include "resource_setup.h"

#define MCLK_FREQUENCY              12288000
#define REF_FREQUENCY               48000
#define PLL_RATIO                   (MCLK_FREQUENCY / REF_FREQUENCY)
#define CONTROL_LOOP_COUNT          512
#define PPM_RANGE                   150

#define APP_PLL_CTL_12288           0x0881FA03
#define APP_PLL_DIV_12288           0x8000001E
#define APP_PLL_NOMINAL_INDEX_12288 35

//Found solution: IN 24.000MHz, OUT 12.288018MHz, VCO 3047.43MHz, RD  4, FD  507.905 (m =  19, n =  21), OD  2, FOD   31, ERR +1.50ppm
#include "fractions.h"

void sw_pll_test(void){

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
    sw_pll_lut_init(&sw_pll,
                    SW_PLL_15Q16(0.0),
                    SW_PLL_15Q16(1.0),
                    SW_PLL_15Q16(0.0),
                    CONTROL_LOOP_COUNT,
                    PLL_RATIO,
                    0, /* No jitter compensation needed */
                    frac_values_80,
                    SW_PLL_NUM_LUT_ENTRIES(frac_values_80),
                    APP_PLL_CTL_12288,
                    APP_PLL_DIV_12288,
                    APP_PLL_NOMINAL_INDEX_12288,
                    PPM_RANGE);

    sw_pll_lock_status_t lock_status = SW_PLL_LOCKED;

    uint32_t max_time = 0;
    while(1)
    {
        port_in(p_ref_clk_timing);   // This blocks each time round the loop until it can sample input (rising edges of word clock). So we know the count will be +1 each time.
        uint16_t mclk_pt =  port_get_trigger_time(p_clock_counter);// Get the port timer val from p_clock_counter (which is clocked running from the PLL output).        
        uint32_t t0 = get_reference_time();
        sw_pll_lut_do_control(&sw_pll, mclk_pt, 0);
        uint32_t t1 = get_reference_time();
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
