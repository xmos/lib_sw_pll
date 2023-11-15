// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

__attribute__((always_inline))
static inline void sw_pll_calc_error_from_port_timers(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_clk_pt)
{
    uint16_t mclk_expected_pt = 0;
    // See if we are using variable loop period sampling, if so, compensate for it by scaling the expected mclk count
    if(sw_pll->ref_clk_expected_inc)
    {
        uint16_t ref_clk_expected_pt = sw_pll->ref_clk_pt_last + sw_pll->ref_clk_expected_inc;
        // This uses casting trickery to work out the difference between the timer values accounting for wrap at 65536
        int16_t ref_clk_diff = PORT_TIMEAFTER(ref_clk_pt, ref_clk_expected_pt) ? -(int16_t)(ref_clk_expected_pt - ref_clk_pt) : (int16_t)(ref_clk_pt - ref_clk_expected_pt);
        sw_pll->ref_clk_pt_last = ref_clk_pt;

        // This allows for wrapping of the timer when CONTROL_LOOP_COUNT is high
        // Note we use a pre-computed divide followed by a shift to replace a constant divide with a constant multiply + shift
        uint32_t mclk_expected_pt_inc = ((uint64_t)sw_pll->mclk_expected_pt_inc
                                         * ((uint64_t)sw_pll->ref_clk_expected_inc + ref_clk_diff) 
                                         * sw_pll->ref_clk_scaling_numerator) >> SW_PLL_PRE_DIV_BITS;
        // Below is the line we would use if we do not pre-compute the divide. This can take a long time if we spill over 32b
        // uint32_t mclk_expected_pt_inc = sw_pll->mclk_expected_pt_inc * (sw_pll->ref_clk_expected_inc + ref_clk_diff) / sw_pll->ref_clk_expected_inc;
        mclk_expected_pt = sw_pll->mclk_pt_last + mclk_expected_pt_inc;
    }
    else // we are assuming mclk_pt is sampled precisely and needs no compoensation
    {
        mclk_expected_pt = sw_pll->mclk_pt_last + sw_pll->mclk_expected_pt_inc;
    }

    // This uses casting trickery to work out the difference between the timer values accounting for wrap at 65536
    sw_pll->mclk_diff = PORT_TIMEAFTER(mclk_pt, mclk_expected_pt) ? -(int16_t)(mclk_expected_pt - mclk_pt) : (int16_t)(mclk_pt - mclk_expected_pt);

    // Check to see if something has gone very wrong, for example ref clock stop/start. If so, reset state and keep trying
    if(MAGNITUDE(sw_pll->mclk_diff) > sw_pll->mclk_max_diff)
    {
        sw_pll->first_loop = 1;
    }
}