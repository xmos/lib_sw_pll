cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(lib_sw_pll_tests)
# These are just non-mash tests. The mash test is built separately under vx4.
add_subdirectory(test_lut)
add_subdirectory(test_app_sdm_ctrl)
add_subdirectory(test_app_sdm_dco)
add_subdirectory(test_app_low_level_api)
add_subdirectory(test_pfd)
