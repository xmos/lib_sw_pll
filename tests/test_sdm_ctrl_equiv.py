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
import re


# from sw_pll.app_pll_model import app_pll_frac_calc
from sw_pll.dco_model import sigma_delta_dco
from sw_pll.controller_model import sdm_pi_ctrl
from test_lib_sw_pll import bin_dir


DUT_XE_SDM_CTRL = Path(__file__).parent / "../build/tests/test_app_sdm_ctrl/test_app_sdm_ctrl.xe"

@dataclass
class DutSDMCTRLArgs:
    kp: float
    ki: float
    kii: float
    loop_rate_count: int
    pll_ratio: int
    ref_clk_expected_inc: int
    app_pll_ctl_reg_val: int
    app_pll_div_reg_val: int
    app_pll_frac_reg_val: int
    ctrl_mid_point: int
    ppm_range: int
    target_output_frequency: int


class Dut_SDM_CTRL:
    """
    run controller in xsim and provide access to the sdm function
    """

    def __init__(self, args:DutSDMCTRLArgs, xe_file=DUT_XE_SDM_CTRL):
        self.args = DutSDMCTRLArgs(**asdict(args))  # copies the values
        # concatenate the parameters to the init function and the whole lut
        # as the command line parameters to the xe.
        list_args = [*(str(i) for i in asdict(self.args).values())] 

        cmd = ["xsim", "--args", str(xe_file), *list_args]

        print(" ".join(cmd))

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

    def do_control(self, mclk_diff):
        """
        returns sigma delta out, calculated frac val, lock status and timing
        """
        self._process.stdin.write(f"{mclk_diff}\n")
        self._process.stdin.flush()

        from_dut = self._process.stdout.readline().strip()
        # print(f"from_dut: {from_dut}")
        error, dco_ctrl, locked, ticks = from_dut.split()

        return int(error), int(dco_ctrl), int(locked), int(ticks)

    def close(self):
        """Send EOF to xsim and wait for it to exit"""
        self._process.stdin.close()
        self._process.wait()


def read_register_file(reg_file):
    with open(reg_file) as rf:
        text = "".join(rf.readlines())
        regex = r".+APP_PLL_CTL_REG 0[xX]([0-9a-fA-F]+)\n.+APP_PLL_DIV_REG 0[xX]([0-9a-fA-F]+)\n.+APP_PLL_FRAC_REG 0[xX]([0-9a-fA-F]+)\n.+SW_PLL_SDM_CTRL_MID (\d+)"
        match = re.search(regex, text)

        app_pll_ctl_reg_val, app_pll_div_reg_val, app_pll_frac_reg_val, ctrl_mid_point = match.groups()

        return int(app_pll_ctl_reg_val, 16), int(app_pll_div_reg_val, 16), int(app_pll_frac_reg_val, 16), int(ctrl_mid_point)


def test_sdm_ctrl_equivalence(bin_dir):
    """
    Simple low level test of equivalence using do_control_from_error
    Feed in random numbers into C and Python DUTs and see if we get the same results
    """

    available_profiles = list(sigma_delta_dco.profiles.keys())

    with open(bin_dir/f"timing-report-sdm-ctrl.txt", "a") as tr:

        for profile_used in available_profiles:
            profile = sigma_delta_dco.profiles[profile_used]
            target_output_frequency = profile["output_frequency"]
            ctrl_mid_point = profile["mod_init"]
            ref_frequency = 48000
            ref_clk_expected_inc = 0

            Kp = 0.0
            Ki = 32.0
            Kii = 0.0

            ctrl_sim = sdm_pi_ctrl(ctrl_mid_point, sigma_delta_dco.sdm_in_max, sigma_delta_dco.sdm_in_min, Kp, Ki)

            dco = sigma_delta_dco(profile_used)
            dco.print_stats()
            register_file = dco.write_register_file()
            app_pll_ctl_reg_val, app_pll_div_reg_val, app_pll_frac_reg_val, read_ctrl_mid_point = read_register_file(register_file)

            assert ctrl_mid_point == read_ctrl_mid_point, f"ctrl_mid_point doesn't match: {ctrl_mid_point} {read_ctrl_mid_point}"

            args = DutSDMCTRLArgs(
                kp = Kp,
                ki = Ki,
                kii = Kii,
                loop_rate_count = 1,
                pll_ratio = target_output_frequency / ref_frequency,
                ref_clk_expected_inc = ref_clk_expected_inc,
                app_pll_ctl_reg_val = app_pll_ctl_reg_val,
                app_pll_div_reg_val = app_pll_div_reg_val,
                app_pll_frac_reg_val = app_pll_frac_reg_val,
                ctrl_mid_point = ctrl_mid_point,
                ppm_range = 1000,
                target_output_frequency = target_output_frequency
            )


            ctrl_dut = Dut_SDM_CTRL(args)

            max_ticks = 0

            for i in range(50):
                mclk_diff = np.random.randint(-10, 10)

                # Run through the model
                dco_ctl_sim, lock_status_sim = ctrl_sim.do_control_from_error(mclk_diff)
                error_sim = ctrl_sim.total_error

                # Run through the firmware
                error_dut, dco_ctl_dut, lock_status_dut, ticks = ctrl_dut.do_control(mclk_diff)

                print(f"SIM: {mclk_diff} {error_sim} {dco_ctl_sim} {lock_status_sim}")
                print(f"DUT: {mclk_diff} {error_dut} {dco_ctl_dut} {lock_status_dut} {ticks}\n")

                max_ticks = ticks if ticks > max_ticks else max_ticks

                assert error_sim == error_dut
                assert dco_ctl_sim == dco_ctl_dut
                assert lock_status_sim == lock_status_dut

            tr.write(f"SDM Control {profile_used} max ticks: {max_ticks}\n")

            print(f"{profile_used} TEST PASSED!")

