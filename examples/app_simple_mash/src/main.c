// Copyright 2022-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <platform.h>
#include <stdio.h>
#include <stdlib.h>
#include <xcore/channel.h>
#include <xcore/parallel.h>
#include <xscope.h>

#include "clock_gen.h"
DECLARE_JOB(clock_gen, (unsigned, unsigned, port_t));

DECLARE_JOB(run_mash_pll, (chanend_t));
void run_mash_pll(chanend_t c_comms);



int main(void)
{
    xscope_mode_lossless();

    channel_t c_comms = chan_alloc();

    PAR_JOBS(
        PJOB(run_mash_pll, (c_comms.end_a)),
        PJOB(clock_gen, (48000, 100, XS1_PORT_1O)) // X0D38 on board
    );
    chan_free(c_comms);
    printf("all jobs finished, exiting now.\n");
    return(0);
}