// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

/*
 * Range tests for sw_pll_calc_error_from_port_timers, run by pytest in xsim.
 * Compare against an independent wrap-aware oracle with compensation on/off.
 * Sample both 16-bit timer ranges and explicitly check wraparound, signed
 * boundaries, reset thresholds, first_loop preservation and timer history.
 * Check small expected increments and fractional scaling, requiring negative
 * elapsed reference counts to request reset and clear the error.
 * The sparse stride keeps simulation fast; this is not an exhaustive sweep.
 */

#include "../../lib_sw_pll/src/sw_pll_pfd.h"
#include <limits.h>
#include <string.h>

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

static int check_elapsed_sample(uint16_t origin, uint32_t ref_increment,
                                uint32_t mclk_increment, int16_t ref_deviation,
                                uint8_t initial_first_loop, int32_t mclk_error)
{
    sw_pll_pfd_state_t pfd = {0};
    pfd.mclk_diff = 1234;
    pfd.mclk_pt_last = origin;
    pfd.ref_clk_pt_last = origin;
    pfd.ref_clk_expected_inc = ref_increment;
    pfd.mclk_expected_pt_inc = mclk_increment;
    pfd.ref_clk_scaling_numerator = ((uint64_t)1 << SW_PLL_PFD_PRE_DIV_BITS) / ref_increment + 1;
    // Disable MCLK-error resets so they cannot mask a missing negative-elapsed guard.
    pfd.mclk_max_diff = UINT16_MAX;

    uint16_t ref_expected = (uint16_t)((uint32_t)origin + ref_increment);
    uint16_t ref_clk_pt = (uint16_t)((int32_t)ref_expected + ref_deviation);
    int64_t elapsed = (int64_t)ref_increment + ref_deviation;
    int32_t expected_error = elapsed < 0 ? 0 : mclk_error;
    uint8_t expected_first_loop = elapsed < 0 ? 1 : initial_first_loop;

    // For these small vectors, reciprocal rounding must match exact integer division.
    uint32_t expected_increment = elapsed < 0 ? 0 :
        (uint32_t)((uint64_t)mclk_increment * (uint64_t)elapsed / ref_increment);
    uint16_t mclk_pt = (uint16_t)((int64_t)origin + expected_increment + mclk_error);
    uint8_t first_loop = initial_first_loop;

    sw_pll_calc_error_from_port_timers(&pfd, &first_loop, mclk_pt, ref_clk_pt);

    if(pfd.mclk_diff != expected_error || first_loop != expected_first_loop ||
       pfd.ref_clk_pt_last != ref_clk_pt || pfd.mclk_pt_last != origin ||
       pfd.ref_clk_expected_inc != ref_increment ||
       pfd.mclk_expected_pt_inc != mclk_increment)
    {
        printf("FAIL: origin=%u ref_inc=%lu mclk_inc=%lu deviation=%d "
               "elapsed=%ld initial_first_loop=%u error=%d expected=%ld "
               "first_loop=%u expected=%u\n",
               (unsigned)origin, (unsigned long)ref_increment,
               (unsigned long)mclk_increment, (int)ref_deviation, (long)elapsed,
               (unsigned)initial_first_loop, (int)pfd.mclk_diff,
               (long)expected_error, (unsigned)first_loop, (unsigned)expected_first_loop);
        return 1;
    }
    return 0;
}

