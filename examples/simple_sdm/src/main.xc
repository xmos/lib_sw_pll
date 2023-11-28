// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <platform.h>
#include <xs1.h>
#include <stdlib.h>

extern void sw_pll_sdm_test(chanend c_sdm_control);
extern void sdm_task(chanend c_sdm_control);
extern "C" {
    #include "clock_gen.h"
}

int main(void)
{
    chan c_sdm_control;

    par
    {
        on tile[0]: par {
        }

        on tile[1]: par {
            sw_pll_sdm_test(c_sdm_control);
            sdm_task(c_sdm_control);
            {
                clock_gen(96000, 300);
                exit(0);
            }
        }
    }
  return 0;
}
