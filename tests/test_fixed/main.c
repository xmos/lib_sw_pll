// Copyright 2023-2025 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.
///
/// Application to call different fixed frequencies to ensure they work.
/// Also checks freq=0 to test this is reliable.
///
/// This app is designed to be run standalone on HW and is not part of the regression
///
///
#include "xs1.h"
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <sw_pll.h>
#include <stdint.h>
#include <xcore/hwtimer.h>

int main(void) {
     hwtimer_t timer = hwtimer_alloc();

    for(int i = 0; i < 100000; i++){
        // printf("on\n");
        sw_pll_fixed_clock(44100*512);
        hwtimer_delay(timer, 1000);
        // printf("off\n");
        sw_pll_fixed_clock(0);
        sw_pll_fixed_clock(0); // Do twice to make sure it responds even if off
        hwtimer_delay(timer, XS1_TIMER_KHZ);
    }
}
