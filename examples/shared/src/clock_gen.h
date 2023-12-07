// Copyright 2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

// Runs a task in a thread that produces a clock that sweeps a reference clock
// between + and - the ppm value specified. 
//
// param ref_frequency  Nominal frequency in Hz
// param ppm_range      The range to sweep
void clock_gen(unsigned ref_frequency, unsigned ppm_range);