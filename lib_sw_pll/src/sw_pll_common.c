// Copyright 2024-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include "sw_pll.h"

#if defined(__XS3A__)
// Implement a delay in 100MHz timer ticks without using a timer resource
static void blocking_delay(const uint32_t delay_ticks)
{
    uint32_t time_delay = get_reference_time() + delay_ticks;
    while(TIMER_TIMEAFTER(time_delay, get_reference_time()));
}
#endif

sw_pll_result_t sw_pll_app_pll_init(const uint32_t tile_id,
                        const  uint32_t app_pll_ctl_val,
                        const uint32_t app_pll_div_val,
                        const uint16_t frac_val_nominal,
                        const sw_pll_tile_mask_t tile_mask)
{
    /* Check the tile mask is in range */
    if((tile_mask == 0) || (tile_mask > SW_PLL_TILE_BOTH))
    {
        return SW_PLL_ERR_INVALID_TILE_MASK;
    }

#if defined(__XS3A__)
    /* XS3 only supports outputting PLL1 from tile[1] */
    if (tile_mask != SW_PLL_TILE_1)
    {
        return SW_PLL_ERR_INVALID_TILE_MASK;
    }

    // Set secondary (App) PLL control register safely
    // See XCORE.AI Errata: 18360

    // Disable the PLL
    unsigned app_pll_ctl_reg_val = app_pll_ctl_val;
    app_pll_ctl_reg_val = XS1_SS_APP_PLL_ENABLE_SET(app_pll_ctl_reg_val, 0);
    write_sswitch_reg(tile_id, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, (app_pll_ctl_reg_val));

    // Enable the PLL to invoke a reset on the appPLL.
    app_pll_ctl_reg_val = XS1_SS_APP_PLL_ENABLE_SET(app_pll_ctl_reg_val, 1);
    write_sswitch_reg(tile_id, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);

    // Must write the CTL register twice so that the F and R divider values are captured using a running clock.
    write_sswitch_reg(tile_id, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);

    // Now disable and re-enable the PLL so we get the full 5us reset time with the correct F and R values.
    app_pll_ctl_reg_val = XS1_SS_APP_PLL_ENABLE_SET(app_pll_ctl_reg_val, 0);
    write_sswitch_reg(tile_id, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);
    app_pll_ctl_reg_val = XS1_SS_APP_PLL_ENABLE_SET(app_pll_ctl_reg_val, 1);
    write_sswitch_reg(tile_id, XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_reg_val);

    // Wait for PLL to settle.
    blocking_delay(500 * XS1_TIMER_MHZ);

    // Write the fractional-n register and set to nominal
    // We set the enable bit in the frac-n block.
    unsigned frac_reg_val = (unsigned) XS1_SS_FRAC_N_ENABLE_SET(frac_val_nominal, 1);
    write_sswitch_reg(tile_id, XS1_SSWITCH_SS_APP_PLL_FRAC_N_DIVIDER_NUM, frac_reg_val);

    // And then write the clock divider register to enable the output
    unsigned app_pll_div_reg_val = app_pll_div_val;
    app_pll_div_reg_val = XS1_SS_APP_CLK_FROM_APP_PLL_SET(app_pll_div_reg_val, 1);
    write_sswitch_reg(tile_id, XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM, app_pll_div_reg_val);
#else // VX4 or Above
    xsystem_success_t ret = 0;
    xsystem_tile_id_t xtile_id = (xsystem_tile_id_t) tile_id;
    xsystem_switch_reg_value_t app_pll_ctl_reg_val = VX_PLL1_DISABLE_SET(app_pll_ctl_val, 0);
    app_pll_ctl_reg_val = VX_PLL1_BYPASS_SET(app_pll_ctl_reg_val, 0);
    ret |= sswitch_reg_try_write(xtile_id, VX_SSB_CSR_PLL1_CTRL_NUM, app_pll_ctl_reg_val);

    // APP_CLK0_MUX_BIT/APP_CLK1_MUX_BIT = PLL1 as source
    xsystem_switch_reg_value_t clk_switch_ctrl_val = 0;

    if(tile_mask & SW_PLL_TILE_0)
    {
        clk_switch_ctrl_val = VX_APP_CLK0_MUX_BIT_SET(clk_switch_ctrl_val, 1);
    }
    if(tile_mask & SW_PLL_TILE_1)
    {
        clk_switch_ctrl_val = VX_APP_CLK1_MUX_BIT_SET(clk_switch_ctrl_val, 1);
    }

    ret |= sswitch_reg_try_write(xtile_id, VX_SSB_CSR_CLK_SWITCH_CTRL_NUM, clk_switch_ctrl_val);

    // Set the fractional-n register to nominal value.
    xsystem_switch_reg_value_t fracRegVal = (xsystem_switch_reg_value_t) frac_val_nominal;
    fracRegVal = VX_SS_FRAC_N_ENABLE_SET(fracRegVal, 1);
    ret |= sswitch_reg_try_write(xtile_id, VX_SSB_CSR_PLL1_FRACN_CTRL_NUM, fracRegVal);

    xsystem_switch_reg_value_t app_pll_div_reg_val = VX_APP_CLK_DIV_ENABLE_SET(app_pll_div_val, 1);

    if(tile_mask & SW_PLL_TILE_0)
    {
        ret |= sswitch_reg_try_write(xtile_id, VX_SSB_CSR_APP_CLK0_DIV_NUM, app_pll_div_reg_val);
    }

    if(tile_mask & SW_PLL_TILE_1)
    {
        ret |= sswitch_reg_try_write(xtile_id, VX_SSB_CSR_APP_CLK1_DIV_NUM, app_pll_div_reg_val);
    }
    xassert(ret && "Error: Failed to configure PLL");
#endif

    return SW_PLL_SUCCESS;
}

