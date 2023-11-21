# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.
"""
Assorted tests which run the test_app in xsim 

This file is structured as a fixture which takes a while to run
and generates a pandas.DataFrame containing some time domain
outputs from the control loops. Then a series of tests which
check different aspects of the content of this DataFrame.
"""

import pytest
import numpy as np
import copy

from sw_pll.app_pll_model import pll_solution, app_pll_frac_calc
from sw_pll.sw_pll_sim import sim_sw_pll_lut

from test_lib_sw_pll import SimDut, Dut, DutArgs

from pathlib import Path
from matplotlib import pyplot as plt

DUT_XE_LOW_LEVEL = Path(__file__).parent / "../build/tests/test_app_low_level_api/test_app_low_level_api.xe"
BIN_PATH = Path(__file__).parent/"bin"



@pytest.fixture(scope="module")
def solution_12288():
    """
    generate the solution, takes a while and no need
    to do it more than once.
    """
    xtal_freq = 24e6
    target_mclk_f = 12.288e6

    ppm_max = 2.0
    sol = pll_solution(xtal_freq, target_mclk_f, ppm_max=ppm_max)

    return ppm_max, xtal_freq, target_mclk_f, sol

@pytest.fixture(scope="module")
def bin_dir():
    d = BIN_PATH
    d.mkdir(parents=True, exist_ok=True)
    return d



def test_low_level_equivalence(solution_12288, bin_dir):
    """
    Simple low level test of equivalence using do_control_from_error
    Feed in random numbers into C and Python DUTs and see if we get the same results
    """

    _, xtal_freq, target_mclk_f, sol = solution_12288

 
    # every sample to speed things up.
    loop_rate_count = 1
    target_ref_f = 48000

    # Generate init parameters
    start_reg = sol.lut[0]
    lut_size = len(sol.lut)

    args = DutArgs(
        target_output_frequency=target_mclk_f,
        kp=0.0,
        ki=1.0,
        loop_rate_count=loop_rate_count,  # copied from ed's setup in 3800
        # have to call 512 times to do 1
        # control update
        pll_ratio=int(target_mclk_f / target_ref_f),
        ref_clk_expected_inc=0,
        app_pll_ctl_reg_val=0,
        app_pll_div_reg_val=start_reg,
        nominal_lut_idx=lut_size//2,
        ppm_range=int(lut_size * 2),
        lut=sol.lut,
    )

    pll = app_pll_frac_calc(xtal_freq, sol.F, sol.R, 1, 2, sol.OD, sol.ACD)

    pll.update_frac_reg(start_reg)

    input_errors = np.random.randint(-lut_size // 2, lut_size // 2, size = 40)
    print(f"input_errors: {input_errors}")

    result_categories = {
        "mclk": [],
        "locked": [],
        "time": [],
        "clk_diff": [],
        "clk_diff_i": [],
        "first_loop": [],
        "ticks": []
    }
    names = ["C", "Python"]
    duts = [Dut(args, pll, xe_file=DUT_XE_LOW_LEVEL), SimDut(args, pll)]
    
    results = {}
    for name in names:
        results[name] = copy.deepcopy(result_categories)

    for dut, name in zip(duts, names):
        _, mclk_f, *_ = dut.do_control_from_error(0)

        locked = -1
        time = 0
        print(f"Running: {name}")
        for input_error in input_errors:

            locked, mclk_f, e, ea, fl, ticks = dut.do_control_from_error(input_error)

            results[name]["mclk"].append(mclk_f)
            results[name]["time"].append(time)
            results[name]["locked"].append(locked)
            results[name]["clk_diff"].append(e)
            results[name]["clk_diff_i"].append(ea)
            results[name]["first_loop"].append(fl)
            results[name]["ticks"].append(ticks)
            time += 1

            # print(name, time, input_error, mclk_f)

    # Plot mclk output dut vs dut
    duts = list(results.keys())
    for dut in duts:
        mclk = results[dut]["mclk"]
        times = results[dut]["time"]
        clk_diff = results[dut]["clk_diff"]
        clk_diff_i = results[dut]["clk_diff_i"]
        locked = results[dut]["locked"]

        plt.plot(mclk, label=dut)

    plt.legend(loc="upper left")
    plt.xlabel("Iteration")
    plt.ylabel("mclk")
    plt.savefig(bin_dir/f"c-vs-python-low-level-equivalence-mclk.png")
    plt.close()

    # Check for equivalence
    for compare_item in ["mclk", "clk_diff", "clk_diff_i"]:
        C = results["C"][compare_item]
        Python = results["Python"][compare_item]
        assert np.allclose(C, Python), f"Error in low level equivalence checking of: {compare_item}"

    print("TEST PASSED!")
