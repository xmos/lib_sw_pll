// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <stdio.h>
#include <stdlib.h>
#include <xscope.h>
#include <xs1.h>

#include "sw_pll.h"

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

void setup_recovered_ref_clock_output(port_t p_recovered_ref_clk, xclock_t clk_recovered_ref_clk, port_t p_mclk, unsigned divider)
{
    // Connect clock block with divide to mclk
    clock_enable(clk_recovered_ref_clk);
    clock_set_source_port(clk_recovered_ref_clk, p_mclk);
    clock_set_divide(clk_recovered_ref_clk, divider / 2);
    printf("Divider: %u\n", divider);

    // Output the divided mclk on a port
    port_enable(p_recovered_ref_clk);
    port_set_clock(p_recovered_ref_clk, clk_recovered_ref_clk);
    port_set_out_clock(p_recovered_ref_clk);
    clock_start(clk_recovered_ref_clk);
}

void sw_pll_test(void){

    // Declare mclk and refclk resources and connect up
    port_t p_mclk = PORT_MCLK_IN;
    xclock_t clk_mclk = XS1_CLKBLK_1;
    port_t p_ref_clk = PORT_I2S_LRCLK;
    xclock_t clk_word_clk = XS1_CLKBLK_2;
    port_t p_ref_clk_count = XS1_PORT_32A;
    setup_ref_and_mclk_ports_and_clocks(p_mclk, clk_mclk, p_ref_clk, clk_word_clk, p_ref_clk_count);

    // Make a test output to observe the recovered mclk divided down to the refclk frequency
    xclock_t clk_recovered_ref_clk = XS1_CLKBLK_3;
    port_t p_recovered_ref_clk = PORT_I2S_DAC_DATA;
    setup_recovered_ref_clock_output(p_recovered_ref_clk, clk_recovered_ref_clk, p_mclk, PLL_RATIO);
    
    sw_pll_state_t sw_pll;
    sw_pll_init(&sw_pll,
                SW_PLL_15Q16(0.0),
                SW_PLL_15Q16(1.0),
                SW_PLL_15Q16(0.01),
                CONTROL_LOOP_COUNT,
                PLL_RATIO,
                0,
                frac_values_80,
                SW_PLL_NUM_LUT_ENTRIES(frac_values_80),
                APP_PLL_CTL_12288,
                APP_PLL_DIV_12288,
                APP_PLL_NOMINAL_INDEX_12288,
                PPM_RANGE);

    int lock_status = SW_PLL_LOCKED;

    uint32_t max_time = 0;
    while(1)
    {
        port_in(p_ref_clk_count);   // This blocks each time round the loop until it can sample input (rising edges of word clock). So we know the count will be +1 each time.
        uint16_t mclk_pt =  port_get_trigger_time(p_ref_clk);// Get the port timer val from p_ref_clk (which is running from MCLK). So this is basically a 16 bit free running counter running from MCLK.
        
        uint32_t t0 = get_reference_time();
        sw_pll_do_control(&sw_pll, mclk_pt, 0);
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

#define DO_CLOCKS \
printf("Ref Hz: %d\n", clock_rate >> 1); \
\
unsigned cycle_ticks_int = XS1_TIMER_HZ / clock_rate; \
unsigned cycle_ticks_remaidner = XS1_TIMER_HZ % clock_rate; \
unsigned carry = 0; \
\
period_trig += XS1_TIMER_HZ * 1; \
unsigned time_now = hwtimer_get_time(period_tmr); \
while(TIMER_TIMEAFTER(period_trig, time_now)) \
{ \
    port_out(p_clock_gen, port_val); \
    hwtimer_wait_until(clock_tmr, time_trig); \
    time_trig += cycle_ticks_int; \
    carry += cycle_ticks_remaidner; \
    if(carry >= clock_rate){ \
        time_trig++; \
        carry -= clock_rate; \
    } \
    port_val ^= 1; \
    time_now = hwtimer_get_time(period_tmr); \
}

void clock_gen(void)
{
    unsigned clock_rate = REF_FREQUENCY * 2; // Note double because we generate edges at this rate
    unsigned ppm_range = 150; // Step from - to + this

    unsigned clock_rate_low = (unsigned)(clock_rate * (1.0 - (float)ppm_range / 1000000.0));
    unsigned clock_rate_high = (unsigned)(clock_rate * (1.0 + (float)ppm_range / 1000000.0));
    unsigned step_size = (clock_rate_high - clock_rate_low) / 20;

    printf("Sweep range: %d %d %d, step size: %d\n", clock_rate_low / 2, clock_rate / 2, clock_rate_high / 2, step_size);

    hwtimer_t period_tmr = hwtimer_alloc();
    unsigned period_trig = hwtimer_get_time(period_tmr);

    hwtimer_t clock_tmr = hwtimer_alloc();
    unsigned time_trig = hwtimer_get_time(clock_tmr);

    port_t p_clock_gen = PORT_I2S_BCLK;
    port_enable(p_clock_gen);
    unsigned port_val = 1;

    for(unsigned clock_rate = clock_rate_low; clock_rate <= clock_rate_high; clock_rate += 2 * step_size){
        DO_CLOCKS
    }
    for(unsigned clock_rate = clock_rate_high; clock_rate > clock_rate_low; clock_rate -= 2 * step_size){
        DO_CLOCKS
    }
    exit(0);
}