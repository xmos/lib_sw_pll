lib_sw_pll library change log
=============================

2.0.0
-----

  * ADDED: Double integral term to controller
  * ADDED: Sigma Delta Modulator option for PLL
  * CHANGED: Refactored Python model into analogous objects

1.1.0
-----

  * ADDED: Function to reset the constants and PI controller state at runtime
  * CHANGED: Framework repositories used by the examples

1.0.0
-----

  * ADDED: Low-level error input API
  * FIXED: Divide by zero exception when not using ref clk compensation

0.3.0
-----

  * ADDED: Documentation
  * ADDED: Simulator can now generate a modulated test tone to measure jitter
  * CHANGED: Updated tools version to 15.2.1

0.2.0
-----

  * REMOVED: support for Kii term (speed optimisation)
  * CHANGED: used pre-calculated divide to improve cycle usage
  * CHANGED: use of const in API
  * FIXED: possible overflow where mclk_inc * refclk_inc is > 32b

0.1.0
-----

  * ADDED: initial version

