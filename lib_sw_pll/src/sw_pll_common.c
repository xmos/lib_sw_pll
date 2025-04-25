// Copyright 2024-2025 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#ifdef __XS3A__

#include "sw_pll.h"

// Implement a delay in 100MHz timer ticks without using a timer resource
static void blocking_delay(const uint32_t delay_ticks)
{
    uint32_t time_delay = get_reference_time() + delay_ticks;
    while(TIMER_TIMEAFTER(time_delay, get_reference_time()));
}


// Set secondary (App) PLL control register safely to work around chip bug.
// See http://bugzilla/show_bug.cgi?id=18380
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

    // Wait for PLL to settle.
    blocking_delay(500 * XS1_TIMER_MHZ);

    // Write the fractional-n register and set to nominal
    // We set the top bit to enable the frac-n block.
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, (0x80000000 | frac_val_nominal));
    // And then write the clock divider register to enable the output
    write_sswitch_reg(tileid, XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM, app_pll_div_reg_val);
}


//Found solution: IN 24.000MHz, OUT 49.151786MHz, VCO 3145.71MHz, RD 1, FD 131.071 (m = 1, n = 14), OD 8, FOD 2, ERR -4.36ppm
// Measure: 100Hz-40kHz: ~7ps
// 100Hz-1MHz: 70ps.
// 100Hz high pass: 118ps.
#define APP_PLL_CTL_49M  0x0B808200
#define APP_PLL_DIV_49M  0x80000001
#define APP_PLL_FRAC_49M 0x8000000D

//Found solution: IN 24.000MHz, OUT 45.157895MHz, VCO 2709.47MHz, RD 1, FD 112.895 (m = 17, n = 19), OD 5, FOD 3, ERR -11.19ppm
// Measure: 100Hz-40kHz: 6.5ps
// 100Hz-1MHz: 67ps.
// 100Hz high pass: 215ps.
#define APP_PLL_CTL_45M  0x0A006F00
#define APP_PLL_DIV_45M  0x80000002
#define APP_PLL_FRAC_45M 0x80001012

// Found solution: IN 24.000MHz, OUT 24.576000MHz, VCO 2457.60MHz, RD 1, FD 102.400 (m = 2, n = 5), OD 5, FOD 5, ERR 0.0ppm
// Measure: 100Hz-40kHz: ~8ps
// 100Hz-1MHz: 63ps.
// 100Hz high pass: 127ps.
#define APP_PLL_CTL_24M  0x0A006500
#define APP_PLL_DIV_24M  0x80000004
#define APP_PLL_FRAC_24M 0x80000104

// Found solution: IN 24.000MHz, OUT 22.579186MHz, VCO 3522.35MHz, RD 1, FD 146.765 (m = 13, n = 17), OD 3, FOD 13, ERR -0.641ppm
// Measure: 100Hz-40kHz: 7ps
// 100Hz-1MHz: 67ps.
// 100Hz high pass: 260ps.
#define APP_PLL_CTL_22M  0x09009100
#define APP_PLL_DIV_22M  0x8000000C
#define APP_PLL_FRAC_22M 0x80000C10

#define APP_PLL_CTL_12M  0x0A006500
#define APP_PLL_DIV_12M  0x80000009
#define APP_PLL_FRAC_12M 0x80000104

#define APP_PLL_CTL_11M  0x09009100
#define APP_PLL_DIV_11M  0x80000019
#define APP_PLL_FRAC_11M 0x80000C10

// Disable APP PLL setting
// Sets bit 29 to zero (do not bypass APP PLL)
//      bit 27 to zero (disable APP PLL)
// Other bits don't care
#define APP_PLL_CTL_OFF         0xD7FFFFFF
// Sets low but valid PLL config
#define APP_PLL_CTL_ON          APP_PLL_CTL_11M
// Bit 16 high - X1D11 is XS1_PORT_1D. Other bits don't care/set to high divider
#define APP_PLL_DIV_PORT_MODE   0xFFFFFFFF

// Setup a fixed clock (not phase locked)
void sw_pll_fixed_clock(const unsigned frequency)
{   
    unsigned ctrl = 0;
    unsigned div = 0;
    unsigned frac = 0;


    switch(frequency)
    {
        case 44100*256:
            ctrl = APP_PLL_CTL_11M;
            div = APP_PLL_DIV_11M;
            frac = APP_PLL_FRAC_11M;
            break;

         case 48000*256:
            ctrl = APP_PLL_CTL_12M;
            div = APP_PLL_DIV_12M;
            frac = APP_PLL_FRAC_12M;
            break;

        case 44100*512:
            ctrl = APP_PLL_CTL_22M;
            div = APP_PLL_DIV_22M;
            frac = APP_PLL_FRAC_22M;
            break;

        case 48000*512:
            ctrl = APP_PLL_CTL_24M;
            div = APP_PLL_DIV_24M;
            frac = APP_PLL_FRAC_24M;
            break;

        case 44100*1024:
            ctrl = APP_PLL_CTL_45M;
            div = APP_PLL_DIV_45M;
            frac = APP_PLL_FRAC_45M;
            break;

        case 48000*1024:
            ctrl = APP_PLL_CTL_49M;
            div = APP_PLL_DIV_49M;
            frac = APP_PLL_FRAC_49M;
            break;

        case 0:
            // Briefly turn on if not on already so we can write to XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM
            write_sswitch_reg(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_CTL_NUM, APP_PLL_CTL_ON);
            // Set pin to port mode
            write_sswitch_reg(get_local_tile_id(), XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM, APP_PLL_DIV_PORT_MODE);
            // Disable APP PLL
            write_sswitch_reg(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_CTL_NUM, APP_PLL_CTL_OFF);
            return;
            break;

        default:
            xassert(0);
            break;
    }

    sw_pll_app_pll_init(get_local_tile_id(), ctrl, div, frac);
}


#endif // __XS3A__
