// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#pragma once

#include <stdio.h>
#include <stdint.h>

#include <xcore/hwtimer.h>
#include <xcore/port.h>
#include <xcore/clock.h>

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
    uint32_t ref_clk_scaling_numerator; // Used for a cheap pre-computed divide rather than runtime divide
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
 * \param sw_pll                Pointer to the struct to be initialised.
 * \param Kp                    Proportional PID constant. Use SW_PLL_15Q16 to convert from a float.
 * \param Ki                    Integral PID constant. Use SW_PLL_15Q16 to convert from a float.
 * \param loop_rate_count       How many counts of the call to sw_pll_do_control before control is done
 * \param pll_ratio             Integer ratio between input reference clock and the PLL output.
 * \param ref_clk_expected_inc  Expected ref clock increment each time sw_pll_do_control is called.
 *                              Pass in zero if you are sure the mclk sampling timing is precise. This
 *                              will disable the scaling of the mclk count inside sw_pll_do_control.
 * \param lut_table_base        Pointer to the base of the fractional PLL LUT used 
 * \param num_lut_entries       Number of entries in the LUT (half sizeof since entries are 16b)
 * \param app_pll_ctl_reg_val   The setting of the app pll control register.
 * \param app_pll_div_reg_val   The setting of the app pll divider register.
 * \param nominal_lut_idx       The index into the LUT which gives the nominal output. Normally
 *                              close to halfway to allow symmetrical range.
 * \param ppm_range             The pre-calculated PPM range. Used to determine the maximum deviation
 *                              of counted mclk before the PLL resets its state.
 * 
 */
void sw_pll_init(   sw_pll_state_t *sw_pll,
                    const sw_pll_15q16_t Kp,
                    const sw_pll_15q16_t Ki,
                    const size_t loop_rate_count,
                    const size_t pll_ratio,
                    const uint32_t ref_clk_expected_inc,
                    const int16_t *lut_table_base,
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
 * \param sw_pll    Pointer to the struct to be initialised.
 * \param mclk_pt   The 16b port timer count of mclk at the time of calling sw_pll_do_control.
 * \param ref_pt    The 16b port timer ref ount at the time of calling sw_pll_do_control. This value 
 *                  is ignored when the pll is initialised with a zero ref_clk_expected_inc and the
 *                  control loop will assume that mclk_pt sample timing is precise.
 * 
 * \returns         The lock status of the PLL. Locked or unlocked high/low. Note that
 *                  this value is only updated when the control loop is running.
 */
sw_pll_lock_status_t sw_pll_do_control(sw_pll_state_t *sw_pll, const uint16_t mclk_pt, const uint16_t ref_pt);
