#! /usr/bin/env bash
#
# build stuff

set -ex

cmake -B build -DCMAKE_TOOLCHAIN_FILE=modules/fwk_io/xmos_cmake_toolchain/xs3a.cmake
cmake --build build --target all --target test_app --target test_app_low_level_api --target test_app_sdm_dco --target test_app_sdm_ctrl --target simple_lut --target simple_sdm --target i2s_slave_lut  -j$(nproc)
