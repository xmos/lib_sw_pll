// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <stdio.h>
#include <stdint.h>

#include <xcore/hwtimer.h>
#include <xcore/port.h>
#include <xcore/clock.h>

// Helpers used in this module
#define TIMER_TIMEAFTER(A, B) ((int)((B) - (A)) < 0)
#define PORT_TIMEAFTER(NOW, EVENT_TIME) ((int16_t)((EVENT_TIME) - (NOW)) < 0)
#define MAGNITUDE(A) (A < 0 ? -A : A)


typedef int32_t sw_pll_15q16_t;
#define SW_PLL_NUM_FRAC_BITS 16
#define SW_PLL_15Q16(val) ((sw_pll_15q16_t)((float)val * (1 << SW_PLL_NUM_FRAC_BITS)))
#define SW_PLL_NUM_LUT_ENTRIES(lut_array) (sizeof(lut_array) / sizeof(lut_array[0]))

typedef struct sw_pll_state_t{
    // User definied paramaters
    sw_pll_15q16_t Kp;
    sw_pll_15q16_t Ki;
    sw_pll_15q16_t Kii;
    int32_t i_windup_limit;
    int32_t ii_windup_limit;
    unsigned loop_rate_count;

    // Internal state
    int32_t error_accum;
    unsigned loop_counter;
    int16_t mclk_pt_last;
    int16_t mclk_expected_pt_inc;
    uint16_t mclk_max_diff;
    int8_t lock_status;
    uint8_t lock_counter;
    uint8_t first_loop;

    int16_t *lut_table_base;
    size_t num_lut_entries;
    unsigned nominal_lut_idx;
}sw_pll_state_t;

enum sw_pll_lock_status{
    SW_PLL_UNLOCKED_LOW = -1,
    SW_PLL_LOCKED = 0,
    SW_PLL_UNLOCKED_HIGH = 1
};

void sw_pll_init(   sw_pll_state_t *sw_pll,
                    sw_pll_15q16_t Kp,
                    sw_pll_15q16_t Ki,
                    size_t loop_rate_count,
                    size_t pll_ratio,
                    int16_t *lut_table_base,
                    size_t num_lut_entries,
                    uint32_t app_pll_ctl_reg_val,
                    uint32_t div_val,
                    unsigned nominal_lut_idx,
                    unsigned ppm_range);

void setup_ref_and_mclk_ports_and_clocks(port_t p_mclk, xclock_t clk_mclk, port_t p_ref_clk_in, xclock_t clk_word_clk, port_t p_ref_clk_count);

int sw_pll_do_control(sw_pll_state_t *sw_pll, uint16_t mclk_pt);

void sw_pll_reset(sw_pll_state_t *sw_pll);
