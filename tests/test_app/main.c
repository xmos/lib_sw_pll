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

#define IN_LINE_SIZE 1000

int main(int argc, char** argv) {
    
    int i = 1;

    sw_pll_15q16_t kp = atoi(argv[i++]);
    sw_pll_15q16_t ki = atoi(argv[i++]);
    sw_pll_15q16_t kii = atoi(argv[i++]);
    size_t loop_rate_count = atoi(argv[i++]);
    size_t pll_ratio = atoi(argv[i++]);
    uint32_t ref_clk_expected_inc = atoi(argv[i++]);
    size_t num_lut_entries = atoi(argv[i++]);
    uint32_t app_pll_ctl_reg_val = atoi(argv[i++]);
    uint32_t app_pll_div_reg_val = atoi(argv[i++]);
    unsigned nominal_lut_idx = atoi(argv[i++]);
    unsigned ppm_range = atoi(argv[i++]);

    if(i + num_lut_entries != argc) {
        return 1; // wrong number of params
    }
    int16_t lut_table_base[5000];

    for(int j = 0; j < num_lut_entries; ++j) {
        lut_table_base[j] = atoi(argv[i+j]);
    }

    sw_pll_state_t sw_pll;
    sw_pll_init(   &sw_pll,
                   kp,
                   ki,
                   kii,
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
        sw_pll_lock_status_t s = sw_pll_do_control(&sw_pll, mclk_pt, ref_pt);

        // xsim doesn't support our register and the val that was set gets
        // dropped
        printf("%i %x\n", s, sw_pll.current_reg_val);
    }
}
