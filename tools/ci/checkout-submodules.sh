#! /usr/bin/env bash
#
# clone required repos and install python packages needed by ci

# clone NAME URL HASH
#
# supposedly, this is the quickest way to clone a single
# commit from a remote git repo
clone() {
    mkdir $1
    cd $1
    git init
    git remote add origin $2
    git fetch --depth 1 origin $3
    git checkout FETCH_HEAD
    git submodule update --init --recursive --depth 1 --jobs $(nproc)
    cd -
}

set -ex
rm -rf modules
mkdir -p modules
cd modules
clone infr_scripts_py git@github.com:xmos/infr_scripts_py.git 1d767cbe89a3223da7a4e27c283fb96ee2a279c9
clone infr_apps       git@github.com:xmos/infr_apps.git       8bc62324b19a1ab32b1e5a5e262f40f710f9f5c1 
clone xcore_sdk       git@github.com:xmos/xcore_sdk.git       a305fcf5ec3d00acd385ddee8fd681b0d855a059

pip install -e infr_apps -e infr_scripts_py
cd -
