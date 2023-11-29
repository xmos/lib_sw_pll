// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.
///
/// Application to call the control loop with the parameters fully 
/// controllable by an external application. This app expects the 
/// sw_pll_lut_init parameters on the commannd line. These will be integers
/// for lut_table_base, skip the parameter in the list and append the whole
/// lut to the command line
///
/// After init, the app will expect 2 integers to come in over stdin, These
/// are the mclk_pt and ref_pt. It will then run control and print out the 
/// locked state and register value.
///
///
///
#include "xs1.h"
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <sw_pll.h>
#include <stdint.h>
#include <xcore/hwtimer.h>

#define IN_LINE_SIZE 1000

int main(int argc, char** argv) {
    
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
    size_t num_lut_entries = atoi(argv[i++]);
    fprintf(stderr, "num_lut_entries\t\t%d\n", num_lut_entries);
    uint32_t app_pll_ctl_reg_val = atoi(argv[i++]);
    fprintf(stderr, "app_pll_ctl_reg_val\t\t%lu\n", app_pll_ctl_reg_val);
    uint32_t app_pll_div_reg_val = atoi(argv[i++]);
    fprintf(stderr, "app_pll_div_reg_val\t\t%lu\n", app_pll_div_reg_val);
    unsigned nominal_lut_idx = atoi(argv[i++]);
    fprintf(stderr, "nominal_lut_idx\t\t%d\n", nominal_lut_idx);
    unsigned ppm_range = atoi(argv[i++]);
    fprintf(stderr, "ppm_range\t\t%d\n", ppm_range);
    unsigned target_output_frequency = atoi(argv[i++]);
    fprintf(stderr, "target_output_frequency\t\t%d\n", target_output_frequency);

    if(i + num_lut_entries != argc) {
        fprintf(stderr, "wrong number of params sent to main.c in xcore test app\n");        
        return 1;
    }
    int16_t lut_table_base[5000];
    
    fprintf(stderr, "LUT:\n");
    for(int j = 0; j < num_lut_entries; ++j) {
        lut_table_base[j] = atoi(argv[i+j]);
        fprintf(stderr, "%d ", lut_table_base[j]);
    }
    fprintf(stderr, "\n");

    sw_pll_state_t sw_pll;
    sw_pll_lut_init(   &sw_pll,
                       SW_PLL_15Q16(kp),
                       SW_PLL_15Q16(ki),
                       SW_PLL_15Q16(kii),
                       loop_rate_count,
                       pll_ratio,
                       ref_clk_expected_inc,
                       lut_table_base,
                       num_lut_entries,
                       app_pll_ctl_reg_val,
                       app_pll_div_reg_val,
                       nominal_lut_idx,
                       ppm_range);


    for(;;) {

        char read_buf[IN_LINE_SIZE];
        int len = 0;
        for(;;) {
            int val = fgetc(stdin);
            if(EOF == val) {
                return 0;
            }
            if('\n' == val) {
                read_buf[len] = 0;
                break;
            }
            else {
                read_buf[len++] = val;
            }
        }

        uint16_t mclk_pt;
        uint16_t ref_pt;
        sscanf(read_buf, "%hu %hu", &mclk_pt, &ref_pt);
        fprintf(stderr, "%hu %hu\n", mclk_pt, ref_pt);
        uint32_t t0 = get_reference_time();
        sw_pll_lock_status_t s = sw_pll_lut_do_control(&sw_pll, mclk_pt, ref_pt);
        uint32_t t1 = get_reference_time();

        // xsim doesn't support our register and the val that was set gets
        // dropped
        printf("%i %x %hd %ld %ld %u %lu\n", s, sw_pll.lut_state.current_reg_val, sw_pll.pfd_state.mclk_diff, sw_pll.pi_state.error_accum, sw_pll.pi_state.error_accum_accum, sw_pll.first_loop, t1 - t0);
    }
}
