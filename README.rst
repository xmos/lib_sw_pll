lib_sw_pll
==========

This library contains software that, together with the on-chip application PLL, provides a PLL that will generate a clock that is phase-locked to an input clock.

It supports both Look Up Table (LUT) and Sigma Delta Modulated (SDM) Digitally Controlled Oscillators (DCO), a Phase Frequency Detector (PFD) and
configurable Proportional Integral (PI) controllers which together form a hybrid Software/Hardware Phase Locked Loop (PLL).

Examples are provided showing a master clock locking to a low frequency input reference clock and also to an I2S slave interface.

In addition, an API providing a range of fixed clocks supporting common master clock frequencies between 11.2896 MHz and 49.152 MHz is available 
in cases where phase locking is not required.

*********************************
Building and running the examples
*********************************

Ensure a correctly configured installation of the XMOS tools and open an XTC command shell. Please check that the XMOS tools are correctly
sourced by running the following command::

    $ xcc
    xcc: no input files

.. note::
    Instructions for installing and configuring the XMOS tools appear on `the XMOS web site <https://www.xmos.ai/software-tools/>`_.

Clone the lib_sw_pll repository::

    git clone git@github.com:xmos/lib_sw_pll.git
    cd lib_sw_pll


Place the fwk_core and fwk_io repositories in the modules directory of lib_sw_pll. These are required dependencies for the example apps.
To do so, from the root of lib_sw_pll (where this read me file exists) type::

    mkdir modules
    cd modules
    git clone --recurse-submodules git@github.com:xmos/fwk_core.git
    git clone --recurse-submodules git@github.com:xmos/fwk_io.git
    cd ..

.. note::
    The fwk_core and fwk_io repositories have not been sub-moduled into this Git repository because only the examples depend upon them.

Run the following commands in the lib_sw_pll root folder to build the firmware.

On linux::

    cmake -B build -DCMAKE_TOOLCHAIN_FILE=modules/fwk_io/xmos_cmake_toolchain/xs3a.cmake
    cd build
    make simple_lut simple_sdm i2s_slave_lut

On Windows::

    cmake -G "Ninja" -B build -DCMAKE_TOOLCHAIN_FILE=modules/fwk_io/xmos_cmake_toolchain/xs3a.cmake
    cd build
    ninja simple_lut simple_sdm i2s_slave_lut


To run the firmware, first connect LRCLK and BCLK (connects the test clock output to the PLL reference input)
and run the following command where <my_example> can be *simple_lut* or *simple_sdm* which use the XCORE-AI-EXPLORER board
or *i2s_slave_lut* which uses the XK-VOICE-SQ66 board::

    xrun --xscope <my_example>.xe


For simple_xxx.xe, to see the PLL lock, put one scope probe on either LRCLK/BCLK (reference input) and the other on PORT_I2S_DAC_DATA to see the 
recovered clock which has been hardware divided back down to the same rate as the input reference clock.

For i2s_slave_lut.xe you will need to connect a 48kHz I2S master to the LRCLK, BCLK pins. You may then observe the I2S input data being
looped back to the output and the MCLK being generated. A divided version of MCLK is output on PORT_I2S_DATA2 which allows
direct comparison of the input reference (LRCLK) with the recovered clock at the same, and locked, frequency.


*********************************
Generating new PLL configurations
*********************************

Please see `doc/rst/sw_pll.rst` for further details on how to design and build new sw_pll configurations. This covers the tradeoff between lock range, 
oscillator noise and resource usage.