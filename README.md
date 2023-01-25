# lib_sw_pll

This library contains software that, together with the on-chip application PLL, provides a PLL that will generate a clock phase locked to an input clock.

********************************
Building and running the example
********************************

First ensure that in the root of lib_sw_pll (where this readme can be found) the xmos_cmake_toolchain repo exists. This can be done by:

    .. code-block:: console
        git clone git@github.com:xmos/xmos_cmake_toolchain.git


Run the following commands in the lib_sw_pll root folder to build the firmware:

.. tab:: Linux and Mac

    .. code-block:: console

        cmake -B build -DCMAKE_TOOLCHAIN_FILE=xmos_cmake_toolchain/xs3a.cmake
        cd build
        make simple

.. tab:: Windows

    .. code-block:: console

        cmake -G "NMake Makefiles" -B build -DCMAKE_TOOLCHAIN_FILE=xmos_cmake_toolchain/xs3a.cmake
        cd build
        nmake simple


To run the firmware, first connect LRCLK and BCLK (connects the test clock output to the PLL input)
and run the following command where <my_example> can be *simple* which uses the XCORE-AI-EXPLORER board
or *i2s_slave* which uses either the EVK3600 of EVK3800 board:

.. code-block:: console

    xrun --xscope <my_example>.xe


For simple.xe, to see the PLL lock, put one scope probe on either LRCLK/BCLK (reference) and the other on PORT_I2S_DAC_DATA to see the 
recovered clock which has been hardware divided back down to the same rate as the input clock.

For i2s_slave.xe you will need to connect a 48kHz I2S master to the LRCLK, BCLK pins. You may then observe the I2S input being
looped back to the output and the MCLK being generated. A divided version of MCLK is output on PORT_I2S_DATA2 which allows
direct comparison of the input reference (LRCLK) with the recovered clock at the same frequency.

**********
Running the tests
**********

A test is available which checks the C implementation and the simulator, to run it:

    .. code-block:: console
        cmake -B build -DCMAKE_TOOLCHAIN_FILE=xmos_cmake_toolchain/xs3a.cmake
        cmake --build build --target test_app
        pip install -r .
        cd tests
        pytest

