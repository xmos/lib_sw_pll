// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <stdio.h>
#include "resource_setup.h"

void setup_ref_and_mclk_ports_and_clocks(port_t p_mclk, xclock_t clk_mclk, port_t p_clock_counter, xclock_t clk_ref_clk, port_t p_ref_clk_timing)
{
    // Create clock from mclk port and use it to clock the p_clock_counter port.
    clock_enable(clk_mclk);
    port_enable(p_mclk);
    clock_set_source_port(clk_mclk, p_mclk);

    // Clock p_clock_counter from MCLK
    port_enable(p_clock_counter);
    port_set_clock(p_clock_counter, clk_mclk);

    clock_start(clk_mclk);

    // Create clock from ref_clock_port and use it to clock the p_clock_counter port.
    clock_enable(clk_ref_clk);
    clock_set_source_port(clk_ref_clk, p_clock_counter);
    port_enable(p_ref_clk_timing);
    port_set_clock(p_ref_clk_timing, clk_ref_clk);

    clock_start(clk_ref_clk);
}


void setup_recovered_ref_clock_output(port_t p_recovered_ref_clk, xclock_t clk_recovered_ref_clk, port_t p_mclk, unsigned divider)
{
    // Connect clock block with divide to mclk
    clock_enable(clk_recovered_ref_clk);
    clock_set_source_port(clk_recovered_ref_clk, p_mclk);
    clock_set_divide(clk_recovered_ref_clk, divider / 2);
    printf("Divider: %u\n", divider);

    // Output the divided mclk on a port
    port_enable(p_recovered_ref_clk);
    port_set_clock(p_recovered_ref_clk, clk_recovered_ref_clk);
    port_set_out_clock(p_recovered_ref_clk);
    clock_start(clk_recovered_ref_clk);
}