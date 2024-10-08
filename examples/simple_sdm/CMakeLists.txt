cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(app_simple_sdm)

set(APP_HW_TARGET           XCORE-AI-EXPLORER)

include(${CMAKE_CURRENT_LIST_DIR}/../deps.cmake)

set(APP_COMPILER_FLAGS      -Os
                            -g
                            -report
                            -DDEBUG_PRINT_ENABLE=1)

set(APP_XSCOPE_SRCS         src/config.xscope)

set(APP_CXX_SRCS            src/simple_sw_pll_sdm.c
                            src/main.xc
                            ../shared/src/clock_gen.c
                            ../shared/src/resource_setup.c)

set(APP_INCLUDES            ../shared/src)

set(XMOS_SANDBOX_DIR        ${CMAKE_CURRENT_LIST_DIR}/../../..)

XMOS_REGISTER_APP()


