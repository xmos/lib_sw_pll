cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(test_app_low_level_api)

set(APP_HW_TARGET           XCORE-AI-EXPLORER)

include(${CMAKE_CURRENT_LIST_DIR}/../test_deps.cmake)

set(APP_COMPILER_FLAGS      -Os
                            -g
                            -report
                            -fcmdline-buffer-bytes=10000  # support for command line params
                            )

set(APP_CXX_SRCS            main.c)


set(XMOS_SANDBOX_DIR        ${CMAKE_CURRENT_LIST_DIR}/../../..)

XMOS_REGISTER_APP()
