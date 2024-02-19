// Copyright 2023-2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

#pragma once

#define SW_PLL_SDM_UPPER_LIMIT    980000
#define SW_PLL_SDM_LOWER_LIMIT    60000

typedef int tileref_t;



/**
 * sw_pll_sdm_controller_init initialisation function.
 *
 * This sets up the PI controller and post processing for the SDM sw_pll. It is provided to allow
 * cases where the PI controller may be separated from the SDM on a different tile and so we want
 * to init the SDM without the sigma delta modulator code and physical writes to the app PLL.
 *
 * \param sw_pll                Pointer to the struct to be initialised.
 * \param Kp                    Proportional PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param Ki                    Integral PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param Kii                   Double integral PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param loop_rate_count       How many counts of the call to sw_pll_sdm_do_control before control is done.
 * \param ctrl_mid_point        The nominal control value for the Sigma Delta Modulator output. Normally
 *                              close to halfway to allow symmetrical range.
 * 
 */
void sw_pll_sdm_controller_init(sw_pll_state_t * const sw_pll,
                                const sw_pll_15q16_t Kp,
                                const sw_pll_15q16_t Ki,
                                const sw_pll_15q16_t Kii,
                                const size_t loop_rate_count,
                                const int32_t ctrl_mid_point);


/**
 * low level sw_pll_calc_sigma_delta function that turns a control signal
 * into a Sigma Delta Modulated output signal.
 *
 *
 * \param sdm_state     Pointer to the SDM state.
 * \param sdm_in        32b signed input error value. Note limited range.
 *                      See SW_PLL_SDM_UPPER_LIMIT and SW_PLL_SDM_LOWER_LIMIT.
 * \returns             Sigma Delta modulated signal.
 */
__attribute__((always_inline))
static inline int32_t sw_pll_calc_sigma_delta(sw_pll_sdm_state_t *sdm_state, int32_t sdm_in){
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
 * NOTE:    Attempting to write the PLL fractional register from more than
 *          one logical core at the same time may result in channel lock-up.
 *          Please ensure the that PLL initiaisation has completed before
 *          the SDM task writes to the register. The provided example
 *          implements a method for doing this.
 *
 * \param this_tile    The ID of the xcore tile that is doing the write.
 * \param frac_val     32b register value
 */
__attribute__((always_inline))
static inline void sw_pll_write_frac_reg(tileref_t this_tile, uint32_t frac_val){
    write_sswitch_reg_no_ack(this_tile, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, frac_val);
}


/**
 * Performs the Sigma Delta Modulation from a control input.
 * It performs the SDM algorithm, converts the output to a fractional register setting
 * and then writes the value to the PLL fractional register.
 * Is typically called in a constant period fast loop and run from a dedicated thread which could be on a remote tile.
 * 
 * NOTE:    Attempting to write the PLL fractional register from more than
 *          one logical core at the same time may result in channel lock-up.
 *          Please ensure the that PLL initiaisation has completed before
 *          the SDM task writes to the register. The provided `simple_sdm` example
 *          implements a method for doing this.
 * 
 * \param sw_pll            Pointer to the SDM state struct.
 * \param this_tile         The ID of the xcore tile that is doing the write.
 *                          Use get_local_tile_id() to obtain this.
 * \param sdm_control_in    Current control value.
 */
__attribute__((always_inline))
static inline void sw_pll_do_sigma_delta(sw_pll_sdm_state_t *sdm_state, tileref_t this_tile, int32_t sdm_control_in){

    int32_t sdm_out = sw_pll_calc_sigma_delta(sdm_state, sdm_control_in);
    uint32_t frac_val = sw_pll_sdm_out_to_frac_reg(sdm_out);
    sw_pll_write_frac_reg(this_tile, frac_val);
}
