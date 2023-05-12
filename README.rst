lib_sw_pll
==========

This library contains software that, together with the on-chip application PLL, provides a PLL that will generate a clock phase locked to an input clock.

********************************
Building and running the example
********************************

Ensure a correctly configured installation of the XMOS tools.

.. note::
    Instructions for installing and configuring the XMOS tools appear on `the XMOS web site <https://www.xmos.ai/software-tools/>`_.

Place the fwk_core and fwk_io repositories in the modules directory of lib_sw_pll.
To do so, from the root of lib_sw_pll (where this read me file exists) type::

    mkdir modules
    pushd modules
    git clone --recurse-submodules git@github.com:xmos/fwk_core.git
    git clone --recurse-submodules git@github.com:xmos/fwk_io.git
    popd

.. note::
    The fwk_core and fwk_io repositories have not been sub-moduled into this Git repository because only the examples depend upon them.

Run the following commands in the lib_sw_pll root folder to build the firmware.

On linux::

    cmake -B build -DCMAKE_TOOLCHAIN_FILE=modules/fwk_io/xmos_cmake_toolchain/xs3a.cmake
    cd build
    make simple

On Windows::

    cmake -G "NMake Makefiles" -B build -DCMAKE_TOOLCHAIN_FILE=modules/fwk_io/xmos_cmake_toolchain/xs3a.cmake
    cd build
    nmake simple


To run the firmware, first connect LRCLK and BCLK (connects the test clock output to the PLL input)
and run the following command where <my_example> can be *simple* which uses the XCORE-AI-EXPLORER board
or *i2s_slave* which uses either the EVK3600 of EVK3800 board::

    xrun --xscope <my_example>.xe


For simple.xe, to see the PLL lock, put one scope probe on either LRCLK/BCLK (reference) and the other on PORT_I2S_DAC_DATA to see the 
recovered clock which has been hardware divided back down to the same rate as the input clock.

For i2s_slave.xe you will need to connect a 48kHz I2S master to the LRCLK, BCLK pins. You may then observe the I2S input being
looped back to the output and the MCLK being generated. A divided version of MCLK is output on PORT_I2S_DATA2 which allows
direct comparison of the input reference (LRCLK) with the recovered clock at the same frequency.

*****************
Running the tests
*****************

A test is available which checks the C implementation and the simulator, to run it::

    cmake -B build -DCMAKE_TOOLCHAIN_FILE=xmos_cmake_toolchain/xs3a.cmake
    cmake --build build --target test_app
    pip install -r .
    cd tests
    pytest

*********************************
Generating new PLL configurations
*********************************

Please see `doc/sw_pll.rst` for further details on how to design and build new sw_pll configurations. This covers the tradeoff between lock range, noise and memory usage.