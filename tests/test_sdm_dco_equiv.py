# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

import pytest
import numpy as np
import copy
from typing import Any
from dataclasses import dataclass, asdict
from pathlib import Path
from matplotlib import pyplot as plt
from subprocess import Popen, PIPE

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

    def do_modulate(self, sdm_in):
        """
        returns sigma delta out, calculated frac val and timing
        """
        self._process.stdin.write(f"{sdm_in}\n")
        self._process.stdin.flush()

        from_dut = self._process.stdout.readline().strip()
        sdm_out, frac_val, ticks = from_dut.split()

        frac_val = int(frac_val)
        frequency = self.pll.update_frac_reg(frac_val)
       
        return int(sdm_out), int(frac_val), frequency, int(ticks)

    def close(self):
        """Send EOF to xsim and wait for it to exit"""
        self._process.stdin.close()
        self._process.wait()

def test_sdm_dco_equivalence(bin_dir):
    """
    Simple low level test of equivalence using do_modulate
    Feed in a sweep of DCO control vals into C and Python DUTs and see if we get the same results
    """

    args = DutSDMDCOArgs(
        dummy = 0
    )

    available_profiles = list(sigma_delta_dco.profiles.keys())

    with open(bin_dir/f"timing-report-sdm-dco.txt", "a") as tr:

        for profile in available_profiles:

            dco_sim = sigma_delta_dco(profile)
            dco_sim.write_register_file()

            dco_sim.print_stats()

            dut_pll = sigma_delta_dco(profile)
            dco_dut = Dut_SDM_DCO(dut_pll, args)

            max_ticks = 0

            for sdm_in in np.linspace(dco_sim.sdm_in_min, dco_sim.sdm_in_max, 100):
                frequency_sim = dco_sim.do_modulate(sdm_in)
                frac_reg_sim = dco_sim.app_pll.get_frac_reg()
               
                print(f"SIM: {sdm_in} {dco_sim.sdm_out} {frac_reg_sim:#x} {frequency_sim}")
                
                sdm_out_dut, frac_reg_dut, frequency_dut, ticks = dco_dut.do_modulate(sdm_in)
                print(f"DUT: {sdm_in} {sdm_out_dut} {frac_reg_dut:#x} {frequency_dut} {ticks}\n")

                max_ticks = ticks if ticks > max_ticks else max_ticks

                assert dco_sim.sdm_out == sdm_out_dut
                assert frac_reg_sim == frac_reg_dut
                assert frequency_sim == frequency_dut

            tr.write(f"SDM DCO {profile} max ticks: {max_ticks}\n")

            print(f"{profile} TEST PASSED!")

