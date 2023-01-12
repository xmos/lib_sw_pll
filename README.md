# lib_sw_pll

This library contains software that, together with the on-chip application PLL, provides a PLL that will generate a clock phase locked to an input clock.

********************************
Building and running the example
********************************

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
and run the following command:

.. code-block:: console

    xrun --xscope simple.xe

To see the PLL lock, put one scope probe on either LRCLK/BCLK (reference) and the other on PORT_I2S_DAC_DATA to see the 
recovered clock which has been hardware divided back down to the same rate as the input clock.