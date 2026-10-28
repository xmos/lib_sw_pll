// Copyright 2022-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <inttypes.h>
#include <stdio.h>
#include <platform.h>
#include <xs1.h>
#include <xcore/channel.h>
#include <xcore/port.h>

#include "sw_pll.h"
#include "register_setup.h"
#include "resource_setup.h"


#define MCLK_FREQUENCY              12288000
#define REF_FREQUENCY               48000
#define PLL_RATIO                   (MCLK_FREQUENCY / REF_FREQUENCY)
#define CONTROL_LOOP_COUNT          512
#define PPM_RANGE                   10000


#define PORT_MCLK_IN                XS1_PORT_1D  // X1D11
#define PORT_INPUT_REF_CLK          XS1_PORT_1F  // X1D13
#define PORT_RECOVERED_REF_CLK      XS1_PORT_1E  // X1D12
#define PORT_REF_CLK_COUNTER        XS1_PORT_32A // Unused port

void run_mash_pll(chanend_t c_comms)
{
    port_t p_mclk = PORT_MCLK_IN;
    xclock_t clk_mclk = XS1_CLKBLK_1;
    port_t p_clock_counter = PORT_INPUT_REF_CLK;
    xclock_t clk_ref_clk = XS1_CLKBLK_2;
    port_t p_ref_clk_timing = PORT_REF_CLK_COUNTER;
    setup_ref_and_mclk_ports_and_clocks(p_mclk, clk_mclk, p_clock_counter, clk_ref_clk, p_ref_clk_timing);

    puts("3");

    xclock_t clk_recovered_ref_clk = XS1_CLKBLK_3;
    port_t p_recovered_ref_clk = PORT_RECOVERED_REF_CLK;
    setup_recovered_ref_clock_output(p_recovered_ref_clk, clk_recovered_ref_clk, p_mclk, PLL_RATIO);

    puts("4");

    sw_pll_state_t sw_pll;
    sw_pll_result_t error = sw_pll_mash_init(&sw_pll,
                SW_PLL_15Q16(150.0),
                SW_PLL_15Q16(50.0),
                SW_PLL_15Q16(1.00),
                CONTROL_LOOP_COUNT,
                PLL_RATIO,
                0,
                APP_PLL_CTL_REG,
                APP_PLL_DIV_REG,
                APP_PLL_MASH_REG,
                PPM_RANGE,
                SW_PLL_TILE_1);

    if(error != SW_PLL_SUCCESS)
    {
        printf("Error setting up PLL: %d\n", error);
        return;
    }

    sw_pll_lock_status_t lock_status = SW_PLL_LOCKED;
    uint32_t max_time = 0;

    for(;;)
    {
        // This blocks each time round the loop until it can sample input (rising edges of word clock).
        // So we know the count will be +1 each time.
        port_in(p_ref_clk_timing); 
        // Get the port timer val from p_clock_counter (which is running from MCLK).
        // So this is basically a 16 bit free running counter running from MCLK.
        uint16_t mclk_pt = port_get_trigger_time(p_clock_counter);

        uint32_t t0 = get_reference_time();
        sw_pll_lock_status_t current_lock_status = sw_pll_mash_do_control(&sw_pll, mclk_pt, 0);
        uint32_t t1 = get_reference_time();

        if(t1 - t0 > max_time)
        {
            max_time = t1 - t0;
            printf("Max ticks taken: %" PRIu32 "\n", max_time);
        }

        if(current_lock_status != lock_status)
        {
            lock_status = current_lock_status;
            const char msg[3][16] = {"UNLOCKED LOW", "LOCKED", "UNLOCKED HIGH"};
            printf("%s\n", msg[lock_status + 1]);
        }
    }
}