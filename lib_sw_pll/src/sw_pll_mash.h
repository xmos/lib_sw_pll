// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

#pragma once

// Round inward so the 20-bit fraction stays within 0.1 through 0.9.
#define SW_PLL_MASH_UPPER_LIMIT   0xE6666 // floor(0.9 * 2^20)
#define SW_PLL_MASH_LOWER_LIMIT   0x1999A // ceil(0.1 * 2^20)
