// Copyright 2023-2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <stdint.h>
#include <stddef.h>

#include "sw_pll_common.h"

#pragma once

#define SW_PLL_PFD_PRE_DIV_BITS 37 // Used pre-computing a divide to save on runtime div usage. Tradeoff between precision and max 

/**
 * Initialises the Phase Frequency Detector.
 *
 * Sets how often the PFD and control loop runs and error limits for resetting
 * 
 * \param pfd_state             Pointer to the struct to be initialised.
 * \param loop_rate_count       How many counts of the call to sw_pll_lut_do_control before control is done.
 *                              Note this is only used by sw_pll_lut_do_control. sw_pll_lut_do_control_from_error
 *                              calls the control loop every time so this is ignored.
 * \param pll_ratio             Integer ratio between input reference clock and the PLL output.
 *                              Only used by sw_pll_lut_do_control for the PFD. Don't care otherwise.
 *                              Used to calculate the expected port timer increment when control is called.
 * \param ref_clk_expected_inc  Expected ref clock increment each time sw_pll_lut_do_control is called.
 *                              Pass in zero if you are sure the mclk sampling timing is precise. This
 *                              will disable the scaling of the mclk count inside sw_pll_lut_do_control.
 *                              Only used by sw_pll_lut_do_control. Don't care otherwise.
 * \param ppm_range             The pre-calculated PPM range. Used to determine the maximum deviation
 *                              of counted mclk before the PLL resets its state.
 *                              Note this is only used by sw_pll_lut_do_control. sw_pll_lut_do_control_from_error
 *                              calls the control loop every time so this is ignored.
 */ 
void sw_pll_pfd_init(sw_pll_pfd_state_t *pfd_state,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const unsigned ppm_range);

/**
 * Helper to perform the maths needed on the port count, accounting for wrapping, to determine the frequency difference.
 *
 * \param pfd_state             Pointer to the PFD state.
 * \param first_loop            Pointer to the first_loop var used for resetting when out of range.
 * \param mclk_pt               The clock count from the port counter.
 * \param ref_clk_pt            The clock count from the ref clock counter (optional).
 */ 
__attribute__((always_inline))
static inline void sw_pll_calc_error_from_port_timers(  sw_pll_pfd_state_t * const pfd,
                                                        uint8_t *first_loop,
                                                        const uint16_t mclk_pt,
                                                        const uint16_t ref_clk_pt)
{
    uint16_t mclk_expected_pt = 0;
    // See if we are using variable loop period sampling, if so, compensate for it by scaling the expected mclk count
    if(pfd->ref_clk_expected_inc)
    {
        uint16_t ref_clk_expected_pt = pfd->ref_clk_pt_last + pfd->ref_clk_expected_inc;
        // This uses casting trickery to work out the difference between the timer values accounting for wrap at 65536
        int16_t ref_clk_diff = PORT_TIMEAFTER(ref_clk_pt, ref_clk_expected_pt) ? -(int16_t)(ref_clk_expected_pt - ref_clk_pt) : (int16_t)(ref_clk_pt - ref_clk_expected_pt);
        pfd->ref_clk_pt_last = ref_clk_pt;

        // This allows for wrapping of the timer when CONTROL_LOOP_COUNT is high
        // Note we use a pre-computed divide followed by a shift to replace a constant divide with a constant multiply + shift
        uint32_t mclk_expected_pt_inc = ((uint64_t)pfd->mclk_expected_pt_inc
                                         * ((uint64_t)pfd->ref_clk_expected_inc + ref_clk_diff) 
                                         * pfd->ref_clk_scaling_numerator) >> SW_PLL_PFD_PRE_DIV_BITS;
        // Below is the line we would use if we do not pre-compute the divide. This can take a long time if we spill over 32b
        // uint32_t mclk_expected_pt_inc = pfd->mclk_expected_pt_inc * (pfd->ref_clk_expected_inc + ref_clk_diff) / pfd->ref_clk_expected_inc;
        mclk_expected_pt = pfd->mclk_pt_last + mclk_expected_pt_inc;
    }
    else // we are assuming mclk_pt is sampled precisely and needs no compoensation
    {
        mclk_expected_pt = pfd->mclk_pt_last + pfd->mclk_expected_pt_inc;
    }

    // This uses casting trickery to work out the difference between the timer values accounting for wrap at 65536
    pfd->mclk_diff = PORT_TIMEAFTER(mclk_pt, mclk_expected_pt) ? -(int16_t)(mclk_expected_pt - mclk_pt) : (int16_t)(mclk_pt - mclk_expected_pt);

    // Check to see if something has gone very wrong, for example ref clock stop/start. If so, reset state and keep trying
    if(MAGNITUDE(pfd->mclk_diff) > pfd->mclk_max_diff)
    {
        *first_loop = 1;
    }
}
