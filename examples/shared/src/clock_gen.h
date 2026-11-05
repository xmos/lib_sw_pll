// Copyright 2023-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

// Runs a task in a thread that produces a clock that sweeps a reference clock
// between + and - the ppm value specified. 
//
// param ref_frequency  Nominal frequency in Hz
// param ppm_range      The range to sweep
// param clock_port     Port on which to generate the clock
void clock_gen_on_i2s_bclk(unsigned ref_frequency, unsigned ppm_range);

#ifndef __XC__
#include <xcore/port.h>
void clock_gen(unsigned ref_frequency, unsigned ppm_range, port_t clock_port);
#endif
