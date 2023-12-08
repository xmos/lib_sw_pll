#! /usr/bin/env bash
#
# test stuff

set -ex

pushd python/sw_pll
python sw_pll_sim.py LUT
python sw_pll_sim.py SDM
popd

