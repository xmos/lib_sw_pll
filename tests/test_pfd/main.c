// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

/*
 * Range tests for sw_pll_calc_error_from_port_timers, run by pytest in xsim.
 * Compare against an independent wrap-aware oracle with compensation on/off.
 * Sample both 16-bit timer ranges and explicitly check wraparound, signed
 * boundaries, reset thresholds, first_loop preservation and timer history.
 * The sparse stride keeps simulation fast; this is not an exhaustive sweep.
 */

#include "../../lib_sw_pll/src/sw_pll_pfd.h"

// Sample the timer range sparsely for xsim; critical boundaries are checked separately.
#define SAMPLE_STRIDE 256

// Independent wrap-aware oracle, avoiding the DUT's int16_t cast/negation logic.
static int32_t signed_difference(uint16_t actual, uint16_t expected)
{
    int32_t difference = (int32_t)actual - (int32_t)expected;
    if(difference > INT16_MAX)
        difference -= 65536;
    if(difference < INT16_MIN)
        difference += 65536;
    return difference;
}

static int check_sample(uint16_t origin, uint16_t mclk_pt, uint16_t ref_clk_pt,
                        int compensated, uint16_t limit, uint8_t initial_first_loop)
{
    sw_pll_pfd_state_t pfd = {0};
    pfd.mclk_pt_last = origin;
    pfd.mclk_expected_pt_inc = 32768;
    pfd.ref_clk_pt_last = origin;
    pfd.ref_clk_expected_inc = compensated ? 32768 : 0;
    // Equal nominal increments give an exact 1:1 ratio, with no scaling-rounding error.
    pfd.ref_clk_scaling_numerator = (uint64_t)1 << (SW_PLL_PFD_PRE_DIV_BITS - 15);
    pfd.mclk_max_diff = limit;

    // Compensation makes the expected MCLK increment track the reference elapsed count.
    uint32_t expected_increment = 32768;
    if(compensated)
    {
        uint16_t ref_expected = (uint16_t)((uint32_t)origin + 32768);
        expected_increment = 32768 + signed_difference(ref_clk_pt, ref_expected);
    }
    uint16_t expected_pt = (uint16_t)((uint32_t)origin + expected_increment);
    int32_t expected_error = signed_difference(mclk_pt, expected_pt);
    int32_t magnitude = expected_error < 0 ? -expected_error : expected_error;
    // Equality must not trigger reset, and an existing first_loop flag must stay set.
    uint8_t expected_first_loop = magnitude > limit ? 1 : initial_first_loop;
    uint8_t first_loop = initial_first_loop;

    sw_pll_calc_error_from_port_timers(&pfd, &first_loop, mclk_pt, ref_clk_pt);

    // Check error/reset outputs and that only the compensated path updates the reference history.
    if(pfd.mclk_diff != expected_error || first_loop != expected_first_loop ||
       pfd.ref_clk_pt_last != (compensated ? ref_clk_pt : origin) ||
       pfd.mclk_pt_last != origin || pfd.mclk_expected_pt_inc != 32768)
    {
        printf("FAIL: origin=%u mclk=%u ref=%u compensated=%d limit=%u "
               "initial_first_loop=%u error=%d expected=%ld first_loop=%u expected=%u\n",
               (unsigned)origin, (unsigned)mclk_pt, (unsigned)ref_clk_pt,
               compensated, (unsigned)limit, (unsigned)initial_first_loop,
               (int)pfd.mclk_diff, (long)expected_error,
               (unsigned)first_loop, (unsigned)expected_first_loop);
        return 1;
    }
    return 0;
}

int main(void)
{
    // Move the timer origins across zero, the half-range boundary and the wrap boundary.
    const uint16_t origins[] = {0, 32768, UINT16_MAX};
    // Include limits that accept INT16_MIN's magnitude (32768) without resetting.
    const uint16_t limits[] = {0, 1, 123, INT16_MAX, 32768, UINT16_MAX};
    const uint16_t boundary_samples[] = {0, 1, 32767, 32768, 32769, 65534, UINT16_MAX};
    // Signed extremes, zero, and errors at/just outside the representative limit of 123.
    const int32_t errors[] = {INT16_MIN, -32767, -124, -123, -1,
                             0, 1, 123, 124, INT16_MAX};

    for(size_t origin_index = 0; origin_index < sizeof(origins) / sizeof(origins[0]); ++origin_index)
    {
        uint16_t origin = origins[origin_index];
        printf("Testing origin: %u\n", (unsigned)origin);
        uint16_t nominal_pt = (uint16_t)((uint32_t)origin + 32768);
        for(int compensated = 0; compensated <= 1; ++compensated)
        {
            // Sweep MCLK with an on-time reference, exercising both compensation modes.
            for(uint32_t sample = 0; sample <= UINT16_MAX; sample += SAMPLE_STRIDE)
            {
                if(check_sample(origin, (uint16_t)sample, nominal_pt, compensated, 123, 0))
                    return 1;
            }
                    // Explicitly cover timer endpoints and half-range neighbors skipped by the stride.
            for(size_t sample_index = 0; sample_index < sizeof(boundary_samples) / sizeof(boundary_samples[0]); ++sample_index)
            {
                if(check_sample(origin, boundary_samples[sample_index], nominal_pt, compensated, 123, 0))
                    return 1;
            }
                    // Check reset thresholds for both error signs and both initial first_loop states.
            for(size_t limit_index = 0; limit_index < sizeof(limits) / sizeof(limits[0]); ++limit_index)
            {
                for(size_t error_index = 0; error_index < sizeof(errors) / sizeof(errors[0]); ++error_index)
                {
                    uint16_t mclk_pt = (uint16_t)((int32_t)nominal_pt + errors[error_index]);
                    for(uint8_t first_loop = 0; first_loop <= 1; ++first_loop)
                    {
                        if(check_sample(origin, mclk_pt, nominal_pt, compensated,
                                        limits[limit_index], first_loop))
                            return 1;
                    }
                }
            }
        }
        // Hold MCLK fixed and vary reference timing to isolate the compensation calculation.
        for(uint32_t sample = 0; sample <= UINT16_MAX; sample += SAMPLE_STRIDE)
        {
            if(check_sample(origin, nominal_pt, (uint16_t)sample, 1, 123, 0))
                return 1;
        }
            // Retain exact reference timer wrap/half-range boundary coverage despite sparse sampling.
        for(size_t sample_index = 0; sample_index < sizeof(boundary_samples) / sizeof(boundary_samples[0]); ++sample_index)
        {
            if(check_sample(origin, nominal_pt, boundary_samples[sample_index], 1, 123, 0))
                return 1;
        }
            // Probe reference deviations at signed extremes and around the reset limit.
        for(size_t error_index = 0; error_index < sizeof(errors) / sizeof(errors[0]); ++error_index)
        {
            uint16_t ref_clk_pt = (uint16_t)((int32_t)nominal_pt + errors[error_index]);
            if(check_sample(origin, nominal_pt, ref_clk_pt, 1, 123, 0))
                return 1;
        }
    }

    puts("PASS: PFD timer ranges, wraparound and reset boundaries");
    return 0;
}