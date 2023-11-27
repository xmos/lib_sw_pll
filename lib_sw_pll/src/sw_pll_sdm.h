// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

#pragma once

#define SW_PLL_SDM_UPPER_LIMIT    980000
#define SW_PLL_SDM_LOWER_LIMIT    60000

typedef int tileref_t;


__attribute__((always_inline))
static inline int32_t do_sigma_delta(sw_pll_sdm_state_t *sdm_state, int32_t ds_in){
    // Third order, 9 level output delta sigma. 20 bit unsigned input.
    int32_t ds_out = ((sdm_state->ds_x3<<4) + (sdm_state->ds_x3<<1)) >> 13;
    if (ds_out > 8){
        ds_out = 8;
    }
    if (ds_out < 0){
        ds_out = 0;
    }
    sdm_state->ds_x3 += (sdm_state->ds_x2>>5) - (ds_out<<9) - (ds_out<<8);
    sdm_state->ds_x2 += (sdm_state->ds_x1>>5) - (ds_out<<14);
    sdm_state->ds_x1 += ds_in - (ds_out<<17);

    return ds_out;
}

__attribute__((always_inline))
static inline uint32_t ds_out_to_frac_reg(int32_t ds_out){
    // bit 31 is frac enable
    // bits 15..8 are the f value
    // bits 7..0 are the p value
    // Freq - F + (f + 1)/(p + 1)
    uint32_t frac_val = 0;

    if (ds_out == 0){
        frac_val = 0x00000007; // step 0/8
    }
    else{
        frac_val = ((ds_out - 1) << 8) | 0x80000007; // steps 1/8 to 8/8
    }

    return frac_val;
}

__attribute__((always_inline))
static inline void write_frac_reg(tileref_t this_tile, uint32_t frac_val){
    write_sswitch_reg(this_tile, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, frac_val);
}

extern void sw_pll_app_pll_init(const unsigned tileid,
                                const uint32_t app_pll_ctl_reg_val,
                                const uint32_t app_pll_div_reg_val,
                                const uint16_t frac_val_nominal);
