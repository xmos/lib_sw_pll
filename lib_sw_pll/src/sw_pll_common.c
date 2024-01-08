// Copyright 2024 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#ifdef __XS3A__

#include "sw_pll.h"

// Implement a delay in 100MHz timer ticks without using a timer resource
static void blocking_delay(const uint32_t delay_ticks){
    uint32_t time_delay = get_reference_time() + delay_ticks;
    while(TIMER_TIMEAFTER(time_delay, get_reference_time()));
}


// Set secondary (App) PLL control register safely to work around chip bug.
void sw_pll_app_pll_init(const unsigned tileid,
                        const uint32_t app_pll_ctl_reg_val,
                        const uint32_t app_pll_div_reg_val,
                        const uint16_t frac_val_nominal)
{
    // Disable the PLL 
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, (app_pll_ctl_reg_val & 0xF7FFFFFF));
    // Enable the PLL to invoke a reset on the appPLL.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);
    // Must write the CTL register twice so that the F and R divider values are captured using a running clock.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);
    // Now disable and re-enable the PLL so we get the full 5us reset time with the correct F and R values.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, (app_pll_ctl_reg_val & 0xF7FFFFFF));
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);

    // Write the fractional-n register and set to nominal
    // We set the top bit to enable the frac-n block.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, (0x80000000 | frac_val_nominal));
    // And then write the clock divider register to enable the output
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM, app_pll_div_reg_val);

    // Wait for PLL to lock.
    blocking_delay(500 * XS1_TIMER_MHZ);
}

#endif // __XS3A__
