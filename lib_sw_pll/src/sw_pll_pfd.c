// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#ifndef __XS2A__

#include <xcore/assert.h>
#include <stdint.h>
#include "sw_pll_pfd.h"

void sw_pll_pfd_init(sw_pll_pfd_state_t *pfd_state,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const unsigned ppm_range)
{
    xassert(loop_rate_count > 0);
    xassert(pll_ratio > 0);
    xassert(loop_rate_count <= UINT32_MAX / pll_ratio);
    xassert(ref_clk_expected_inc == 0 || loop_rate_count <= UINT32_MAX / ref_clk_expected_inc);

    const uint32_t mclk_expected_pt_inc = (uint32_t)((uint64_t)loop_rate_count * (uint64_t)pll_ratio);
    const uint64_t ppm_multiplier = (uint64_t)ppm_range * 2ULL;
    xassert(ppm_multiplier <= UINT64_MAX / mclk_expected_pt_inc);
    const uint64_t mclk_max_diff = ppm_multiplier * (uint64_t)mclk_expected_pt_inc / 1000000ULL;
    xassert(mclk_max_diff <= INT16_MAX);

    pfd_state->mclk_diff = 0;
    pfd_state->ref_clk_pt_last = 0;
    pfd_state->ref_clk_expected_inc = (uint32_t)((uint64_t)ref_clk_expected_inc * (uint64_t)loop_rate_count);
    pfd_state->ref_clk_scaling_numerator = 0;
    if(pfd_state->ref_clk_expected_inc) // Avoid div 0 error if ref_clk compensation not used
    {
        pfd_state->ref_clk_scaling_numerator = (1ULL << SW_PLL_PFD_PRE_DIV_BITS) / pfd_state->ref_clk_expected_inc + 1; //+1 helps with rounding accuracy
    }
    pfd_state->mclk_pt_last = 0;
    pfd_state->mclk_expected_pt_inc = mclk_expected_pt_inc;
    // Set max PPM deviation before we chose to reset the PLL state. Nominally twice the normal range.
    pfd_state->mclk_max_diff = (uint16_t)mclk_max_diff;
    // Check we can actually support the numbers used in the maths we use
    const float calc_max = (float)UINT64_MAX / 1.1f; // Add 10% headroom from ULL MAX
    const float max = (float)pfd_state->ref_clk_expected_inc
                    * (float)pfd_state->ref_clk_scaling_numerator
                    * (float)pfd_state->mclk_expected_pt_inc;
    // If you have hit this assert then you need to reduce loop_rate_count or possibly the PLL ratio and or MCLK frequency
    xassert(max < calc_max);
}

#endif // ifndef __XS2A__
