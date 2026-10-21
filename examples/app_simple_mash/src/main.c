// Copyright 2022-2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <platform.h>
#include <stdio.h>
#include <stdlib.h>
#include <xcore/channel.h>
#include <xcore/parallel.h>
#include <xscope.h>
#include <xs1.h>
#include <netmain.h>

DECLARE_JOB(run_mash_pll, (chanend_t));
DECLARE_JOB(clock_gen, (unsigned, unsigned));
void run_mash_pll(chanend_t c_comms);
void clock_gen(unsigned freq, unsigned duration);



void main_tile_1(void)
{
    xscope_mode_lossless();

    channel_t c_comms = chan_alloc();

    PAR_JOBS(
        PJOB(run_mash_pll, (c_comms.end_a)),
        PJOB(clock_gen, (48000, 100))
    );
    chan_free(c_comms);
    printf("all jobs finished, exiting now.\n");
    exit(0);
}

void main_tile_0(void)
{
    printf("main_tile_0\n");
    return;
}

NETWORK_MAIN(
    TILE_MAIN_VOID(main_tile_1, 1),
    TILE_MAIN_VOID(main_tile_0, 0)
)