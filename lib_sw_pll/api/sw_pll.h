// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#pragma once

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#include <xcore/hwtimer.h>
#include <xcore/port.h>
#include <xcore/clock.h>
#include <xcore/channel.h>

// SW_PLL Component includes
#include "sw_pll_common.h"
#include "sw_pll_pfd.h"
#include "sw_pll_sdm.h"

/**
 * \addtogroup sw_pll_api sw_pll_general
 *
 * The public API for using the Software PLL.
 * @{
 */


/**
 * sw_pll initialisation function.
 *
 * This must be called before use of sw_pll_do_control.
 * Call this passing a pointer to the sw_pll_state_t stuct declared locally.
 *
 * \param \c sw_pll                Pointer to the struct to be initialised.
 * \param \c Kp                    Proportional PI constant. Use \c SW_PLL_15Q16() to convert from a float.
 * \param \c Ki                    Integral PI constant. Use \c SW_PLL_15Q16() to convert from a float.
 * \param \c Kii                   Double integral PI constant. Use \c SW_PLL_15Q16() to convert from a float.
 * \param \c loop_rate_count       How many counts of the call to sw_pll_do_control before control is done.
 *                                 Note this is only used by \c sw_pll_do_control. \c sw_pll_do_control_from_error
 *                                 calls the control loop every time so this is ignored.
 * \param \c pll_ratio             Integer ratio between input reference clock and the PLL output.
 *                                 Only used by sw_pll_do_control. Don't care otherwise.
 * \param \c ref_clk_expected_inc  Expected ref clock increment each time sw_pll_do_control is called.
 *                                 Pass in zero if you are sure the mclk sampling timing is precise. This
 *                                 will disable the scaling of the mclk count inside \c sw_pll_do_control.
 *                                 Only used by \c  sw_pll_do_control. Don't care otherwise.
 * \param \c lut_table_base        Pointer to the base of the fractional PLL LUT used 
 * \param \c num_lut_entries       Number of entries in the LUT (half sizeof since entries are 16b)
 * \param \c app_pll_ctl_reg_val   The setting of the app pll control register.
 * \param \c app_pll_div_reg_val   The setting of the app pll divider register.
 * \param \c nominal_lut_idx       The index into the LUT which gives the nominal output. Normally
 *                                 close to halfway to allow symmetrical range.
 * \param \c ppm_range             The pre-calculated PPM range. Used to determine the maximum deviation
 *                                 of counted mclk before the PLL resets its state.
 *                                 Note this is only used by \c sw_pll_do_control. \c sw_pll_do_control_from_error
 *                                 calls the control loop every time so this is ignored.
 * 
 */
void sw_pll_init(   sw_pll_state_t * const sw_pll,
                    const sw_pll_15q16_t Kp,
                    const sw_pll_15q16_t Ki,
                    const sw_pll_15q16_t Kii,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const int16_t * const lut_table_base,
                    const size_t num_lut_entries,
                    const uint32_t app_pll_ctl_reg_val,
                    const uint32_t app_pll_div_reg_val,
                    const unsigned nominal_lut_idx,
                    const unsigned ppm_range);

/**@}*/ // END: addtogroup sw_pll_general


/**
 * \addtogroup sw_pll_api sw_pll_lut
 *
 * The public API for using the Software PLL.
 * @{
 */

/**
 * sw_pll control function.
 *
 * This must be called periodically for every reference clock transition.
 * Typically, in an audio system, this would be at the I2S or reference clock input rate.
 * Eg. 16kHz, 48kHz ...
 * 
 * When this is called, the control loop will be executed every n times (set by init) and the 
 * application PLL will be adjusted to minimise the error seen on the mclk count value.
 * 
 * If the precise sampling point of mclk is not easily controlled (for example in an I2S callback)
 * then an additional timer count may be passed in which will scale the mclk count. See i2s_slave
 * example to show how this is done. This will help reduce input jitter which, in turn, relates 
 * to output jitter being a PLL.
 *
 * \param \c sw_pll    Pointer to the struct to be initialised.
 * \param \c mclk_pt   The 16b port timer count of mclk at the time of calling sw_pll_do_control.
 * \param \c ref_pt    The 16b port timer ref ount at the time of calling \c sw_pll_do_control. This value 
 *                     is ignored when the pll is initialised with a zero \c ref_clk_expected_inc and the
 *                     control loop will assume that \c mclk_pt sample timing is precise.
 * 
 * \returns            The lock status of the PLL. Locked or unlocked high/low. Note that
 *                     this value is only updated when the control loop has run.
 *                     The type is \c sw_pll_lock_status_t.
 */