/* The APP_PLL_CTL_xx defines relate to the SS_APP_PLL_CRL and CSR_PLL1_CTRL registers for XS3A
 * and VX4 respectively.
 *
 * The values relate to the SS_PLL_CTL_POST_DIVISOR/PLL1_OD_DIVIDER, SS_PLL_CTL_FEEDBACK_MUL/
 * PLL_FEEDBACK_MUL and SS_PLL_CTL_INPUT_DIVISOR/PLL_R_DIVIDER fields. These arrangement of these
 * bit fields are shared between XS3A and VX4. Device specific fields such as the enable and bypass
 * bits are not included in these defines and are set in the sw_pll_app_pll_init function.
 *
 * Ideally the OD/F/R values would be separate defines for clarity and to support registers
 * changes in future devices.
 */

//Found solution: IN 24.000MHz, OUT 49.151786MHz, VCO 3145.71MHz, RD 1, FD 131.071 (m = 1, n = 14), OD 8, FOD 2, ERR -4.36ppm
// Measure: 100Hz-40kHz: ~7ps
// 100Hz-1MHz: 70ps.
// 100Hz high pass: 118ps.
#define APP_PLL_CTL_49M  0x03808200
#define APP_PLL_DIV_49M  0x00000001
#define APP_PLL_FRAC_49M 0x0000000D

//Found solution: IN 24.000MHz, OUT 45.157895MHz, VCO 2709.47MHz, RD 1, FD 112.895 (m = 17, n = 19), OD 5, FOD 3, ERR -11.19ppm
// Measure: 100Hz-40kHz: 6.5ps
// 100Hz-1MHz: 67ps.
// 100Hz high pass: 215ps.
#define APP_PLL_CTL_45M  0x02006F00
#define APP_PLL_DIV_45M  0x00000002
#define APP_PLL_FRAC_45M 0x00001012

// Found solution: IN 24.000MHz, OUT 24.576000MHz, VCO 2457.60MHz, RD 1, FD 102.400 (m = 2, n = 5), OD 5, FOD 5, ERR 0.0ppm
// Measure: 100Hz-40kHz: ~8ps
// 100Hz-1MHz: 63ps.
// 100Hz high pass: 127ps.
#define APP_PLL_CTL_24M  0x02006500
#define APP_PLL_DIV_24M  0x00000004
#define APP_PLL_FRAC_24M 0x00000104

// Found solution: IN 24.000MHz, OUT 1.536000MHz, VCO 2457.60MHz, RD  1, FD  102, FRAC 0.400 (m =   2, n =   5), OD  5, FOD   80, ERR 0.0ppm
#define APP_PLL_CTL_1M536  0x02006500
#define APP_PLL_DIV_1M536  0x0000004F
#define APP_PLL_FRAC_1M536 0x00000104

