#! /usr/bin/env bash
#
# build stuff

set -ex

cmake -B build -G "Unix Makefiles"
xmake -j 6 -C build

cd tests
# Iterate through 
for d in */ ; do
    cd "$d"
    cmake -B build -G "Unix Makefiles"
    xmake -j 6 -C build
    cd -
done
