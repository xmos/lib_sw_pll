lib_sw_pll library change log
=============================

0.2.0
-----

  * REMOVED: support for Kii term (speed optimisation)
  * CHANGED: used pre-calculated divide to improve cycle usage
  * CHANGED: use of const in API
  * FIXED: possible overflow where mclk_inc * refclk_inc is > 32b

0.1.0
-----

  * ADDED: initial version

