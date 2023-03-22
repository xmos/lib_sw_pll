How the Software PLL works
--------------------------

The XCORE-AI devices come with a secondary PLL sometimes called the Application (App) PLL. This PLL
multiplies the clock from the on-board crystal source and has a fractional register allowing very fine control
over the multiplication and division ratios.

However, it does not support an external reference clock input and so cannot natively track and lock
to an external clock reference. This SW-PLL module is a set of scripts and firmware which enables the
provision of an input clock which, along with a control loop, allows tracking of the external reference
over a certain range.

The range is governed by the look up table (LUT) which has a finite number of entries and consequently
a step size which affects the output jitter performance. The index into the LUT is controlled by a 
PI controller which multiplies the error in put and integral error input by the supplied loop constants.
An integrated wind up limiter for the integral term is nominally set at 2x the maximum LUT index
deviation to prevent excessive overshoot where the starting input error is high.

In addition to the standard API which takes a clock counting input, for applications where the PLL is 
to be controlled using a PI fed with a raw error input, a low-level API is also provided. This low-level
API allows the Software PLL to track an arbitrary clock source which is calculated by another means.

This document provides a guide to generating the LUT and configuring the available parameters to
reach the appropriate compromise of performance and resource usage for your application.



Running the PI simulation and LUT generation script
---------------------------------------------------

In the ``python/sw_pll`` directory you will find two files::

    .
    ├── pll_calc.py
    └── sw_pll_sim.py

``pll_calc.py`` is the command line script that generates the LUT. It is quite a complex to use script which requires in depth
knowledge of the operation of the App PLL. Instead, it is recommended to use ``sw_pll_sim.py`` which calls ``pll_calc.py`` 
except with a number of example PLL profiles already provided as a starting point.

By running `sw_pll_sim.py` a number of operations will take place:

 - The ``fractions.h`` LUT include file will be generated.
 - The ``register_setup.h`` PLL configuration file will be generated.
 - A graphical view of the LUT settings ``sw_pll_range.png`` showing index vs. output frequency is generated.
 - A time domain simulation of the PI loop showing the response to steps and out of range reference inputs is run.
 - A graphical view of the simulation is saved to ``pll_step_response.png``.
 - A wave file containing a 1 kHz modulated tone for offline analysis. Note that ``ppm_shifts`` will need to be set to ``()`` otherwise it will contain the injected PPM deviations as part of the step response test.
 - A zoomed-in log FFT plot of the 1 kHz tone to see how the LUT frequency steps affect a pure tone. The same note applies as the above item.
 - A summary report of the PLL range is printed to the console.

The directory listing following running of ``sw_pll_sim.py`` should look as follows::

    .
    ├── fractions.h
    ├── pll_calc.py
    ├── pll_step_response.png
    ├── register_setup.h
    ├── sw_pll_range.png
    ├── modulated_tone_1000Hz.wav
    ├── modulated_tone_fft_1000Hz.png
    └── sw_pll_sim.py


A typical LUT transfer function is shown below. Note that although not perfectly regular it is monotonic and hence
the control loop will work well with it. This is an artifact of the fractional setting steps available.
You can also see the actual frequency oscillate very slightly over time. This is because the control loop hunts
between two discrete fractional settings in the LUT and is expected. You may adjust the rate at which the control
loop is called to center this noise around different frequencies or decrease the step size (larger LUT) to
manage the amplitude of this artifact.

.. image:: ./images/sw_pll_range.png
   :width: 500


Here you can see the step response of the control loop below. You can see it track smaller step changes but for the
larger steps it can be seen to clip and not reach the input step, which is larger than the LUT size will 
allow. The LUT size can be increased if needed to accommodate a wider range.

The step response is quite fast and you can see even a very sharp change in frequency is accommodated in just
a handful of control loop iterations.

.. image:: ./images/pll_step_response.png
   :width: 500

Note that each time you run ``sw_pll_sim.py`` and the ``fractions.h`` file is produced, a short report will be produced that indicates the achieved range of settings.
Below is a typical report showing what information is summarised::

    $ rm -f fractions.h  && python sw_pll_sim.py 
    Running: lib_sw_pll/python/sw_pll/pll_calc.py -i 24.0  -a -m 80 -t 12.288 -p 6.0 -e 5 -r --fracmin 0.695 --fracmax 0.905 --header
    Available F values: [30, 32, 77, 79, 116, 118, 122, 159, 163, 165, 200, 204, 208, 245, 286, 331, 417]
    output_frequency: 12288000.0, vco_freq: 2457600000.0, F: 203, R: 1, f: 3, p: 4, OD: 1, ACD: 24, ppm: 0.0
    PLL register settings F: 203, R: 1, OD: 1, ACD: 24, f: 3, p: 4
    min_freq: 12281739Hz
    mid_freq: 12288000Hz
    max_freq: 12294286Hz
    average step size: 30.3791Hz, PPM: 2.47226
    PPM range: -509.771
    PPM range: +511.533
    LUT entries: 413 (826 bytes)


