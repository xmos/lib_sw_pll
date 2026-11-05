// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <xs1.h>
#include <stdio.h>
#include <xcore/hwtimer.h>
#include <xcore/port.h>
#include <platform.h>

#include "sw_pll_common.h"
#include "clock_gen.h"

#define LOOP_FOREVER    1 // If non-zero, will ramp up and down forever, otherwise will sweep up/down once

static inline void do_clocks(unsigned clock_rate,
                             hwtimer_t period_tmr,
                             unsigned *period_trig,
                             hwtimer_t clock_tmr,
                             unsigned *time_trig,
                             port_t p_clock_gen,
                             unsigned *port_val)
{
    printf("Ref Hz: %d\n", clock_rate >> 1);

    unsigned cycle_ticks_int = XS1_TIMER_HZ / clock_rate;
    unsigned cycle_ticks_remaidner = XS1_TIMER_HZ % clock_rate;
    unsigned carry = 0;

    *period_trig += XS1_TIMER_HZ;
    unsigned time_now = hwtimer_get_time(period_tmr);
    while(TIMER_TIMEAFTER(*period_trig, time_now))
    {
        port_out(p_clock_gen, *port_val);
        hwtimer_wait_until(clock_tmr, *time_trig);
        *time_trig += cycle_ticks_int;
        carry += cycle_ticks_remaidner;
        if(carry >= clock_rate)
        {
            (*time_trig)++;
            carry -= clock_rate;
        }
        *port_val ^= 1;
        time_now = hwtimer_get_time(period_tmr);
    }
}

void clock_gen(unsigned ref_frequency, unsigned ppm_range, port_t p_clock_gen) // Step from - to + this
{
    unsigned clock_rate = ref_frequency * 2; // Note double because we generate edges at this rate

    unsigned clock_rate_low = (unsigned)(clock_rate * (1.0 - (float)ppm_range / 1000000.0));
    unsigned clock_rate_high = (unsigned)(clock_rate * (1.0 + (float)ppm_range / 1000000.0));
    unsigned step_size = (clock_rate_high - clock_rate_low) / 20;
    if(step_size == 0){
        step_size = 1;
    }

    printf("Sweep range: %d %d %d, step size: %d\n", clock_rate_low / 2, clock_rate / 2, clock_rate_high / 2, step_size);

    hwtimer_t period_tmr = hwtimer_alloc();
    unsigned period_trig = hwtimer_get_time(period_tmr);

    hwtimer_t clock_tmr = hwtimer_alloc();
    unsigned time_trig = hwtimer_get_time(clock_tmr);

    port_enable(p_clock_gen);
    unsigned port_val = 1;

    do {
        for(unsigned clock_rate = clock_rate_low; clock_rate <= clock_rate_high; clock_rate += 2 * step_size){
            do_clocks(clock_rate, period_tmr, &period_trig, clock_tmr, &time_trig, p_clock_gen, &port_val);
        }
        for(unsigned clock_rate = clock_rate_high; clock_rate > clock_rate_low; clock_rate -= 2 * step_size){
            do_clocks(clock_rate, period_tmr, &period_trig, clock_tmr, &time_trig, p_clock_gen, &port_val);
        }
    } while(LOOP_FOREVER);
}

void clock_gen_on_i2s_bclk(unsigned ref_frequency, unsigned ppm_range)
{
    clock_gen(ref_frequency, ppm_range, PORT_I2S_BCLK);
}