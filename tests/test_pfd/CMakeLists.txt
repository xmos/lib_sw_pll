cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(test_pfd)

set(APP_HW_TARGET XCORE-AI-EXPLORER)
set(APP_COMPILER_FLAGS -Os -g -fcmdline-buffer-bytes=256)
set(APP_CXX_SRCS main.c ../../lib_sw_pll/src/sw_pll_pfd.c)

XMOS_REGISTER_APP()