// Found solution: IN 24.000MHz, OUT 3.072000MHz, VCO 2457.60MHz, RD  1, FD  102, FRAC 0.400 (m =   2, n =   5), OD  5, FOD   40, ERR 0.0ppm
#define APP_PLL_CTL_3M072  0x02006500
#define APP_PLL_DIV_3M072  0x00000027
#define APP_PLL_FRAC_3M072 0x00000104

// Found solution: IN 24.000MHz, OUT 6.144000MHz, VCO 2457.60MHz, RD  1, FD  102, FRAC 0.400 (m =   2, n =   5), OD  5, FOD   20, ERR 0.0ppm
#define APP_PLL_CTL_6M144  0x02006500
#define APP_PLL_DIV_6M144  0x00000013
#define APP_PLL_FRAC_6M144 0x00000104

// Found solution: IN 24.000MHz, OUT 22.579186MHz, VCO 3522.35MHz, RD 1, FD 146.765 (m = 13, n = 17), OD 3, FOD 13, ERR -0.641ppm
// Measure: 100Hz-40kHz: 7ps
// 100Hz-1MHz: 67ps.
// 100Hz high pass: 260ps.
#define APP_PLL_CTL_22M  0x01009100
#define APP_PLL_DIV_22M  0x0000000C
#define APP_PLL_FRAC_22M 0x00000C10

#define APP_PLL_CTL_12M  0x02006500
#define APP_PLL_DIV_12M  0x00000009
#define APP_PLL_FRAC_12M 0x00000104

#define APP_PLL_CTL_11M  0x01009100
#define APP_PLL_DIV_11M  0x00000019
#define APP_PLL_FRAC_11M 0x00000C10

