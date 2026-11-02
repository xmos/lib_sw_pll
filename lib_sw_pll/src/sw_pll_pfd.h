// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <stdint.h>
#include <stddef.h>

#include "sw_pll_common.h"

//TODO delme
#include <stdio.h> //TODO delme

#pragma once

// Fractional bits in the precomputed reciprocal: more bits improve precision
// but leave less headroom in the uint64_t scaling product.
#define SW_PLL_PFD_PRE_DIV_BITS 37

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
 * Populates pfd_state->mclk_diff with the signed, wrap-adjusted difference between the sampled and expected MCLK counts.
 *
 * \param pfd_state             Pointer to the PFD state.
 * \param first_loop            Pointer to the first_loop var used for resetting when out of range.
 * \param mclk_pt               The clock count from the port counter.
 * \param ref_clk_pt            The clock count from the ref clock counter (optional).
 * 
 * 
 */
__attribute__((always_inline))
static inline void sw_pll_calc_error_from_port_timers(  sw_pll_pfd_state_t * const pfd,
                                                        uint8_t *first_loop,
                                                        const uint16_t mclk_pt,
                                                        const uint16_t ref_clk_pt)
{
    uint16_t mclk_expected_pt = 0;
    // A nonzero nominal reference increment enables compensation for sampling jitter.
    if(pfd->ref_clk_expected_inc)
    {
        // Timer positions are modulo 65536; nominal increments retain whole wraps
        // in uint32_t, and only the predicted position is reduced to 16 bits.
        uint16_t ref_clk_expected_pt = (uint16_t)(pfd->ref_clk_pt_last + pfd->ref_clk_expected_inc);
        // uint16_t operands promote to 32-bit int, so subtraction cannot overflow.
        // The target's int16_t conversion keeps the low 16 bits and sign-extends:
        // positive means late, negative means early, even across timer wrap.
        // This conversion is implementation-defined before C23. Timing deviations
        // must be less than half a wrap to be unambiguous; exactly half maps to -32768.
        int16_t ref_clk_diff = (int16_t)(ref_clk_pt - ref_clk_expected_pt);
        pfd->ref_clk_pt_last = ref_clk_pt;

        // Reject nominal increment + deviation < 0 without a signed 64-bit add.
        // Widen before negating so INT16_MIN becomes +32768, then compare unsigned
        // to retain the full uint32_t nominal range. Equality (zero elapsed) is valid.
        if(ref_clk_diff < 0 && pfd->ref_clk_expected_inc < (uint32_t)(-(int32_t)ref_clk_diff))
        {
            // The caller can still consume mclk_diff before reinitializing next time.
            pfd->mclk_diff = 0;
            *first_loop = 1;
            return;
        }

        // Scale the nominal MCLK increment by elapsed_ref / nominal_ref.
        // init computes numerator = floor(2^37 / nominal_ref) + 1; multiplying
        // by it and shifting replaces division with a slightly upward-biased
        // reciprocal approximation. The shift discards fractional count bits.
        // A negative deviation converts modulo 2^64; unsigned addition cancels
        // that wrap and yields the nonnegative elapsed count established above.
        // Keep this sum wide: a positive deviation can take it beyond UINT32_MAX.
        // Both multiplications are uint64_t and must fit for correct scaling;
        // the guard above prevents negative elapsed counts, not product overflow.
        uint32_t mclk_expected_pt_inc = ((uint64_t)pfd->mclk_expected_pt_inc
                                         * ((uint64_t)pfd->ref_clk_expected_inc + (uint64_t)ref_clk_diff)
                                         * pfd->ref_clk_scaling_numerator) >> SW_PLL_PFD_PRE_DIV_BITS;
        // Mathematical alternative (requires sufficiently wide intermediates):
        // uint32_t mclk_expected_pt_inc = pfd->mclk_expected_pt_inc * (pfd->ref_clk_expected_inc + ref_clk_diff) / pfd->ref_clk_expected_inc;
        // Reduce the incremented position modulo 65536 only after scaling.
        mclk_expected_pt = (uint16_t)(pfd->mclk_pt_last + mclk_expected_pt_inc);
    }
    else // we are assuming mclk_pt is sampled precisely and needs no compensation
    {
        mclk_expected_pt = (uint16_t)(pfd->mclk_pt_last + pfd->mclk_expected_pt_inc);
    }

    // The same low-16-bit signed interpretation gives the wrap-aware MCLK error:
    // positive means more MCLK edges than expected, negative means fewer.
    // Only errors smaller than half a wrap have an unambiguous direction.
    pfd->mclk_diff = (int16_t)(mclk_pt - mclk_expected_pt);
    // printf("mclk_diff: %d, expected: %d\n", pfd->mclk_diff, pfd->mclk_expected_pt_inc);

    // int16_t promotes to 32-bit int in MAGNITUDE, so abs(-32768) is safely 32768.
    // Reset only beyond the configured limit; equality is accepted and an already
    // set first_loop flag is never cleared here (e.g. after a reference stop/start).
    if(MAGNITUDE(pfd->mclk_diff) > pfd->mclk_max_diff)
    {
        *first_loop = 1;
    }
}
