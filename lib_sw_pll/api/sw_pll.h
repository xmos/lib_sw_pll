// Copyright 2022-2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#pragma once

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <xccompat.h>

#ifdef __XC__
#define _Bool uint8_t
#else
#include <xcore/hwtimer.h>
#include <xcore/port.h>
#include <xcore/clock.h>
#include <xcore/channel.h>
#include <xcore/assert.h>
#endif

// SW_PLL Component includes
#include "sw_pll_common.h"
#include "sw_pll_pfd.h"
#include "sw_pll_sdm.h"


/**
 * \addtogroup sw_pll_lut sw_pll_lut
 *
 * The public API for using the Software PLL.
 * @{
 */

/**
 * sw_lut_pll initialisation function.
 *
 * This must be called before use of sw_pll_lut_do_control.
 * Call this passing a pointer to the sw_pll_state_t stuct declared locally.
 *
 * \param sw_pll                Pointer to the struct to be initialised.
 * \param Kp                    Proportional PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param Ki                    Integral PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param Kii                   Double integral PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param loop_rate_count       How many counts of the call to sw_pll_lut_do_control before control is done.
 *                              Note this is only used by sw_pll_lut_do_control. sw_pll_lut_do_control_from_error
 *                              calls the control loop every time so this is ignored.
 * \param pll_ratio             Integer ratio between input reference clock and the PLL output.
 *                              Only used by sw_pll_lut_do_control for the PFD. Don't care otherwise.
 *                              Used to calculate the expected port timer increment when control is called.
 * \param ref_clk_expected_inc  Expected ref clock increment each time sw_pll_lut_do_control is called.
 *                              Pass in zero if you are sure the mclk sampling timing is precise. This
 *                              will disable the scaling of the mclk count inside sw_pll_lut_do_control.
 *                              Only used by  sw_pll_lut_do_control. Don't care otherwise.
 * \param lut_table_base        Pointer to the base of the fractional PLL LUT used 
 * \param num_lut_entries       Number of entries in the LUT (half sizeof since entries are 16b)
 * \param app_pll_ctl_reg_val   The setting of the app pll control register.
 * \param app_pll_div_reg_val   The setting of the app pll divider register.
 * \param nominal_lut_idx       The index into the LUT which gives the nominal output. Normally
 *                              close to halfway to allow symmetrical range.
 * \param ppm_range             The pre-calculated PPM range. Used to determine the maximum deviation
 *                              of counted mclk before the PLL resets its state.
 *                              Note this is only used by sw_pll_lut_do_control. sw_pll_lut_do_control_from_error
 *                              calls the control loop every time so this is ignored.
 * 
 */
void sw_pll_lut_init(   sw_pll_state_t * const sw_pll,
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



/**
 * sw_pll LUT version control function.
 * 
 * It implements the PFD, controller and DCO output.
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
 * to reduced output jitter.
 *
 * \param sw_pll    Pointer to the sw_pll state struct.
 * \param mclk_pt   The 16b port timer count of mclk at the time of calling sw_pll_lut_do_control.
 * \param ref_pt    The 16b port timer ref ount at the time of calling sw_pll_lut_do_control. This value 
 *                  is ignored when the pll is initialised with a zero ref_clk_expected_inc and the
 *                  control loop will assume that mclk_pt sample timing is precise.
 * 
 * \returns         The lock status of the PLL. Locked or unlocked high/low. Note that
 *                  this value is only updated when the control loop has run.
 *                  The type is sw_pll_lock_status_t.
 */
sw_pll_lock_status_t sw_pll_lut_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_pt);

/**
 * low level sw_pll control function for use as pure PLL control loop.
 *
 * This must be called periodically.
 * 
 * When this is called, the control loop will be executed every time and the 
 * application PLL will be adjusted to minimise the error seen on the input error value.
 *
 * \param sw_pll    Pointer to the sw_pll state struct.
 * \param error     16b signed input error value
 * \returns         The lock status of the PLL. Locked or unlocked high/low. Note that
 *                  this value is only updated when the control loop is running.
 *                  The type is sw_pll_lock_status_t.
 */
sw_pll_lock_status_t sw_pll_lut_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error);


/**
 * Helper to do a partial init of the PI controller at runtime without setting the physical PLL and LUT settings.
 *
 * Sets Kp, Ki and the windup limits. Note this resets the PFD accumulators too and so PI controller state is reset.
 * 
 * \param sw_pll            Pointer to the state struct to be reset.
 * \param Kp                New Kp in sw_pll_15q16_t format.
 * \param Ki                New Ki in sw_pll_15q16_t format.
 * \param Kii               New Kii in sw_pll_15q16_t format.
 * \param num_lut_entries   The number of elements in the sw_pll LUT.
 */ 