// Setup a fixed clock (not phase locked)
sw_pll_result_t sw_pll_fixed_clock(const unsigned frequency, const sw_pll_tile_mask_t tile_mask)
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
        
        case 768000*2:
            ctrl = APP_PLL_CTL_1M536;
            div = APP_PLL_DIV_1M536;
            frac = APP_PLL_FRAC_1M536;
            break;

        case 768000*4:
            ctrl = APP_PLL_CTL_3M072;
            div = APP_PLL_DIV_3M072;
            frac = APP_PLL_FRAC_3M072;
            break;

        case 768000*8:
            ctrl = APP_PLL_CTL_6M144;
            div = APP_PLL_DIV_6M144;
            frac = APP_PLL_FRAC_6M144;
            break;

        case 0:
        {
#if defined (__XS3A__)
            // Briefly turn on if not on already so we can write to XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM
            // Set a low but valid PLL config
            write_sswitch_reg(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_CTL_NUM, APP_PLL_CTL_11M);

            // Bit 16 high - X1D11 is XS1_PORT_1D. Other bits don't care/set to high divider
            uint32_t app_clk_div_reg_val = 0;
            app_clk_div_reg_val = XS1_SS_APP_CLK_DIV_SET(app_clk_div_reg_val, XS1_SS_APP_CLK_DIV_MASK);
            app_clk_div_reg_val = XS1_SS_APP_CLK_DIV_DISABLE_SET(app_clk_div_reg_val, 1);
            app_clk_div_reg_val = XS1_SS_APP_CLK_FROM_APP_PLL_SET(app_clk_div_reg_val, 1);

            write_sswitch_reg(get_local_tile_id(), XS1_SSWITCH_SS_APP_CLK_DIVIDER_NUM, app_clk_div_reg_val);

            // Disable APP PLL
            // - Do not bypass APP PLL
            // - Other bits: 'don't care'
            uint32_t app_pll_ctl_val = XS1_SS_PLL_CTL_INPUT_DIVISOR_SET(0, 0x63);
            app_pll_ctl_val = XS1_SS_PLL_CTL_FEEDBACK_MUL_SET(app_pll_ctl_val, 0x1FFF);
            app_pll_ctl_val = XS1_SS_PLL_CTL_POST_DIVISOR_SET(app_pll_ctl_val, 0x7);
            app_pll_ctl_val = XS1_SS_APP_PLL_ENABLE_SET(app_pll_ctl_val, 0);
            app_pll_ctl_val = XS1_SS_APP_PLL_INPUT_FROM_SYS_PLL_SET(app_pll_ctl_val, 0x1);
            app_pll_ctl_val = XS1_SS_APP_PLL_BYPASS_SET(app_pll_ctl_val, 0);

            write_sswitch_reg(get_local_tile_id(), XS1_SSWITCH_SS_APP_PLL_CTL_NUM, app_pll_ctl_val);
#else
            xsystem_tile_id_t xtile_id = get_local_tile_id();

            /* Disable divider for both tiles - this puts the port back to port mode */
            xsystem_switch_reg_value_t app_pll_div_reg_val = VX_APP_CLK_DIV_VALUE_SET(0, 0);
            app_pll_div_reg_val = VX_APP_CLK_DIV_ENABLE_SET(app_pll_div_reg_val, 0);

            sswitch_reg_try_write(xtile_id, VX_SSB_CSR_APP_CLK1_DIV_NUM, app_pll_div_reg_val);
            sswitch_reg_try_write(xtile_id, VX_SSB_CSR_APP_CLK0_DIV_NUM, app_pll_div_reg_val);

            /* Put the muxes back to default state */
            /* TODO read modify write? Otherwise might causes issues with DDR etc */
            xsystem_switch_reg_value_t clk_switch_ctrl_val = 0;
            clk_switch_ctrl_val = VX_REF_CLK_MUX_BIT_SET(clk_switch_ctrl_val, 0); // 0: XTAL, 1: RC_OSC
            clk_switch_ctrl_val = VX_SYSTEM_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_APP_CLK0_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_APP_CLK1_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_DDR_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_MIPI_CFG_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_MIPI_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_USB_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_APP_CLK_SYNC_MUX_BIT_SET(clk_switch_ctrl_val, 0);
            clk_switch_ctrl_val = VX_APP_CLK_IN_PHASE_BIT_SET(clk_switch_ctrl_val, 0);
            sswitch_reg_try_write(xtile_id, VX_SSB_CSR_CLK_SWITCH_CTRL_NUM, clk_switch_ctrl_val);

            /* Disable the fractional N divider */
            xsystem_switch_reg_value_t fracRegVal = 0;
            fracRegVal = VX_SS_FRAC_N_PERIOD_CYC_CNT_SET(fracRegVal, 0);
            fracRegVal = VX_SS_FRAC_N_F_HIGH_CYC_CNT_SET(fracRegVal, 0);
            fracRegVal = VX_SS_FRAC_N_ENABLE_SET(fracRegVal, 0);
            sswitch_reg_try_write(xtile_id, VX_SSB_CSR_PLL1_FRACN_CTRL_NUM, fracRegVal);

            /* Disable secondary PLL */
            /* Note, must set BYPASS bit before setting the DISABLE bit. Setting the DISABLE
             * bit without being in BYPASS will mean there is no clock to allow the write to
             * complete */
            xsystem_switch_reg_value_t app_pll_ctl_reg_val = 0;
            app_pll_ctl_reg_val = VX_PLL1_R_DIVIDER_SET(app_pll_ctl_reg_val, 0);
            app_pll_ctl_reg_val = VX_PLL1_F_MULTIPLIER_SET(app_pll_ctl_reg_val, 0);
            app_pll_ctl_reg_val = VX_PLL1_OD_DIVIDER_SET(app_pll_ctl_reg_val, 0);
            app_pll_ctl_reg_val = VX_PLL1_DISABLE_SET(app_pll_ctl_reg_val, 0);
            app_pll_ctl_reg_val = VX_PLL1_BYPASS_SET(app_pll_ctl_reg_val, 1);
            app_pll_ctl_reg_val = VX_PLL1_NLOCK_SET(app_pll_ctl_reg_val, 0);
            sswitch_reg_try_write(xtile_id, VX_SSB_CSR_PLL1_CTRL_NUM, app_pll_ctl_reg_val);

            app_pll_ctl_reg_val = VX_PLL1_DISABLE_SET(app_pll_ctl_reg_val, 0);
            sswitch_reg_try_write(xtile_id, VX_SSB_CSR_PLL1_CTRL_NUM, app_pll_ctl_reg_val);
#endif
            return SW_PLL_SUCCESS;
        }

        default:
            return SW_PLL_ERR_INVALID_FREQUENCY; // Invalid frequency requested
    }

    return sw_pll_app_pll_init(get_local_tile_id(), ctrl, div, (uint16_t)frac, tile_mask);
}
