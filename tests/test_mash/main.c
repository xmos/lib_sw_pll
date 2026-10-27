// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.
/// MASH controller harness for Python/xsim equivalence and closed-loop tests.
/// Arguments follow sw_pll_mash_init, with target frequency retained for the
/// Python harness and optional mode: "timers", "error", or "timers-batch".
/// Timer mode reads mclk/ref port counts; error mode reads signed 16-bit errors.
/// xsim represents average PLL frequency, not the hardware MASH sequence.
/// Report the commanded word explicitly so Python can derive average frequency;
/// these tests do not establish hardware noise shaping, phase noise or jitter.
#include "xs1.h"
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <sw_pll.h>
#include <stdint.h>
#include <inttypes.h>
#include <string.h>
#include <xcore/hwtimer.h>

#define IN_LINE_SIZE 1000

int main(int argc, char** argv) {
    if (argc != 12 && argc != 13) {
        fprintf(stderr, "Expected 11 initialization arguments and optional timers/error mode\n");
        return 1;
    }
    bool direct_error = argc == 13 && strcmp(argv[12], "error") == 0;
    bool batch_mode = argc == 13 && strcmp(argv[12], "timers-batch") == 0;
    if (argc == 13 && !direct_error && !batch_mode && strcmp(argv[12], "timers") != 0) {
        fprintf(stderr, "Unknown MASH test mode: %s\n", argv[12]);
        return 1;
    }
    // Batch traces require no per-sample host handshake. Buffer responses to
    // reduce xsim stdio overhead; process exit flushes the remaining output.
    if (batch_mode) {
        setvbuf(stdout, NULL, _IOFBF, 4096);
    }
    int arg_index = 1;
    float kp = strtof(argv[arg_index++], NULL);
    float ki = strtof(argv[arg_index++], NULL);
    float kii = strtof(argv[arg_index++], NULL);
    size_t loop_rate_count = (size_t)strtoul(argv[arg_index++], NULL, 0);
    size_t pll_ratio = (size_t)strtoul(argv[arg_index++], NULL, 0);
    uint32_t ref_clk_expected_inc = (uint32_t)strtoul(argv[arg_index++], NULL, 0);
    uint32_t app_pll_ctl_reg_val = (uint32_t)strtoul(argv[arg_index++], NULL, 0);
    uint32_t app_pll_div_reg_val = (uint32_t)strtoul(argv[arg_index++], NULL, 0);
    sw_pll_mash_word_t nominal_mash_val = (sw_pll_mash_word_t)strtol(argv[arg_index++], NULL, 0);
    unsigned ppm_range = (unsigned)strtoul(argv[arg_index++], NULL, 0);
    if (loop_rate_count == 0) {
        fprintf(stderr, "loop_rate_count must be positive\n");
        return 1;
    }

    sw_pll_state_t sw_pll = {0};
    sw_pll_result_t error = sw_pll_mash_init(&sw_pll,
                                SW_PLL_15Q16(kp),
                                SW_PLL_15Q16(ki),
                                SW_PLL_15Q16(kii),
                                loop_rate_count,
                                pll_ratio,
                                ref_clk_expected_inc,
                                app_pll_ctl_reg_val,
                                app_pll_div_reg_val,
                                nominal_mash_val,
                                ppm_range,
                                SW_PLL_TILE_1);

    if(error != SW_PLL_SUCCESS) {
        fprintf(stderr, "Error from sw_pll_mash_init: %d\n", error);
        return 1;
    }

    char read_buf[IN_LINE_SIZE];
    while (fgets(read_buf, sizeof(read_buf), stdin) != NULL) {
        uint16_t mclk_pt = 0;
        uint16_t ref_pt = 0;
        int32_t input_error = 0;
        if (direct_error) {
            if (sscanf(read_buf, "%" SCNd32, &input_error) != 1 ||
                input_error < INT16_MIN || input_error > INT16_MAX) {
                fprintf(stderr, "Expected a signed 16-bit error\n");
                return 1;
            }
        } else if (sscanf(read_buf, "%" SCNu16 " %" SCNu16, &mclk_pt, &ref_pt) != 2) {
            fprintf(stderr, "Expected two unsigned 16-bit port counts\n");
            return 1;
        }
        uint32_t t0 = get_reference_time();
        sw_pll_lock_status_t status = direct_error
            ? sw_pll_mash_do_control_from_error(&sw_pll, (int16_t)input_error)
            : sw_pll_mash_do_control(&sw_pll, mclk_pt, ref_pt);
        uint32_t t1 = get_reference_time();
        int32_t reported_error = direct_error ? input_error : sw_pll.pfd_state.mclk_diff;
        // Observe the controller command, not a cycle-accurate modulator output.
        printf("%d %" PRId32 " %" PRId32 " %" PRId32 " %" PRId32 " %u %" PRIu32 " %u %u\n",
               status, sw_pll.mash_state.current_ctrl_val, reported_error,
               sw_pll.pi_state.error_accum, sw_pll.pi_state.error_accum_accum,
               sw_pll.first_loop, t1 - t0, sw_pll.lock_counter, sw_pll.loop_counter);
        if (!batch_mode) {
            fflush(stdout);
        }
    }
    return 0;
}
