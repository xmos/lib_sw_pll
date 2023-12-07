// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <xcore/port.h>

#pragma once

// Sets up the provided resources so that we can count PLL output clocks.
// We do this by clocking the input reference clock port with the output from the PLL
// and its internal counter is used to count the PLL clock cycles(normal timers cannot count custom clocks)
// It also sets up a dummy port clocked by the input reference to act as a timing barrier so that 
// the output clock count can be precisely sampled. 
//
// param p_mclk             The mclk output port (Always P1D on tile[1])
// param clk_mclk           The clockblock for mclk out 
// param p_clock_counter    The port used for counting mclks - in this case the ref input clock
// param clk_ref_clk        The clockblock for the timing barrier
// param p_ref_clk_timing   The port used for t he timing barrier
void setup_ref_and_mclk_ports_and_clocks(port_t p_mclk, xclock_t clk_mclk, port_t p_clock_counter, xclock_t clk_ref_clk, port_t p_ref_clk_timing);

// Sets up a divided version of the PLL output so it can visually be compared (eg. on a DSO)
// with the input reference clock to the PLL
//
// param p_recovered_ref_clk    The port used to drive the recovered and divided clock
// param clk_recovered_ref_clk  The clockblock used to drive the recovered and divided clock 
// param p_mclk                 The mclk output port (Always P1D on tile[1])
// param divider                The divide value from mclk to the divided output
void setup_recovered_ref_clock_output(port_t p_recovered_ref_clk, xclock_t clk_recovered_ref_clk, port_t p_mclk, unsigned divider);