#! /usr/bin/env bash
#
# build and test stuff

set -ex

pushd tests
pytest --junitxml=results.xml -rA -v --durations=0 -o junit_logging=all
ls bin
popd

