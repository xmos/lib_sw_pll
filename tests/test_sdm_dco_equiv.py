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
from typing import Any
from dataclasses import dataclass, asdict
from pathlib import Path
from matplotlib import pyplot as plt
from subprocess import Popen, PIPE


# from sw_pll.app_pll_model import app_pll_frac_calc
from sw_pll.dco_model import sigma_delta_dco

from test_lib_sw_pll import bin_dir


DUT_XE_SDM_DCO = Path(__file__).parent / "../build/tests/test_app_sdm_dco/test_app_sdm_dco.xe"

@dataclass
class DutSDMDCOArgs:
    dummy: int


class Dut_SDM_DCO:
    """
    run DCO in xsim and provide access to the sdm function
    """

    def __init__(self, pll, args:DutSDMDCOArgs, xe_file=DUT_XE_SDM_DCO):
        self.args = DutSDMDCOArgs(**asdict(args))  # copies the values
        # concatenate the parameters to the init function and the whole lut
        # as the command line parameters to the xe.
        list_args = [*(str(i) for i in asdict(self.args).values())] 

        cmd = ["xsim", "--args", str(xe_file), *list_args]

        print(" ".join(cmd))

        self.pll = pll.app_pll
        self._process = Popen(
            cmd,
            stdin=PIPE,
            stdout=PIPE,
            encoding="utf-8",
        )

    def __enter__(self):
        """support context manager"""
        return self

    def __exit__(self, *_):
        """support context manager"""
        self.close()

    def do_modulate(self, ds_in):
        """
        returns sigma delta out, calculated frac val, lock status and timing
        """
        self._process.stdin.write(f"{ds_in}\n")
        self._process.stdin.flush()

        from_dut = self._process.stdout.readline().strip()
        ds_out, frac_val, locked, ticks = from_dut.split()

        frac_val = int(frac_val)
        if frac_val & 0x80000000:
            self.pll.update_frac(0, 0, fractional=True)
            frequency = self.pll.update_frac_reg(frac_val)
        else:
            frequency = self.pll.update_frac(0, 0, fractional=False)
            
        return int(ds_out), int(frac_val), frequency, int(locked), int(ticks)

    def close(self):
        """Send EOF to xsim and wait for it to exit"""
        self._process.stdin.close()
        self._process.wait()

def test_sdm_dco_equivalence(bin_dir):
    """
    Simple low level test of equivalence using do_control_from_error
    Feed in random numbers into C and Python DUTs and see if we get the same results
    """

    args = DutSDMDCOArgs(
        dummy = 0
    )

    available_profiles = list(sigma_delta_dco.profiles.keys())
    profile = available_profiles[0]

    dco_sim = sigma_delta_dco(profile)
    dco_sim.write_register_file()

    dco_sim.print_stats()

    dut_pll = sigma_delta_dco(profile)
    dco_dut = Dut_SDM_DCO(dut_pll, args)

    for ds_in in [400000] * 20:
        frequency, lock_status = dco_sim.do_modulate(ds_in)
        sim_frac_reg = dco_sim.app_pll.get_frac_reg()
        if sim_frac_reg is None: sim_frac_reg = 0x00000007
        print(f"SIM: {dco_sim.sdm_out} {sim_frac_reg:#x} {frequency} {lock_status}")
        sdm_out, frac_val, frequency, lock_status, ticks = dco_dut.do_modulate(ds_in)
        print(f"DUT: {sdm_out} {frac_val:#x} {frequency} {lock_status} {ticks}\n")

    # pll = app_pll_frac_calc(xtal_freq, sol.F, sol.R, 1, 2, sol.OD, sol.ACD)

    # pll.update_frac_reg(start_reg)

    # input_errors = np.random.randint(-lut_size // 2, lut_size // 2, size = 40)
    # print(f"input_errors: {input_errors}")

    # result_categories = {
    #     "mclk": [],
    #     "locked": [],
    #     "time": [],
    #     "clk_diff": [],
    #     "clk_diff_i": [],
    #     "first_loop": [],
    #     "ticks": []
    # }
    # names = ["C", "Python"]
    # duts = [Dut(args, pll, xe_file=DUT_XE_LOW_LEVEL), SimDut(args, pll)]
    
    # results = {}
    # for name in names:
    #     results[name] = copy.deepcopy(result_categories)

    # for dut, name in zip(duts, names):
    #     _, mclk_f, *_ = dut.do_control_from_error(0)

    #     locked = -1
    #     time = 0
    #     print(f"Running: {name}")
    #     for input_error in input_errors:

    #         locked, mclk_f, e, ea, fl, ticks = dut.do_control_from_error(input_error)

    #         results[name]["mclk"].append(mclk_f)
    #         results[name]["time"].append(time)
    #         results[name]["locked"].append(locked)
    #         results[name]["clk_diff"].append(e)
    #         results[name]["clk_diff_i"].append(ea)
    #         results[name]["first_loop"].append(fl)
    #         results[name]["ticks"].append(ticks)
    #         time += 1

    #         # print(name, time, input_error, mclk_f)

    # # Plot mclk output dut vs dut
    # duts = list(results.keys())
    # for dut in duts:
    #     mclk = results[dut]["mclk"]
    #     times = results[dut]["time"]
    #     clk_diff = results[dut]["clk_diff"]
    #     clk_diff_i = results[dut]["clk_diff_i"]
    #     locked = results[dut]["locked"]

    #     plt.plot(mclk, label=dut)

    # plt.legend(loc="upper left")
    # plt.xlabel("Iteration")
    # plt.ylabel("mclk")
    # plt.savefig(bin_dir/f"c-vs-python-low-level-equivalence-mclk.png")
    # plt.close()

    # # Check for equivalence
    # for compare_item in ["mclk", "clk_diff", "clk_diff_i"]:
    #     C = results["C"][compare_item]
    #     Python = results["Python"][compare_item]
    #     assert np.allclose(C, Python), f"Error in low level equivalence checking of: {compare_item}"

    # print("TEST PASSED!")

