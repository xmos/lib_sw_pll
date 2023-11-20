// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#pragma once

// Helpers used in this module
#define TIMER_TIMEAFTER(A, B) ((int)((B) - (A)) < 0)    // Returns non-zero if A is after B, accounting for wrap
#define PORT_TIMEAFTER(NOW, EVENT_TIME) ((int16_t)((EVENT_TIME) - (NOW)) < 0) // Returns non-zero if A is after B, accounting for wrap
#define MAGNITUDE(A) (A < 0 ? -A : A)                   // Removes the sign of a value


typedef int32_t sw_pll_15q16_t; // Type for 15.16 signed fixed point

#define SW_PLL_NUM_FRAC_BITS 16
#define SW_PLL_15Q16(val) ((sw_pll_15q16_t)((float)val * (1 << SW_PLL_NUM_FRAC_BITS)))
#define SW_PLL_NUM_LUT_ENTRIES(lut_array) (sizeof(lut_array) / sizeof(lut_array[0]))