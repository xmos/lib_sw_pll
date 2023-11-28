# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

import pytest
import numpy as np
import copy

from sw_pll.app_pll_model import pll_solution, app_pll_frac_calc
from sw_pll.sw_pll_sim import sim_sw_pll_lut

from test_lib_sw_pll import SimDut, Dut, DutArgs, solution_12288, bin_dir

from pathlib import Path
from matplotlib import pyplot as plt

DUT_XE_LOW_LEVEL = Path(__file__).parent / "../build/tests/test_app_low_level_api/test_app_low_level_api.xe"
BIN_PATH = Path(__file__).parent/"bin"


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
        ki=2.0,
        kii=1.0, # NOTE WE SPECIFICALLY ENABLE KII in this test as it is not tested elsewhere
        loop_rate_count=loop_rate_count,
        pll_ratio=int(target_mclk_f / target_ref_f),
        ref_clk_expected_inc=0,
        app_pll_ctl_reg_val=0,
        app_pll_div_reg_val=start_reg,
        nominal_lut_idx=lut_size//2,
        ppm_range=int(lut_size * 2),
        lut=sol.lut,
    )

    pll = app_pll_frac_calc(xtal_freq, sol.F, sol.R, 1, 2, sol.OD, sol.ACD)

    pll.update_frac_reg(start_reg | app_pll_frac_calc.frac_enable_mask)

    input_errors = np.random.randint(-lut_size // 10, lut_size // 10, size = 40)
    print(f"input_errors: {input_errors}")

    result_categories = {
        "mclk": [],
        "locked": [],
        "time": [],
        "clk_diff": [],
        "clk_diff_i": [],
        "clk_diff_ii": [],
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

            locked, mclk_f, e, ea, eaa, fl, ticks = dut.do_control_from_error(input_error)

            results[name]["mclk"].append(mclk_f)
            results[name]["time"].append(time)
            results[name]["locked"].append(locked)
            results[name]["clk_diff"].append(e)
            results[name]["clk_diff_i"].append(ea)
            results[name]["clk_diff_ii"].append(eaa)
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
        clk_diff_ii = results[dut]["clk_diff_ii"]
        locked = results[dut]["locked"]

        plt.plot(mclk, label=dut)

    plt.legend(loc="upper left")
    plt.xlabel("Iteration")
    plt.ylabel("mclk")
    plt.savefig(bin_dir/f"c-vs-python-low-level-equivalence-mclk.png")
    plt.close()

    # Check for equivalence
    for compare_item in ["clk_diff", "clk_diff_i", "clk_diff_ii", "mclk"]:
        C = results["C"][compare_item]
        Python = results["Python"][compare_item]
        print("***", compare_item)
        for c, p in zip(C, Python):
            print(c, p)
        print()
        assert np.allclose(C, Python), f"Error in low level equivalence checking of: {compare_item}"

    print("TEST PASSED!")