The following section provides guidance for adjusting the LUT.

How to configure the fractions table
------------------------------------

The fractions lookup table is a trade-off between PPM range and frequency step size. Frequency 
step size will affect jitter amplitude as it is the amount that the PLL will change frequency when it needs 
to adjust. Typically, the locked control loop will slowly oscillate between two values that 
straddle the target frequency, depending on input frequency.

Small discontinuities in the LUT may be experienced in certain ranges, particularly close to 0.5 fractional values, so it is preferable 
to keep in the lower or upper half of the fractional range. However the LUT table is always monotonic 
and so control instability will not occur for that reason. The range of the ``sw_pll`` can be seen 
in the ``sw_pll_range.png`` image. It should be a reasonably linear response without significant 
discontinuities. If not, try moving the range towards 0.0 or 1.0 where fewer discontinuities will
be observed.

Steps to vary PPM range and frequency step size
-----------------------------------------------


1. Ascertain your target PPM range, step size and maximum tolerable table size. Each lookup value is 16b so the total size in bytes is 2 x n.
2. Start with the given example values and run the generator to see if the above three parameters meet your needs. The values are reported by ``sw_pll_sim.py``.
3. If you need to increase the PPM range, you may either:
    - Decrease the ``min_F`` to allow the fractional value to have a greater effect. This will also increase step size. It will not affect the LUT size.
    - Increase the range of ``fracmin`` and ``fracmax``. Try to keep the range closer to 0 or 1.0. This will decrease step size and increase LUT size.
4. If you need to decrease the step size you may either:
    - Increase the ``min_F`` to allow the fractional value to have a greater effect. This will also reduce the PPM range. When the generation script is run the allowable F values are reported so you can tune the ``min_F`` to force use of a higher F value.
    - Increase the ``max_denom`` beyond 80. This will increase the LUT size (finer step resolution) but not affect the PPM range. Note this will increase the intrinsic jitter of the PLL hardware on chip due to the way the fractional divider works. 80 has been chosen for a reasonable tradeoff between step size and PLL intrinsic jitter and pushes this jitter beyond 40 kHz which is out of the audio band. The lowest intrinsic fractional PLL jitter freq is input frequency (normally 24 MHz) / ref divider / largest value of n.
5. If the +/-PPM range is not symmetrical and you wish it to be, then adjust the ``fracmin`` and ``fracmax`` values around the center point that the PLL finder algorithm has found. For example if the -PPM range is to great, increase ``fracmin`` and if the +PPM range is too great, decrease the ``fracmax`` value.


Note when the process has completed, please inspect the ``sw_pll_range.png`` output figure which shows how the fractional PLL setting affects the output frequency.
This should be monotonic and not contain an significant discontinuities for the control loop to operate satisfactorily.

Steps to tune the PI loop
-------------------------

Note, in the python simulation file ``sw_pll_sim.py``, the PI constants *Kp* and *Ki* can be found in the function `run_sim()`.

Typically the PID loop tuning should start with 0 *Kp* term and a small (e.g. 1.0) *Ki* term.
 
 - Decreasing the ref_to_loop_call_rate parameter will cause the control loop to execute more frequently and larger constants will be needed.
 - Try tuning *Ki* value until the desired response curve (settling time, overshoot etc.) is achieved in the ``pll_step_response.png`` output.
 - *Kp* can normally remain zero, but you may wish to add a small value to improve step response

.. note::
    After changing the configuration, ensure you delete `fractions.h` otherwise the script will re-use the last calculated values. This is done to speed execution time of the script by avoiding the generation step.

Example configurations
----------------------

A number of example configurations, which demonstrate the effect on PPM, step size etc. of changing various parameters, is provided in the ``sw_pll_sim.py`` file.
Search for ``profiles`` and ``profile_choice`` in this file. Change profile choice index to select the different example profiles and run the python file again.

.. list-table:: xscope throughput 
   :widths: 50 50 50 50 50
   :header-rows: 1

   * - Output frequency MHz
     - Reference frequency kHz
     - Range +/- PPM
     - Average step size Hz
     - LUT size bytes
   * - 12.288
     - 48.0
     - 250
     - 29.3
     - 426
   * - 12.288
     - 48.0
     - 500
     - 30.4
     - 826
   * - 12.288
     - 48.0
     - 500
     - 31.0
     - 1580
   * - 24.576
     - 48.0
     - 500
     - 60.8
     - 826
   * - 24.576
     - 48.0
     - 100
     - 9.5
     - 1050
   * - 6.144
     - 16.0
     - 150
     - 30.2
     - 166

Note that the PLL actually multiplies the input crystal, not the reference input clock. A change in the reference input clock only affects the control loop
and its associated constants such as how often the PI loop is called.

Transferring the results to C
-----------------------------

Once the LUT has been generated and simulated in Python, the values can be transferred to the firmware application. Either consult the ``sw_pll.h`` API file (below) for details or follow one of the examples in the ``/examples`` directory.

lib_sw_pll API
--------------

.. doxygengroup:: sw_pll_api
    :content-only:

