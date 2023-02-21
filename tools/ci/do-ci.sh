#! /usr/bin/env bash
#
# build and test stuff

set -ex

cmake -B build -DCMAKE_TOOLCHAIN_FILE=modules/xcore_sdk/xmos_cmake_toolchain/xs3a.cmake -DXCORE_SDK_DIR=modules/xcore_sdk
cmake --build build --target all --target test_app -j$(nproc)

# Build examples
cmake --build build --target all --target simple -j$(nproc)
cmake --build build --target all --target i2s_slave -j$(nproc)

pushd tests
pytest --junitxml=results.xml -rA -v --durations=0 -o junit_logging=all
ls bin
popd

