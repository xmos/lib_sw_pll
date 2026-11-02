cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(test_pfd)

set(APP_HW_TARGET XCORE-AI-EXPLORER)
set(APP_COMPILER_FLAGS -Os -g)
set(APP_CXX_SRCS main.c)

XMOS_REGISTER_APP()