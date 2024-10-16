:orphan:

################################
lib_sw_pll: Software PLL library
################################

:vendor: XMOS
:version: 2.3.0
:scope: General Use
:description: PLL functionality using a combination of software and on-device PLL
:category: Audio
:keywords: PLL, clocking
:devices: xcore.ai

********
Overview
********

This library contains software that, together with the `xcore.ai` application PLL, provides a PLL
that will generate a clock that is phase-locked to an input clock.

It supports both Look Up Table (LUT) and Sigma Delta Modulated (SDM) Digitally Controlled
Oscillators (DCO), a Phase Frequency Detector (PFD) and configurable Proportional Integral (PI)
controllers which together form a hybrid Software/Hardware Phase Locked Loop (PLL).

Examples are provided showing a master clock locking to a low frequency input reference clock and
also to an I2S slave interface.

In addition, an API providing a range of fixed clocks supporting common master clock frequencies
between 11.2896 MHz and 49.152 MHz is available in cases where phase locking is not required.

********
Features
********

  * High quality clock recovery using on-board PLL
  * Flexible clock reference (external pin or internal source)
  * Low resource usage
  * Optional Sigma-Delta Modulator
  * Fixed output clock option for typical audio master clocks
  * Hardware locks: fast and power efficient but there are a limited number per tile
  * Software locks: slower but an unlimited number can be used

************
Known Issues
************

  * None

**************
Required Tools
**************

  * XMOS XTC Tools: 15.3.0

*********************************
Required Libraries (dependencies)
*********************************

  * None

*************************
Related Application Notes
*************************

  * None

*******
Support
*******

This package is supported by XMOS Ltd. Issues can be raised against the software at www.xmos.com/support