sw_pll_lock_status_t sw_pll_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_pt);

/**
 * low level sw_pll control function for use as pure PLL control loop.
 *
 * This must be called periodically.
 * 
 * When this is called, the control loop will be executed every n times (set by init) and the 
 * application PLL will be adjusted to minimise the error seen on the input error value.
 *
 * \param \c sw_pll    Pointer to the struct to be initialised.
 * \param \c error     16b signed input error value
 * \returns            The lock status of the PLL. Locked or unlocked high/low. Note that
 *                     this value is only updated when the control loop is running.
 *                     The type is \c sw_pll_lock_status_t.
 */
sw_pll_lock_status_t sw_pll_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error);


/**
 * Helper to do a partial init of the PI controller at runtime without setting the physical PLL and LUT settings.
 *
 * Sets Kp, Ki and the windup limit. Note this resets the accumulator too and so state is reset.
 * 
 * \param \c sw_pll            Pointer to the struct to be initialised.
 * \param \c Kp                New Kp in \c sw_pll_15q16_t format.
 * \param \c Ki                New Ki in \c sw_pll_15q16_t format.
 * \param \c Kii               New Ki in \c sw_pll_15q16_t format.

 * \param \c num_lut_entries   The number of elements in the sw_pll LUT.
 */ 
static inline void sw_pll_reset(sw_pll_state_t *sw_pll, sw_pll_15q16_t Kp, sw_pll_15q16_t Ki, sw_pll_15q16_t Kii, size_t num_lut_entries)
{
    sw_pll->pi_state.Kp = Kp;
    sw_pll->pi_state.Ki = Ki;
    sw_pll->pi_state.Kii = Kii;

    sw_pll->pi_state.error_accum = 0;
    sw_pll->pi_state.error_accum_accum = 0;
    if(Ki){
        sw_pll->pi_state.i_windup_limit = (num_lut_entries << SW_PLL_NUM_FRAC_BITS) / Ki; // Set to twice the max total error input to LUT
    }else{
        sw_pll->pi_state.i_windup_limit = 0;
    }
    if(Kii){
        sw_pll->pi_state.ii_windup_limit = (num_lut_entries << SW_PLL_NUM_FRAC_BITS) / Kii; // Set to twice the max total error input to LUT
    }else{
        sw_pll->pi_state.ii_windup_limit = 0;
    }
}


/**@}*/ // END: addtogroup sw_pll_lut


/**
 * \addtogroup sw_pll_api sw_pll_sdm
 *
 * The public API for using the Software PLL.
 * @{
 */

/**
 * sw_pll_sdm initialisation function.
 *
 * This must be called before use of sw_pll_sdm_do_control or sw_pll_sdm_do_control_from_error.
 * Call this passing a pointer to the sw_pll_state_t stuct declared locally.
 *
 * \param \c sw_pll                Pointer to the struct to be initialised.
 * \param \c Kp                    Proportional PI constant. Use \c SW_PLL_15Q16() to convert from a float.
 * \param \c Ki                    Integral PI constant. Use \c SW_PLL_15Q16() to convert from a float.
 * \param \c Kii                   Double integral PI constant. Use \c SW_PLL_15Q16() to convert from a float.
 * \param \c loop_rate_count       How many counts of the call to sw_pll_sdm_do_control before control is done.
 *                                 Note this is only used by \c sw_pll_sdm_do_control. \c sw_pll_sdm_do_control_from_error
 *                                 calls the control loop every time so this is ignored.
 * \param \c pll_ratio             Integer ratio between input reference clock and the PLL output.
 *                                 Only used by sw_pll_sdm_do_control. Don't care otherwise.
 * \param \c ref_clk_expected_inc  Expected ref clock increment each time sw_pll_do_control is called.
 *                                 Pass in zero if you are sure the mclk sampling timing is precise. This
 *                                 will disable the scaling of the mclk count inside \c sw_pll_sdm_do_control.
 *                                 Only used by \c  sw_pll_sdm_do_control. Don't care otherwise.
 * \param \c app_pll_ctl_reg_val   The setting of the app pll control register.
 * \param \c app_pll_div_reg_val   The setting of the app pll divider register.
 * \param \c app_pll_frac_reg_val  The setting of the app pll fractional register.
 * \param \c ctrl_mid_point        The nominal control value for the Sigma Delta Modulator output. Normally
 *                                 close to halfway to allow symmetrical range.
 * \param \c ppm_range             The pre-calculated PPM range. Used to determine the maximum deviation
 *                                 of counted mclk before the PLL resets its state. Note this is only used 
 *                                 by \c sw_pll_sdm_do_control. \c sw_pll_sdm_do_control_from_error
 *                                 calls the control loop every time so this is ignored.
 * 
 */
