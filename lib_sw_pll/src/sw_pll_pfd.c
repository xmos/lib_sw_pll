// Copyright 2023-2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#ifdef __XS3A__

#include <xcore/assert.h>
#include "sw_pll_pfd.h"

void sw_pll_pfd_init(sw_pll_pfd_state_t *pfd_state,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const unsigned ppm_range)
{
    pfd_state->mclk_diff = 0;
    pfd_state->ref_clk_pt_last = 0;
    pfd_state->ref_clk_expected_inc = ref_clk_expected_inc * loop_rate_count;
    if(pfd_state->ref_clk_expected_inc) // Avoid div 0 error if ref_clk compensation not used
    {
        pfd_state->ref_clk_scaling_numerator = (1ULL << SW_PLL_PFD_PRE_DIV_BITS) / pfd_state->ref_clk_expected_inc + 1; //+1 helps with rounding accuracy
    }
    pfd_state->mclk_pt_last = 0;
    pfd_state->mclk_expected_pt_inc = loop_rate_count * pll_ratio;
    // Set max PPM deviation before we chose to reset the PLL state. Nominally twice the normal range.
    pfd_state->mclk_max_diff = (uint64_t)(((uint64_t)ppm_range * 2ULL * (uint64_t)pll_ratio * (uint64_t)loop_rate_count) / 1000000); 
    // Check we can actually support the numbers used in the maths we use
    const float calc_max = (float)0xffffffffffffffffULL / 1.1; // Add 10% headroom from ULL MAX
    const float max = (float)pfd_state->ref_clk_expected_inc 
                    * (float)pfd_state->ref_clk_scaling_numerator 
                    * (float)pfd_state->mclk_expected_pt_inc;
    // If you have hit this assert then you need to reduce loop_rate_count or possibly the PLL ratio and or MCLK frequency
    xassert(max < calc_max);
}

#endif // __XS3A__
