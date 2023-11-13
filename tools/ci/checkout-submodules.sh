#! /usr/bin/env bash
#
# clone required repos and install python packages needed by ci

# clone NAME URL HASH
#
# supposedly, this is the quickest way to clone a single
# commit from a remote git repo
clone() {
    mkdir $1
    pushd $1
    git init
    git remote add origin $2
    git fetch --depth 1 origin $3
    git checkout FETCH_HEAD
    git submodule update --init --recursive --depth 1 --jobs $(nproc)
    popd
}

set -ex
rm -rf modules
mkdir -p modules
pushd modules

clone fwk_core        git@github.com:xmos/fwk_core.git        v1.0.2
clone fwk_io          git@github.com:xmos/fwk_io.git          v3.3.0

clone infr_scripts_py git@github.com:xmos/infr_scripts_py.git v1.2.1
clone infr_apps       git@github.com:xmos/infr_apps.git       v1.4.6 

pip install -e infr_apps -e infr_scripts_py
popd
