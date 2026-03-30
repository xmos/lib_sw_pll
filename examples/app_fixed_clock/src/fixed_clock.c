// Copyright 2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <sw_pll.h>
#include <xcore/hwtimer.h>
#include <print.h>

void fixed_clock(void)
{
    hwtimer_t timer = hwtimer_alloc();
    sw_pll_result_t pll_result;

    // Loop forever, cycling between 24.576 MHz and 0 Hz (disabled)
    while(1)
    {
        // Enable PLL at 24.576 MHz
        pll_result = sw_pll_fixed_clock(24576000, SW_PLL_TILE_1);
        if (pll_result != SW_PLL_SUCCESS)
        {
            printstr("Error: sw_pll_fixed_clock() failed to set 24.576 MHz\r\n");
            return;
        }

        // Wait 5 seconds
        hwtimer_delay(timer, 5 * XS1_TIMER_MHZ * 1000000);

        // Disable PLL (set to 0 Hz)
        pll_result = sw_pll_fixed_clock(0, SW_PLL_TILE_1);
        if (pll_result != SW_PLL_SUCCESS)
        {
            printstr("Error: sw_pll_fixed_clock() failed to disable PLL\r\n");
            return;
        }

        // Wait 5 seconds
        hwtimer_delay(timer, 5 * XS1_TIMER_MHZ * 1000000);
    }
}