static inline void sw_pll_lut_reset(sw_pll_state_t *sw_pll, sw_pll_15q16_t Kp, sw_pll_15q16_t Ki, sw_pll_15q16_t Kii, size_t num_lut_entries)
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
 * \addtogroup sw_pll_sdm sw_pll_sdm
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
 * \param sw_pll                Pointer to the struct to be initialised.
 * \param Kp                    Proportional PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param Ki                    Integral PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param Kii                   Double integral PI constant. Use SW_PLL_15Q16() to convert from a float.
 * \param loop_rate_count       How many counts of the call to sw_pll_sdm_do_control before control is done.
 *                              Note this is only used by sw_pll_sdm_do_control. sw_pll_sdm_do_control_from_error
 *                              calls the control loop every time so this is ignored.
 * \param pll_ratio             Integer ratio between input reference clock and the PLL output.
 *                              Only used by sw_pll_sdm_do_control in the PFD. Don't care otherwise.
 *                              Used to calculate the expected port timer increment when control is called.
 * \param ref_clk_expected_inc  Expected ref clock increment each time sw_pll_sdm_do_control is called.
 *                              Pass in zero if you are sure the mclk sampling timing is precise. This
 *                              will disable the scaling of the mclk count inside sw_pll_sdm_do_control.
 *                              Only used by  sw_pll_sdm_do_control. Don't care otherwise.
 * \param app_pll_ctl_reg_val   The setting of the app pll control register.
 * \param app_pll_div_reg_val   The setting of the app pll divider register.
 * \param app_pll_frac_reg_val  The initial setting of the app pll fractional register.
 * \param ctrl_mid_point        The nominal control value for the Sigma Delta Modulator output. Normally
 *                              close to halfway to allow symmetrical range.
 * \param ppm_range             The pre-calculated PPM range. Used to determine the maximum deviation
 *                              of counted mclk before the PLL resets its state. Note this is only used 
 *                              by sw_pll_sdm_do_control. sw_pll_sdm_do_control_from_error
 *                              calls the control loop every time so this is ignored.
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
 * It implements the PFD and controller and generates a DCO control value for the SDM.
 *
 * This must be called periodically for every reference clock transition.
 * Typically, in an audio system, this would be at the I2S or reference clock input rate.
 * Eg. 16kHz, 48kHz ...
 * 
 * When this is called, the control loop will be executed every n times (set by init) and the 
 * Sigma Delta Modulator control value will be set according the error seen on the mclk count value.
 * 
 * If control is executed, TRUE is returned from the function and the value can be sent to the SDM. 
 * The most recent calculated control output value can be found written to sw_pll->sdm_state.current_ctrl_val.
 * 
 * If the precise sampling point of mclk is not easily controlled (for example in an I2S callback)
 * then an additional timer count may be passed in which will scale the mclk count. See i2s_slave
 * example to show how this is done. This will help reduce input jitter which, in turn, relates 
 * to reduced output jitter.
 *
 * \param sw_pll    Pointer to the sw_pll state struct.
 * \param mclk_pt   The 16b port timer count of mclk at the time of calling sw_pll_sdm_do_control.
 * \param ref_pt    The 16b port timer ref ount at the time of calling sw_pll_sdm_do_control. This value 
 *                  is ignored when the pll is initialised with a zero ref_clk_expected_inc and the
 *                  control loop will assume that mclk_pt sample timing is precise.
 * 
 * \returns         Whether or not control was executed (controoled by loop_rate_count)
 */
bool sw_pll_sdm_do_control(sw_pll_state_t * const sw_pll, const uint16_t mclk_pt, const uint16_t ref_pt);

/**
 * low level sw_pll_sdm control function for use as pure PLL control loop.
 *
 * This must be called periodically.
 * 
 * Takes the raw error input and applies the PI controller algorithm.
 * The most recent calculated control output value can be found written to sw_pll->sdm_state.current_ctrl_val.
 *
 * \param sw_pll    Pointer to the sw_pll state struct.
 * \param error     16b signed input error value
 * \returns         The controller lock status
 */
sw_pll_lock_status_t sw_pll_sdm_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error);


/**
 * Use to initialise the core sigma delta modulator. Broken out as seperate API as the SDM
 * is usually run in a dedicated thread which could be on a remote tile.
 * 
 * \param sw_pll    Pointer to the SDM state struct.
 */
void sw_pll_init_sigma_delta(sw_pll_sdm_state_t *sdm_state);


#ifdef __DOXYGEN__
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
static inline void sw_pll_do_sigma_delta(sw_pll_sdm_state_t *sdm_state, tileref_t this_tile, int32_t sdm_control_in);
#endif

/**@}*/ // END: addtogroup sw_pll_sdm

/**
 * \addtogroup sw_pll_common sw_pll_common
 *
 * The public API for using the Software PLL.
 * @{
 */

/**
 * Resets PI controller state
 *
 * \param sw_pll            Pointer to the Software PLL state.
 */ 
__attribute__((always_inline))
inline void sw_pll_reset_pi_state(sw_pll_state_t * const sw_pll)
{
    sw_pll->pi_state.error_accum = 0;
    sw_pll->pi_state.error_accum_accum = 0;
}

/**
 * Output a fixed (not phase locked) clock between 11.2896 MHz and 49.152 MHz.
 * Assumes a 24 MHz XTAL.
 *
 * \param frequency         Frequency in Hz. An incorrect value will assert.
 */ 
void sw_pll_fixed_clock(const unsigned frequency);

/**@}*/ // END: addtogroup sw_pll_common
