// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

#pragma once

#define SW_PLL_SDM_UPPER_LIMIT    980000
#define SW_PLL_SDM_LOWER_LIMIT    60000

typedef int tileref_t;

/**
 * \addtogroup sw_pll_sdm sw_pll_sdm
 *
 * The public API for using the Software PLL.
 * @{
 */

/**
 * low level sw_pll_do_sigma_delta function that turns a control signal
 * into a Sigma Delta Modulated output signal.
 *
 *
 * \param sdm_state     Pointer to the SDM state.
 * \param sdm_in        32b signed input error value. Note limited range.
 *                      See SW_PLL_SDM_UPPER_LIMIT and SW_PLL_SDM_LOWER_LIMIT.
 * \returns             Sigma Delta modulated signal.
 */
__attribute__((always_inline))
static inline int32_t sw_pll_do_sigma_delta(sw_pll_sdm_state_t *sdm_state, int32_t sdm_in){
    // Third order, 9 level output delta sigma. 20 bit unsigned input.
    int32_t sdm_out = ((sdm_state->ds_x3<<4) + (sdm_state->ds_x3<<1)) >> 13;
    if (sdm_out > 8){
        sdm_out = 8;
    }
    if (sdm_out < 0){
        sdm_out = 0;
    }
    sdm_state->ds_x3 += (sdm_state->ds_x2>>5) - (sdm_out<<9) - (sdm_out<<8);
    sdm_state->ds_x2 += (sdm_state->ds_x1>>5) - (sdm_out<<14);
    sdm_state->ds_x1 += sdm_in - (sdm_out<<17);

    return sdm_out;
}

/**
 * low level sw_pll_sdm sw_pll_sdm_out_to_frac_reg function that turns
 * a sigma delta output signal into a PLL fractional register setting.
 * 
 * \param sdm_out   32b signed input value.
 * \returns         Fractional register value.
 */
__attribute__((always_inline))
static inline uint32_t sw_pll_sdm_out_to_frac_reg(int32_t sdm_out){
    // bit 31 is frac enable
    // bits 15..8 are the f value
    // bits 7..0 are the p value
    // Freq - F + (f + 1)/(p + 1)
    uint32_t frac_val = 0;

    if (sdm_out == 0){
        frac_val = 0x00000007; // step 0/8
    }
    else{
        frac_val = ((sdm_out - 1) << 8) | 0x80000007; // steps 1/8 to 8/8
    }

    return frac_val;
}

/**
 * low level sw_pll_write_frac_reg function that writes the PLL fractional
 * register.
 * 
 * NOTE:    attempting to write the PLL fractional register from more than
 *          one logical core at the same time may result in channel lock-up.
 *          Please ensure the that PLL initiaisation has completed before
 *          the SDM task writes to the register. The provided example
 *          implements a method for doing this.
 *
 * \param this_tile    The ID of the xcore tile that is doing the write.
 * \param frac_val     16b signed input error value
 */
__attribute__((always_inline))
static inline void sw_pll_write_frac_reg(tileref_t this_tile, uint32_t frac_val){
    write_sswitch_reg(this_tile, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, frac_val);
}

/**@}*/ // END: addtogroup sw_pll_sdm


extern void sw_pll_app_pll_init(const unsigned tileid,
                                const uint32_t app_pll_ctl_reg_val,
                                const uint32_t app_pll_div_reg_val,
                                const uint16_t frac_val_nominal);
