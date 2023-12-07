// Copyright 2022-2023 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <platform.h>
#include <xs1.h>
#include <stdlib.h>

extern void sw_pll_test(void);
extern "C" {
    #include "clock_gen.h"
}


int main(void)
{
    par
    {
        on tile[0]: par {
        }
        on tile[1]: par {
            sw_pll_test();
            {
                clock_gen(48000, 500);
                exit(0);
            }
        }
    }
  return 0;
}