void sw_pll_sdm_init(sw_pll_state_t * const sw_pll,
                    const sw_pll_15q16_t Kp,
                    const sw_pll_15q16_t Ki,
                    const sw_pll_15q16_t Kii,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const uint32_t app_pll_ctl_reg_val,
                    const uint32_t app_pll_div_reg_val,
                    const uint32_t app_pll_frac_reg_val,
                    const int32_t ctrl_mid_point,
                    const unsigned ppm_range);

/**
 * sw_pll_sdm_do_control control function.
 *
 * This must be called periodically for every reference clock transition.
 * Typically, in an audio system, this would be at the I2S or reference clock input rate.
 * Eg. 16kHz, 48kHz ...
 * 
 * When this is called, the control loop will be executed every n times (set by init) and the 
 * Sigma Delta Modulator control value will be set according the error seen on the mclk count value.
 * 
 * If control is executed, TRUE is returned from the function.
 * The most recent calculated control output value can be found written to sw_pll->sdm_state.current_ctrl_val.
 * 
 * If the precise sampling point of mclk is not easily controlled (for example in an I2S callback)
 * then an additional timer count may be passed in which will scale the mclk count. See i2s_slave
 * example to show how this is done. This will help reduce input jitter which, in turn, relates 
 * to output jitter being a PLL.
 *
 * \param \c sw_pll    Pointer to the struct to be initialised.
 * \param \c mclk_pt   The 16b port timer count of mclk at the time of calling sw_pll_do_control.
 * \param \c ref_pt    The 16b port timer ref ount at the time of calling \c sw_pll_do_control. This value 
 *                     is ignored when the pll is initialised with a zero \c ref_clk_expected_inc and the
 *                     control loop will assume that \c mclk_pt sample timing is precise.
 * 
 * \returns            Whether or not control was executed (controoled by loop_rate_count)
 */
bool sw_pll_sdm_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_pt);

/**
 * low level sw_pll_sdm control function for use as pure PLL control loop.
 *
 * This must be called periodically.
 * 
 * Takes the raw error input and applies the PI controller algorithm
 *
 * \param \c sw_pll    Pointer to the struct to be initialised.
 * \param \c error     16b signed input error value
 * \returns            The PI processed error
 */
int32_t sw_pll_sdm_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error);

/**
 * low level sw_pll_sdm post control processing function.
 *
 * This must be called after sw_pll_sdm_do_control_from_error.
 * 
 * Takes the PI processed error and applies a low pass filter and calaculates the Sigma Delta Modulator
 * control signal. It also checks the range and sets the PLL lock status if exceeded.
 *
 * \param \c sw_pll    Pointer to the struct to be initialised.
 * \param \c error     32b signed input error value from PI controller
 * \returns            The Sigma Delta Modulator Control signal
 */
int32_t sw_pll_sdm_post_control_proc(sw_pll_state_t * const sw_pll, int32_t error);

/**
 * Use to initialise the core sigma delta modulator. Broken out as seperate API as the SDM
 * is often run in a dedicated thread which could be on a remote tile.
 * 
 * \param \c sdm_state    Pointer to the struct to be initialised.
 */
void sw_pll_init_sigma_delta(sw_pll_sdm_state_t *sdm_state);


/**@}*/ // END: addtogroup sw_pll_sdm
