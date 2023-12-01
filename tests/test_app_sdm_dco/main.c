// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.
///
/// Application to call the control loop with the parameters fully 
/// controllable by an external application. This app expects the 
/// sw_pll_init parameters on the commannd line. These will be integers
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
    
    sw_pll_sdm_state_t sdm_state;
    sw_pll_init_sigma_delta(&sdm_state);

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

        int32_t ds_in;
        sscanf(read_buf, "%ld", &ds_in);
        // fprintf(stderr, "%ld\n", ds_in);

        // calc new ds_out and then wait to write
        uint32_t t0 = get_reference_time();
        int32_t ds_out = sw_pll_calc_sigma_delta(&sdm_state, ds_in);
        uint32_t frac_val = sw_pll_sdm_out_to_frac_reg(ds_out);
        uint32_t t1 = get_reference_time();

        printf("%ld %lu %lu\n", ds_out, frac_val, t1 - t0);
    }
}
