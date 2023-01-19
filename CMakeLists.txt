cmake_minimum_required(VERSION 3.21)

## Disable in-source build.
if("${CMAKE_SOURCE_DIR}" STREQUAL "${CMAKE_BINARY_DIR}")
    message(FATAL_ERROR "In-source build is not allowed! Please specify a build folder.\n\tex:cmake -B build")
endif()

## Project declaration
project(lib_sw_pll)

## Enable languages for project
enable_language(CXX C ASM)

## Add library subdirectories
add_subdirectory(lib_sw_pll)


## Add top level project targets
if(PROJECT_IS_TOP_LEVEL)
    include(examples/examples.cmake)
    # Note this assumes we are in a sandbox alongside xcore_sdk
    # TODO ensure this fetches the SDK if this is not true
    add_subdirectory(../xcore_sdk xcore_sdk)
endif()
