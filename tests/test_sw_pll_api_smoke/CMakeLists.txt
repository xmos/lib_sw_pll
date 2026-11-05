cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(test_sw_pll_api_smoke)

include(${CMAKE_CURRENT_LIST_DIR}/../test_deps.cmake)

set(APP_HW_TARGET XK-EVK-XU416)
set(APP_COMPILER_FLAGS -D__VX4B__)
set(XMOS_SANDBOX_DIR ${CMAKE_CURRENT_LIST_DIR}/../../..)

XMOS_REGISTER_APP()