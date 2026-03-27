// Copyright 2026 XMOS LIMITED.
// This Software is subject to the terms of the XMOS Public Licence: Version 1.

#include <platform.h>

void fixed_clock(void);

int main(void)
{
    par
    {
        on tile[1]: fixed_clock();
    }

    return 0;
}
