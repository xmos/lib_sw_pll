Software PLL Library 
===================

Overview
--------

This library contains software that, together with the on-chip application PLL, provides a PLL that will generate a clock that is phase-locked to an input clock.

It supports both Look Up Table (LUT) and Sigma Delta Modulated (SDM) Digitally Controlled Oscillators (DCO), a Phase Frequency Detector (PFD) and
configurable Proportional Integral (PI) controllers which together form a hybrid Software/Hardware Phase Locked Loop (PLL).

Examples are provided showing a master clock locking to a low frequency input reference clock and also to an I2S slave interface.

In addition, an API providing a range of fixed clocks supporting common master clock frequencies between 11.2896 MHz and 49.152 MHz is available 
in cases where phase locking is not required.

Features
........

    * High quality clock recovery using on-board PLL
    * Flexible clock reference (external pin or internal source)
    * Low resource usage
    * Optional Sigma-Delta Modulator
    * Fixed output clock option for typical audio master clocks

Software version and dependencies
.................................

The CHANGELOG contains information about the current and previous versions.
For a list of direct dependencies, look for DEPENDENT_MODULES in lib_sw_pll/module_build_info.