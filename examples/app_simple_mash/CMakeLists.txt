cmake_minimum_required(VERSION 3.21)
include($ENV{XMOS_CMAKE_PATH}/xcommon.cmake)
project(app_simple_mash)

set(APP_HW_TARGET           XK-EVK-XU416)

include(${CMAKE_CURRENT_LIST_DIR}/../deps.cmake)

set(APP_COMPILER_FLAGS      -Os
                            -g
                            -report
                            -DDEBUG_PRINT_ENABLE=1
                            -DPORT_I2S_BCLK=XS1_PORT_1B   # ovveride bclk output port in clockgen
)

set(APP_XSCOPE_SRCS         src/config.xscope)

set(APP_CXX_SRCS            src/main.c
                            src/simple_mash.c
                            ../shared/src/clock_gen.c
                            ../shared/src/resource_setup.c)

set(APP_INCLUDES            ../shared/src)

set(XMOS_SANDBOX_DIR        ${CMAKE_CURRENT_LIST_DIR}/../../..)

XMOS_REGISTER_APP()
