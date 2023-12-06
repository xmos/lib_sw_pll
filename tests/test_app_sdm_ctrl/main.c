// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.
///
/// Application to call the control loop with the parameters fully 
/// controllable by an external application. This app expects the 
/// sw_pll_init parameters on the commannd line. 
///
/// After init, the app will expect 1 integer to come in over stdin, This
/// is the mclk diff and is fed into the controller.
///
///
#include "xs1.h"
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <sw_pll.h>
#include <stdint.h>
#include <xcore/hwtimer.h>
#include <xcore/parallel.h>
#include <xcore/channel.h>
#include <xcore/select.h>

#define IN_LINE_SIZE 1000

extern int32_t sw_pll_sdm_post_control_proc(sw_pll_state_t * const sw_pll, int32_t error);


DECLARE_JOB(control_task, (int, char**, chanend_t));
void control_task(int argc, char** argv, chanend_t c_sdm_control) {
       
    int i = 1;

    float kp = atof(argv[i++]);
    fprintf(stderr, "kp\t\t%f\n", kp);
    float ki = atof(argv[i++]);
    fprintf(stderr, "ki\t\t%f\n", ki);
    float kii = atof(argv[i++]);
    fprintf(stderr, "kii\t\t%f\n", kii);
    size_t loop_rate_count = atoi(argv[i++]);
    fprintf(stderr, "loop_rate_count\t\t%d\n", loop_rate_count);
    size_t pll_ratio = atoi(argv[i++]);
    fprintf(stderr, "pll_ratio\t\t%d\n", pll_ratio);
    uint32_t ref_clk_expected_inc = atoi(argv[i++]);
    fprintf(stderr, "ref_clk_expected_inc\t\t%lu\n", ref_clk_expected_inc);
    uint32_t app_pll_ctl_reg_val = atoi(argv[i++]);
    fprintf(stderr, "app_pll_ctl_reg_val\t\t%lu\n", app_pll_ctl_reg_val);
    uint32_t app_pll_div_reg_val = atoi(argv[i++]);
    fprintf(stderr, "app_pll_div_reg_val\t\t%lu\n", app_pll_div_reg_val);
    uint32_t app_pll_frac_reg_val = atoi(argv[i++]);
    fprintf(stderr, "app_pll_frac_reg_val\t\t%lu\n", app_pll_frac_reg_val);
    int32_t ctrl_mid_point = atoi(argv[i++]);
    fprintf(stderr, "ctrl_mid_point\t\t%ld\n", ctrl_mid_point);
    unsigned ppm_range = atoi(argv[i++]);
    fprintf(stderr, "ppm_range\t\t%d\n", ppm_range);
    unsigned target_output_frequency = atoi(argv[i++]);
    fprintf(stderr, "target_output_frequency\t\t%d\n", target_output_frequency);

    if(i != argc) {
        fprintf(stderr, "wrong number of params sent to main.c in xcore test app\n");        
        exit(1);
    }

    sw_pll_state_t sw_pll;

    sw_pll_sdm_init(&sw_pll,
                SW_PLL_15Q16(kp),
                SW_PLL_15Q16(ki),
                SW_PLL_15Q16(kii),
                loop_rate_count,
                pll_ratio,
                ref_clk_expected_inc,
                app_pll_ctl_reg_val,
                app_pll_div_reg_val,
                app_pll_frac_reg_val,
                ctrl_mid_point,
                ppm_range);


    for(;;) {
        char read_buf[IN_LINE_SIZE];
        int len = 0;
        for(;;) {
            int val = fgetc(stdin);
            if(EOF == val) {
                exit(0);
            }
            if('\n' == val) {
                read_buf[len] = 0;
                break;
            }
            else {
                read_buf[len++] = val;
            }
        }

        int16_t mclk_diff;
        sscanf(read_buf, "%hd", &mclk_diff);

        uint32_t t0 = get_reference_time();
        int32_t error = sw_pll_do_pi_ctrl(&sw_pll, -mclk_diff);
        int32_t dco_ctl = sw_pll_sdm_post_control_proc(&sw_pll, error);
        uint32_t t1 = get_reference_time();

        printf("%ld %ld %d %lu\n", error, dco_ctl, sw_pll.lock_status, t1 - t0);
    }
}

DECLARE_JOB(sdm_dummy, (chanend_t));
void sdm_dummy(chanend_t c_sdm_control){
    int running = 1;

    int ds_in = 0;
    while(running){
        // Poll for new SDM control value
        SELECT_RES(
            CASE_THEN(c_sdm_control, ctrl_update),
            DEFAULT_THEN(default_handler)
        )
        {
            ctrl_update:
            {
                ds_in = chan_in_word(c_sdm_control);
                fprintf(stderr, "%d\n", ds_in);
            }
            break;

            default_handler:
            {
                // Do nothing & fall-through
            }
            break;
        }
    }
}


int main(int argc, char** argv) {

    channel_t c_sdm_control = chan_alloc();
       
    PAR_JOBS(PJOB(control_task, (argc, argv, c_sdm_control.end_a)),
             PJOB(sdm_dummy, (c_sdm_control.end_a)));

    return 0;
}