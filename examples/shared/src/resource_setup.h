// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <xcore/port.h>

#pragma once

// Sets up the provided resources so that we can count PLL output clocks.
// We do this by clocking the input reference clock port with the output from the PLL
// and its internal counter is used to count the PLL clock cycles(normal timers cannot count custom clocks)
// It also sets up a dummy port clocked by the input reference to act as a timing barrier so that 
// the output clock count can be precisely sampled. 
void setup_ref_and_mclk_ports_and_clocks(port_t p_mclk, xclock_t clk_mclk, port_t p_ref_clk_in, xclock_t clk_word_clk, port_t p_ref_clk_count);

// Sets up a divided version of the PLL output so it can visually be compared (eg. on a DSO)
// with the input reference clock to the PLL
void setup_recovered_ref_clock_output(port_t p_recovered_ref_clk, xclock_t clk_recovered_ref_clk, port_t p_mclk, unsigned divider);