static int check_init(void)
{
    const struct {
        size_t loop_count;
        size_t ratio;
        uint32_t ref_increment;
        unsigned ppm;
        uint32_t expected_mclk;
        uint32_t expected_ref;
        uint16_t expected_limit;
    } cases[] = {
        {512, 256, 0, 10000, 131072, 0, 2621},
        {512, 256, 100, 10000, 131072, 51200, 2621},
        {1, 500000, 0, 32767, 500000, 0, INT16_MAX},
        {1, UINT32_MAX, 0, 0, UINT32_MAX, 0, 0},
        {1, 1, UINT32_MAX, 0, 1, UINT32_MAX, 0},
    };

    for(size_t case_index = 0; case_index < sizeof(cases) / sizeof(cases[0]); ++case_index)
    {
        sw_pll_pfd_state_t pfd;
        memset(&pfd, 0xff, sizeof(pfd));
        sw_pll_pfd_init(&pfd, cases[case_index].loop_count, cases[case_index].ratio,
                        cases[case_index].ref_increment, cases[case_index].ppm);
        uint64_t expected_scaling = cases[case_index].expected_ref == 0 ? 0 :
            ((uint64_t)1 << SW_PLL_PFD_PRE_DIV_BITS) / cases[case_index].expected_ref + 1;
        if(pfd.mclk_expected_pt_inc != cases[case_index].expected_mclk ||
           pfd.ref_clk_expected_inc != cases[case_index].expected_ref ||
           pfd.mclk_max_diff != cases[case_index].expected_limit ||
           pfd.ref_clk_scaling_numerator != expected_scaling ||
           pfd.mclk_diff != 0 || pfd.mclk_pt_last != 0 || pfd.ref_clk_pt_last != 0)
        {
            printf("FAIL: PFD initialization case %u\n", (unsigned)case_index);
            return 1;
        }
    }
    return 0;
}

static int check_invalid_init(const char *name)
{
    const struct {
        const char *name;
        size_t loop_count;
        size_t ratio;
        uint32_t ref_increment;
        unsigned ppm;
    } cases[] = {
        {"zero-loop", 0, 256, 0, 1000},
        {"zero-ratio", 512, 0, 0, 1000},
        {"mclk-overflow", 65536, 65536, 0, 0},
        {"ref-overflow", 2, 1, UINT32_MAX, 0},
        {"threshold-half-range", 1, 500000, 0, 32768},
        {"threshold-truncation", 512, 256, 0, 250000},
        {"threshold-product-overflow", 1, UINT32_MAX, 0, UINT_MAX},
    };

    for(size_t case_index = 0; case_index < sizeof(cases) / sizeof(cases[0]); ++case_index)
    {
        if(strcmp(name, cases[case_index].name) == 0)
        {
            sw_pll_pfd_state_t pfd = {0};
            printf("Testing invalid init: %s\n", name);
            fflush(stdout);
            sw_pll_pfd_init(&pfd, cases[case_index].loop_count, cases[case_index].ratio,
                            cases[case_index].ref_increment, cases[case_index].ppm);
            puts("FAIL: invalid PFD initialization was accepted");
            return 1;
        }
    }
    puts("FAIL: unknown PFD initialization case");
    return 1;
}

int main(int argc, char **argv)
{
    if(argc == 2)
        return check_invalid_init(argv[1]);
    if(argc != 1 || check_init())
        return 1;

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

        // Exercise other increments and non-unity scaling without expanding the range sweeps.
        const uint32_t ref_increments[] = {100, 100, 256};
        const uint32_t mclk_increments[] = {100, 150, 384};
        for(size_t config_index = 0; config_index < sizeof(ref_increments) / sizeof(ref_increments[0]); ++config_index)
        {
            int32_t ref_increment = (int32_t)ref_increments[config_index];
            // Around zero elapsed time, negative deviations can be valid or invalid.
            const int16_t deviations[] = {INT16_MIN, -ref_increment - 1,
                                         -ref_increment, -ref_increment + 1,
                                         -1, 0, 1, INT16_MAX};
            for(size_t deviation_index = 0; deviation_index < sizeof(deviations) / sizeof(deviations[0]); ++deviation_index)
            {
                for(uint8_t first_loop = 0; first_loop <= 1; ++first_loop)
                {
                    // Check both an exact MCLK match and a nonzero residual error.
                    for(int32_t mclk_error = 0; mclk_error <= 7; mclk_error += 7)
                    {
                        if(check_elapsed_sample(origin, ref_increments[config_index],
                                                mclk_increments[config_index],
                                                deviations[deviation_index], first_loop, mclk_error))
                            return 1;
                    }
                }
            }
        }
    }

    puts("PASS: PFD timer ranges, wraparound and reset boundaries");
    return 0;
}