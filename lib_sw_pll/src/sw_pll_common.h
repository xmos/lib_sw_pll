// Copyright 2023-2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#pragma once

// The number of consecutive lock positive reports of the control loop before declaring we are finally locked
#define SW_PLL_LOCK_COUNT   10 

// Helpers used in this module
#define TIMER_TIMEAFTER(A, B) ((int)((B) - (A)) < 0)    // Returns non-zero if A is after B, accounting for wrap
#define PORT_TIMEAFTER(NOW, EVENT_TIME) ((int16_t)((EVENT_TIME) - (NOW)) < 0) // Returns non-zero if A is after B, accounting for wrap
#define MAGNITUDE(A) (A < 0 ? -A : A)                   // Removes the sign of a value

typedef int32_t sw_pll_15q16_t; // Type for 15.16 signed fixed point

#define SW_PLL_NUM_FRAC_BITS 16
#define SW_PLL_15Q16(val) ((sw_pll_15q16_t)((float)val * (1 << SW_PLL_NUM_FRAC_BITS)))
#define SW_PLL_NUM_LUT_ENTRIES(lut_array) (sizeof(lut_array) / sizeof(lut_array[0]))

// This is just here to catch an error and provide useful info if you happen to forget to include from XC properly
typedef struct xc_check{
    int *xc_check; // If you see this error, then you need to extern "C"{} the sw_pll include in your XC file.
} xc_check;

typedef enum sw_pll_lock_status_t{
    SW_PLL_UNLOCKED_LOW = -1,
    SW_PLL_LOCKED = 0,
    SW_PLL_UNLOCKED_HIGH = 1
} sw_pll_lock_status_t;

typedef struct sw_pll_pfd_state_t{
    int16_t mclk_diff;                  // Raw difference between mclk count and expected mclk count
    uint16_t ref_clk_pt_last;           // Last ref clock value
    uint32_t ref_clk_expected_inc;      // Expected ref clock increment
    uint64_t ref_clk_scaling_numerator; // Used for a cheap pre-computed divide rather than runtime divide
    uint16_t mclk_pt_last;              // The last mclk port timer count  
    uint32_t mclk_expected_pt_inc;      // Expected increment of port timer count
    uint16_t mclk_max_diff;             // Maximum mclk_diff before control loop decides to skip that iteration
} sw_pll_pfd_state_t;

typedef struct sw_pll_pi_state_t{
    sw_pll_15q16_t Kp;                  // Proportional constant
    sw_pll_15q16_t Ki;                  // Integral constant
    sw_pll_15q16_t Kii;                 // Double integral constant
    int32_t i_windup_limit;             // Integral term windup limit
    int32_t ii_windup_limit;            // Double integral term windup limit
    int32_t error_accum;                // Accumulation of the raw mclk_diff term (for I)
    int32_t error_accum_accum;          // Accumulation of the raw mclk_diff term (for II)
    int32_t iir_y;                      // Optional IIR low pass filter state
} sw_pll_pi_state_t;

typedef struct sw_pll_lut_state_t{
    const int16_t * lut_table_base;     // Pointer to the base of the fractional look up table  
    size_t num_lut_entries;             // Number of LUT entries
    unsigned nominal_lut_idx;           // Initial (mid point normally) LUT index
    uint16_t current_reg_val;           // Last value sent to the register, used by tests
} sw_pll_lut_state_t;


typedef struct sw_pll_sdm_state_t{
    int32_t current_ctrl_val;           // The last control value calculated
    int32_t ctrl_mid_point;             // The mid point for the DCO input
    int32_t ds_x1;                      // Sigma delta modulator state
    int32_t ds_x2;                      // Sigma delta modulator state
    int32_t ds_x3;                      // Sigma delta modulator state
} sw_pll_sdm_state_t;


typedef struct sw_pll_state_t{

    sw_pll_lock_status_t lock_status;   // State showing whether the PLL has locked or is under/over 
    uint8_t lock_counter;               // Counter used to determine lock status
    uint8_t first_loop;                 // Flag which indicates if the sw_pll is initialising or not
    unsigned loop_rate_count;           // How often the control loop logic runs compared to control call rate
    unsigned loop_counter;              // Intenal loop counter to determine when to do control

    sw_pll_pfd_state_t pfd_state;       // Phase Frequency Detector
    sw_pll_pi_state_t pi_state;         // PI(II) controller
    sw_pll_lut_state_t lut_state;       // Look Up Table based DCO
    sw_pll_sdm_state_t sdm_state;       // Sigma Delta Modulator base DCO
    
}sw_pll_state_t;

/**
 * This is the core PI controller code used by both SDM and LUT SW PLLs.
 *
 * \param sw_pll                Pointer to the Software PLL state.
 * \param error                 The error input to the PI controller.
 */ 
__attribute__((always_inline))
inline int32_t sw_pll_do_pi_ctrl(sw_pll_state_t * const sw_pll, int16_t error)
{
    sw_pll->pi_state.error_accum += error; // Integral error.
    sw_pll->pi_state.error_accum = sw_pll->pi_state.error_accum > sw_pll->pi_state.i_windup_limit ? sw_pll->pi_state.i_windup_limit : sw_pll->pi_state.error_accum;
    sw_pll->pi_state.error_accum = sw_pll->pi_state.error_accum < -sw_pll->pi_state.i_windup_limit ? -sw_pll->pi_state.i_windup_limit : sw_pll->pi_state.error_accum;
 
    sw_pll->pi_state.error_accum_accum += sw_pll->pi_state.error_accum; // Double integral error.
    sw_pll->pi_state.error_accum_accum = sw_pll->pi_state.error_accum_accum > sw_pll->pi_state.ii_windup_limit ? sw_pll->pi_state.ii_windup_limit : sw_pll->pi_state.error_accum_accum;
    sw_pll->pi_state.error_accum_accum = sw_pll->pi_state.error_accum_accum < -sw_pll->pi_state.ii_windup_limit ? -sw_pll->pi_state.ii_windup_limit : sw_pll->pi_state.error_accum_accum;

    // Use long long maths to avoid overflow if ever we had a large error accum term
    int64_t error_p = ((int64_t)sw_pll->pi_state.Kp * (int64_t)error);
    int64_t error_i = ((int64_t)sw_pll->pi_state.Ki * (int64_t)sw_pll->pi_state.error_accum);
    int64_t error_ii = ((int64_t)sw_pll->pi_state.Kii * (int64_t)sw_pll->pi_state.error_accum_accum);

    // Convert back to 32b since we are handling LUTs of around a hundred entries
    int32_t total_error = (int32_t)((error_p + error_i + error_ii) >> SW_PLL_NUM_FRAC_BITS);

    return total_error;
}

/**
 * Initialise the application (secondary) PLL.
 *
 * \param tileid                The resource ID of the tile that calls this function.
 * \param app_pll_ctl_reg_val   The App PLL control register setting.
 * \param app_pll_div_reg_val   The App PLL divider register setting.
 * \param frac_val_nominal      The App PLL initial fractional register setting.
 */ void sw_pll_app_pll_init(   const unsigned tileid,
                                const uint32_t app_pll_ctl_reg_val,
                                const uint32_t app_pll_div_reg_val,
                                const uint16_t frac_val_nominal);

