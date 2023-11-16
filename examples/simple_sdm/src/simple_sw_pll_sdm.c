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

#define MCLK_FREQUENCY              24576000
#define REF_FREQUENCY               48000
#define PLL_RATIO                   (MCLK_FREQUENCY / REF_FREQUENCY)
#define CONTROL_LOOP_COUNT          512
#define PPM_RANGE                   150 //TODO eliminate

#include "register_setup.h"
#define APP_PLL_NOMINAL_INDEX_12288 35 //TODO eliminate

typedef int tileref_t;

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

typedef struct sdm_state_t{
    int32_t ds_x1;
    int32_t ds_x2;
    int32_t ds_x3;
}sdm_state_t;


void init_sigma_delta(sdm_state_t *sdm_state){
    sdm_state->ds_x1 = 0;
    sdm_state->ds_x2 = 0;
    sdm_state->ds_x3 = 0;
}

__attribute__((always_inline))
static inline int32_t do_sigma_delta(sdm_state_t *sdm_state, int32_t ds_in){
    // Third order, 9 level output delta sigma. 20 bit unsigned input.
    int32_t ds_out = ((sdm_state->ds_x3<<4) + (sdm_state->ds_x3<<1)) >> 13;
    if (ds_out > 8){
        ds_out = 8;
    }
    if (ds_out < 0){
        ds_out = 0;
    }
    sdm_state->ds_x3 += (sdm_state->ds_x2>>5) - (ds_out<<9) - (ds_out<<8);
    sdm_state->ds_x2 += (sdm_state->ds_x1>>5) - (ds_out<<14);
    sdm_state->ds_x1 += ds_in - (ds_out<<17);

    return ds_out;
}

__attribute__((always_inline))
static inline uint32_t ds_out_to_frac_reg(int32_t ds_out){
    // bit 31 is frac enable
    // bits 15..8 are the f value
    // bits 7..0 are the p value
    // Freq - F + (f + 1)/(p + 1)
    uint32_t frac_val = 0;

    if (ds_out == 0){
        frac_val = 0x00000007; // step 0/8
    }
    else{
        frac_val = ((ds_out - 1) << 8) | 0x80000007; // steps 1/8 to 8/8
    }

    return frac_val;
}

__attribute__((always_inline))
static inline void write_frac_reg(tileref_t this_tile, uint32_t frac_val){
    write_sswitch_reg(this_tile, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, frac_val);
}

void sdm_task(chanend_t c_sdm_control){
    printf("sdm_task\n");

    const uint32_t sdm_interval = 100;

    sdm_state_t sdm_state;
    init_sigma_delta(&sdm_state);

    tileref_t this_tile = get_local_tile_id();

    hwtimer_t tmr = hwtimer_alloc();
    int32_t trigger_time = hwtimer_get_time(tmr) + sdm_interval;
    bool running = true;
    int32_t ds_in = 666666;

    while(running){
        // Poll for new SDM control value
        SELECT_RES(
            CASE_THEN(c_sdm_control, ctrl_update),
            DEFAULT_THEN(default_handler)
        )
        {
            ctrl_update:
            {
                ds_in = chan_in_word(c_sdm_control);
            }
            break;

            default_handler:
            {
                // Do nothing & fall-through
            }
            break;
        }

        // calc new ds_out and then wait to write
        int32_t ds_out = do_sigma_delta(&sdm_state, ds_in);
        uint32_t frac_val = ds_out_to_frac_reg(ds_out);

        hwtimer_wait_until(tmr, trigger_time);
        trigger_time += sdm_interval;
        write_frac_reg(this_tile, frac_val);

        static int cnt = 0;
        if (cnt % 1000000 == 0) printintln(cnt);
        cnt++;
    }
}

void sw_pll_send_ctrl_to_sdm_task(chanend_t c_sdm_control, int32_t dco_ctl){
    chan_out_word(c_sdm_control, dco_ctl);
}

void sw_pll_sdm_test(chanend_t c_sdm_control){

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
    setup_recovered_ref_clock_output(p_recovered_ref_clk, clk_recovered_ref_clk, p_mclk, PLL_RATIO / 2); // TODO fix me /2
    
    sw_pll_state_t sw_pll;
    sw_pll_sdm_init(&sw_pll,
                SW_PLL_15Q16(0.0),
                SW_PLL_15Q16(32.0),
                CONTROL_LOOP_COUNT,
                PLL_RATIO,
                0,
                APP_PLL_CTL_REG,
                APP_PLL_DIV_REG,
                APP_PLL_FRAC_REG,
                PPM_RANGE);

    sw_pll_lock_status_t lock_status = SW_PLL_LOCKED;

    uint32_t max_time = 0;
    while(1)
    {
        port_in(p_ref_clk_count);   // This blocks each time round the loop until it can sample input (rising edges of word clock). So we know the count will be +1 each time.
        uint16_t mclk_pt =  port_get_trigger_time(p_ref_clk);// Get the port timer val from p_ref_clk (which is running from MCLK). So this is basically a 16 bit free running counter running from MCLK.
        
        uint32_t t0 = get_reference_time();
        sw_pll_sdm_do_control(&sw_pll, c_sdm_control, mclk_pt, 0);
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