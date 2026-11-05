// Copyright 2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

// Build-only API coverage for vx4 (clang): retain references to public functions without running PLL hardware setup.
#include <stdint.h>

#include "sw_pll.h"

static void call_sw_pll_api(void)
{
    static const int16_t lut_table[] = {0, 0};
    sw_pll_state_t state = {0};

    sw_pll_lut_reset(&state, 0, 0, 0, 2);
    sw_pll_reset_pi_state(&state);
    (void)sw_pll_lut_init(&state, 0, 0, 0, 1, 1, 0, lut_table, 2, 0, 0, 0, 0, SW_PLL_TILE_BOTH);
    (void)sw_pll_lut_do_control(&state, 0, 0);
    (void)sw_pll_lut_do_control_from_error(&state, 0);

    (void)sw_pll_sdm_init(&state, 0, 0, 0, 1, 1, 0, 0, 0, 0, 500000, 0, SW_PLL_TILE_BOTH);
    (void)sw_pll_sdm_do_control(&state, 0, 0);
    (void)sw_pll_sdm_do_control_from_error(&state, 0);
    sw_pll_init_sigma_delta(&state.sdm_state);
    sw_pll_do_sigma_delta(&state.sdm_state, (tileref_t)get_local_tile_id(), 0);

    (void)sw_pll_mash_init(&state, 0, 0, 0, 1, 1, 0, 0, 0, 0x80000, 0, SW_PLL_TILE_BOTH);
    (void)sw_pll_mash_do_control(&state, 0, 0);
    (void)sw_pll_mash_do_control_from_error(&state, 0);

    (void)sw_pll_app_pll_init(get_local_tile_id(), 0, 0, 0, SW_PLL_TILE_BOTH);
    (void)sw_pll_app_pll_mash_init(get_local_tile_id(), 0, 0, 0x80000, SW_PLL_TILE_BOTH);
    (void)sw_pll_fixed_clock(0, SW_PLL_TILE_BOTH);
}

int main(void)
{
    call_sw_pll_api();
    return 0;
}