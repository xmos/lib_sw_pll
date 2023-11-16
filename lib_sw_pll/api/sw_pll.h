// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#pragma once

#include <stdio.h>
#include <stdint.h>

#include <xcore/hwtimer.h>
#include <xcore/port.h>
#include <xcore/clock.h>
#include <xcore/channel.h>

// Helpers used in this module
#define TIMER_TIMEAFTER(A, B) ((int)((B) - (A)) < 0)    // Returns non-zero if A is after B, accounting for wrap
#define PORT_TIMEAFTER(NOW, EVENT_TIME) ((int16_t)((EVENT_TIME) - (NOW)) < 0) // Returns non-zero if A is after B, accounting for wrap
#define MAGNITUDE(A) (A < 0 ? -A : A)                   // Removes the sign of a value


typedef int32_t sw_pll_15q16_t; // Type for 15.16 signed fixed point
#define SW_PLL_NUM_FRAC_BITS 16
#define SW_PLL_15Q16(val) ((sw_pll_15q16_t)((float)val * (1 << SW_PLL_NUM_FRAC_BITS)))
#define SW_PLL_NUM_LUT_ENTRIES(lut_array) (sizeof(lut_array) / sizeof(lut_array[0]))

typedef enum sw_pll_lock_status_t{
    SW_PLL_UNLOCKED_LOW = -1,
    SW_PLL_LOCKED = 0,
    SW_PLL_UNLOCKED_HIGH = 1
} sw_pll_lock_status_t;

/**
 * \addtogroup sw_pll_api sw_pll_api
 *
 * The public API for using the RTOS I2C slave driver.
 * @{
 */

typedef struct sw_pll_state_t{
    // User definied paramaters
    sw_pll_15q16_t Kp;                  // Proportional constant
    sw_pll_15q16_t Ki;                  // Integral constant
    int32_t i_windup_limit;             // Integral term windup limit
    unsigned loop_rate_count;           // How often the control loop logic runs compared to control cal rate

    // Internal state
    int16_t mclk_diff;                  // Raw difference between mclk count and expected mclk count
    uint16_t ref_clk_pt_last;           // Last ref clock value
    uint32_t ref_clk_expected_inc;      // Expected ref clock increment
    uint64_t ref_clk_scaling_numerator; // Used for a cheap pre-computed divide rather than runtime divide
    int32_t error_accum;                // Accumulation of the raw mclk_diff term (for I)
    unsigned loop_counter;              // Intenal loop counter to determine when to do control
    uint16_t mclk_pt_last;              // The last mclk port timer count  
    uint32_t mclk_expected_pt_inc;      // Expected increment of port timer count
    uint16_t mclk_max_diff;             // Maximum mclk_diff before control loop decides to skip that iteration
    sw_pll_lock_status_t lock_status;   // State showing whether the PLL has locked or is under/over 
    uint8_t lock_counter;               // Counter used to determine lock status
    uint8_t first_loop;                 // Flag which indicates if the sw_pll is initialising or not

    const int16_t * lut_table_base;     // Pointer to the base of the fractional look up table  
    size_t num_lut_entries;             // Number of LUT entries
    unsigned nominal_lut_idx;           // Initial (mid point normally) LUT index
    
    uint16_t current_reg_val;           // Last value sent to the register, used by tests
}sw_pll_state_t;


/**
 * sw_pll initialisation function.
 *
 * This must be called before use of sw_pll_do_control.
 * Call this passing a pointer to the sw_pll_state_t stuct declared locally.
 *
 * \param \c sw_pll                Pointer to the struct to be initialised.
 * \param \c Kp                    Proportional PI constant. Use \c SW_PLL_15Q16() to convert from a float.
 * \param \c Ki                    Integral PI constant. Use \c SW_PLL_15Q16() to convert from a float.
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
 * 
 */
void sw_pll_init(   sw_pll_state_t * const sw_pll,
                    const sw_pll_15q16_t Kp,
                    const sw_pll_15q16_t Ki,
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
 * \param \c num_lut_entries   The number of elements in the sw_pll LUT.
 */ 
static inline void sw_pll_reset(sw_pll_state_t *sw_pll, sw_pll_15q16_t Kp, sw_pll_15q16_t Ki, size_t num_lut_entries)
{
    sw_pll->Kp = Kp;
    sw_pll->Ki = Ki;
    sw_pll->error_accum = 0;
    if(Ki){
        sw_pll->i_windup_limit = (num_lut_entries << SW_PLL_NUM_FRAC_BITS) / Ki; // Set to twice the max total error input to LUT
    }else{
        sw_pll->i_windup_limit = 0;
    }
}

///////// SDM WORK IN PROGRESS /////////

void sw_pll_sdm_init(sw_pll_state_t * const sw_pll,
                    const sw_pll_15q16_t Kp,
                    const sw_pll_15q16_t Ki,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const uint32_t app_pll_ctl_reg_val,
                    const uint32_t app_pll_div_reg_val,
                    const uint32_t app_pll_frac_reg_val,
                    const unsigned ppm_range);
sw_pll_lock_status_t sw_pll_sdm_do_control(sw_pll_state_t * const sw_pll, chanend_t c_sdm_control, const uint16_t mclk_pt, const uint16_t ref_pt);
int32_t sw_pll_sdm_do_control_from_error(sw_pll_state_t * const sw_pll, int16_t error);
void sw_pll_app_pll_init(const unsigned tileid,
                        const uint32_t app_pll_ctl_reg_val,
                        const uint32_t app_pll_div_reg_val,
                        const uint16_t frac_val_nominal); //TODO hide me
void sw_pll_send_ctrl_to_sdm_task(chanend_t c_sdm_control, int32_t dco_ctl);
