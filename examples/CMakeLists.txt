cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(lib_sw_pll_examples)
add_subdirectory(app_fixed_clock)
add_subdirectory(app_i2s_slave_lut)
add_subdirectory(app_simple_lut)
add_subdirectory(app_simple_sdm)

# The mash example is built separately under vx4, so we don't include it here.
# add_subdirectory(app_simple_mash)
