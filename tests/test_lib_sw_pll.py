# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.
"""
Assorted tests which run the test_app in xsim 

This file is structured as a fixture which takes a while to run
and generates a pandas.DataFrame containing some time domain
outputs from the control loops. Then a series of tests which
check different aspects of the content of this DataFrame.
"""

import pandas
import pytest
import numpy as np
import copy

from sw_pll.app_pll_model import pll_solution, app_pll_frac_calc
from sw_pll.sw_pll_sim import sim_sw_pll_lut

from typing import Any
from dataclasses import dataclass, asdict
from subprocess import Popen, PIPE
from itertools import product
from pathlib import Path
from matplotlib import pyplot as plt

DUT_XE = Path(__file__).parent / "../build/tests/test_app/test_app.xe"
BIN_PATH = Path(__file__).parent/"bin"

@dataclass
class DutArgs:
    kp: float
    ki: float
    kii: float
    loop_rate_count: int
    pll_ratio: int
    ref_clk_expected_inc: int
    lut: Any
    app_pll_ctl_reg_val: int
    app_pll_div_reg_val: int
    nominal_lut_idx: int
    ppm_range: int
    target_output_frequency: int


class SimDut:
    """wrapper around sw_pll_ctrl so it works nicely with the tests"""

    def __init__(self, args: DutArgs, pll):
        self.pll = pll
        self.args = DutArgs(**asdict(args))  # copies the values
        self.lut = self.args.lut
        self.args.lut = len(self.lut)
        nominal_control_rate_hz = args.target_output_frequency / args.pll_ratio / args.loop_rate_count 
        self.ctrl = sim_sw_pll_lut(
            args.target_output_frequency,
            nominal_control_rate_hz,
            args.kp,
            args.ki,
            Kii=args.kii        )

    def lut_func(self, error):
        """Sim requires a function to provide access to the LUT. This is that"""
        return get_frequency_from_error(error, self.lut, self.pll)

    def __enter__(self):
        """support context manager"""
        return self

    def __exit__(self, *_):
        """Support context manager. Nothing to do"""

    def do_control(self, mclk_pt, _ref_pt):
        """
        Execute control using simulator
        """
        f, l = self.ctrl.do_control_loop(mclk_pt)

        return l, f, self.ctrl.controller.diff, self.ctrl.controller.error_accum, self.ctrl.controller.error_accum_accum, 0, 0

    def do_control_from_error(self, error):
        """
        Execute control using simulator
        """
        dco_ctl = self.ctrl.controller.get_dco_control_from_error(error)
        f, l = self.ctrl.dco.get_frequency_from_dco_control(dco_ctl)

        return l, f, self.ctrl.controller.diff, self.ctrl.controller.error_accum, self.ctrl.controller.error_accum_accum, 0, 0

class Dut:
    """
    run pll in xsim and provide access to the control function
    """

    def __init__(self, args: DutArgs, pll, xe_file=DUT_XE):
        self.pll = pll
        self.args = DutArgs(**asdict(args))  # copies the values
        self.args.kp = self.args.kp
        self.args.ki = self.args.ki
        self.args.kii = self.args.kii
        lut = self.args.lut
        self.args.lut = len(args.lut)
        # concatenate the parameters to the init function and the whole lut
        # as the command line parameters to the xe.
        list_args = [*(str(i) for i in asdict(self.args).values())] + [
            str(i) for i in lut
        ]

        cmd = ["xsim", "--args", str(xe_file), *list_args]

        print(" ".join(cmd))

        self.lut = lut
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

    def do_control(self, mclk_pt, ref_pt):
        """
        returns lock_state, reg_val, mclk_diff, error_acum, error_acum_acum, first_loop, ticks
        """
        self._process.stdin.write(f"{mclk_pt % 2**16} {ref_pt % 2**16}\n")
        self._process.stdin.flush()

        locked, reg, diff, acum, acum_acum, first_loop, ticks = self._process.stdout.readline().strip().split()

        self.pll.update_frac_reg(int(reg, 16) | app_pll_frac_calc.frac_enable_mask)
        return int(locked), self.pll.get_output_frequency(), int(diff), int(acum), int(acum_acum), int(first_loop), int(ticks)

    def do_control_from_error(self, error):
        """
        returns lock_state, reg_val, mclk_diff, error_acum, error_acum_acum, first_loop, ticks
        """
        self._process.stdin.write(f"{error % 2**16}\n")
        self._process.stdin.flush()

        locked, reg, diff, acum, acum_acum, first_loop, ticks = self._process.stdout.readline().strip().split()

        self.pll.update_frac_reg(int(reg, 16) | app_pll_frac_calc.frac_enable_mask)
        return int(locked), self.pll.get_output_frequency(), int(diff), int(acum), int(acum_acum), int(first_loop), int(ticks)


    def close(self):
        """Send EOF to xsim and wait for it to exit"""
        self._process.stdin.close()
        self._process.wait()


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

# pytest params for fixtures aren't as flexible as with tests as far as I can tell
# so manually doing the combination here, 16k and 48k for both xsim and python versions.
BASIC_TEST_PARAMS = list(product([16000, 48000], [Dut, SimDut]))

@pytest.fixture(
    scope="module", params=BASIC_TEST_PARAMS, ids=[str(i) for i in BASIC_TEST_PARAMS]
)
def basic_test_vector(request, solution_12288, bin_dir):
    """
    Generate some test vectors that can be tested by running the dut class with a series
    of in range and out of range values. This returns a pandas dataframe that can be analysed
    by the test functions.

    This simulates a scenario where a 16kHz or 48kHz I2S LRCLK is the trigger for calling 
    the control loop. The control function is called once every 512 loops (rather than every loop)
    with a loop_rate_count of 1, this is equivelant to calling it every loop with a loop rate count
    of 512 but requires less processing on xsim so should be faster.

    Each loop the MCLK count is calculated based on the previous iterations ref_clk and pll settings.
    This also saves some graphs as png and the whole dataframe as a csv
    """
    _, xtal_freq, target_mclk_f, sol = solution_12288
    lrclk_f = request.param[0]
    dut_class = request.param[1]
    name = f"{lrclk_f}-{dut_class.__name__}"
    bclk_per_lrclk = 64
    target_ref_f = lrclk_f * bclk_per_lrclk  # 64 bclk per sample

    # We are doing the scaling externally so multiply by factor
    ref_pt_per_loop = bclk_per_lrclk * 512

    # every sample to speed things up.
    exp_mclk_per_loop = ref_pt_per_loop * (target_mclk_f / target_ref_f)
    loop_rate_count = 1

    # Generate init parameters
    start_reg = sol.lut[0]
    args = DutArgs(
        target_output_frequency=target_mclk_f,
        kp=0.0,
        ki=1.0,
        kii=0.0,
        loop_rate_count=loop_rate_count,  # copied from ed's setup in 3800
        # have to call 512 times to do 1
        # control update
        pll_ratio=int(target_mclk_f / (target_ref_f / ref_pt_per_loop)),
        ref_clk_expected_inc=ref_pt_per_loop,
        app_pll_ctl_reg_val=0,  # TODO maybe we should check this somehow
        app_pll_div_reg_val=start_reg,
        nominal_lut_idx=0,  # start low so there is some control to do
        # with ki of 1 and the other values 0, the diff value translates
        # directly into the lut index. therefore the "ppm_range" or max
        # allowable diff must be at least as big as the LUT. *2 used here
        # to allow recovery from out of range values.
        ppm_range=int(len(sol.lut) * 2),
        lut=sol.lut,
    )

    pll = app_pll_frac_calc(xtal_freq, sol.F, sol.R,  1, 2, sol.OD, sol.ACD)

    frequency_lut = []
    for reg in sol.lut:
        pll.update_frac_reg(reg | app_pll_frac_calc.frac_enable_mask)
        frequency_lut.append(pll.get_output_frequency())
    frequency_range_frac = (frequency_lut[-1] - frequency_lut[0])/frequency_lut[0]

    plt.figure()
    pandas.DataFrame({"freq": frequency_lut}).plot()
    plt.savefig(bin_dir/f"lut-{name}.png")
    plt.close()

    pll.update_frac_reg(start_reg | app_pll_frac_calc.frac_enable_mask)

    input_freqs = {
        "perfect": target_ref_f,
        "out_of_range_low": target_ref_f * (1 - frequency_range_frac),
        "in_range_low": target_ref_f * (1 - (frequency_range_frac/4)),
        "out_of_range_high": target_ref_f * (1 + (frequency_range_frac)),
        "in_range_high": target_ref_f * (1 + (frequency_range_frac/4)),
        "way_out_out_range": target_ref_f * 2.1,
        "recover_in_range": target_ref_f + 1  # close to perfect
    }

    results = {
        "target": [],
        "mclk": [],
        "locked": [],
        "time": [],
        "exp_mclk_count": [],
        "mclk_count": [],
        "ref_f": [],
        "actual_diff": [],
        "clk_diff": [],
        "clk_diff_i": [],
        "clk_diff_ii": [],
        "first_loop": [],
        "ticks": []
    }
    with dut_class(args, pll) as dut:
        _, mclk_f, *_ = dut.do_control(0, 0)

        ref_pt = 0
        mclk_pt = 0
        locked = -1
        time = 0
        # do 100 loops at each frequency
        for ref_f in sum(([f] * 100 for f in input_freqs.values()), start=[]):
            # this basic test has fixed ref clock, the sunny day case

            ref_pt = ref_pt + ref_pt_per_loop

            # increment the mclk count based on the frequency that was
            # set by the pll and the current reference frequency
            loop_time = ref_pt_per_loop / ref_f
            mclk_count = loop_time * mclk_f
            mclk_pt = mclk_pt + mclk_count
            locked, mclk_f, e, ea, eaa, fl, ticks = dut.do_control(int(mclk_pt), int(ref_pt))

            results["target"].append(ref_f * (target_mclk_f / target_ref_f))
            results["ref_f"].append(ref_f)
            results["mclk"].append(mclk_f)
            time += loop_time
            results["time"].append(time)
            results["locked"].append(locked)
            results["exp_mclk_count"].append(exp_mclk_per_loop)
            results["mclk_count"].append(mclk_count)
            results["clk_diff"].append(e)
            results["actual_diff"].append(mclk_count - (ref_pt_per_loop * (target_mclk_f/target_ref_f)))
            results["clk_diff_i"].append(ea)
            results["clk_diff_ii"].append(eaa)
            results["first_loop"].append(fl)
            results["ticks"].append(ticks)

    df = pandas.DataFrame(results)
    df = df.set_index("time")
    plt.figure()
    y = frequency_lut[0] * frequency_range_frac
    df[["target", "mclk"]].plot(ylim=(frequency_lut[0] - y, frequency_lut[-1] + y))
    plt.savefig(bin_dir/f"basic-test-vector-{name}-freqs.png")
    plt.close()

    plt.figure()
    df[["target", "clk_diff_i"]].plot(secondary_y=["target"])
    plt.savefig(bin_dir/f"basic-test-vector-{name}-error-acum.png")
    plt.close()

    plt.figure()
    df[["target", "clk_diff_ii"]].plot(secondary_y=["target"])
    plt.savefig(bin_dir/f"basic-test-vector-{name}-error-acum-acum.png")
    plt.close()

    plt.figure()
    df[["exp_mclk_count", "mclk_count"]].plot()
    plt.savefig(bin_dir/f"basic-test-vector-{name}-counts.png")
    plt.close()

    plt.figure()
    df[["ticks"]].plot()
    plt.savefig(bin_dir/f"basic-test-vector-{name}-ticks.png")
    plt.close()

    df.to_csv(bin_dir/f"basic-test-vector-{name}.csv")

    with open(bin_dir/f"timing-report-lut.txt", "a") as tr:
        max_ticks = int(df[["ticks"]].max())
        tr.write(f"{name} max ticks: {max_ticks}\n")

    return df, args, input_freqs, frequency_lut


@pytest.mark.parametrize("test_f", ["perfect", "in_range_high", "in_range_low", "recover_in_range"])
def test_lock_acquired(basic_test_vector, test_f):
    """
    check that lock is achieved and then not lost for each in range
    reference frequency.
    """
    df, _, input_freqs, _ = basic_test_vector

    this_df = df[df["ref_f"] == input_freqs[test_f]]
    locked_df = this_df[this_df["locked"] == 0]
    assert not locked_df.empty, "Expected lock to be achieved"
    first_locked = locked_df.index[0]
    after_locked = this_df[first_locked:]["locked"] == 0
    assert after_locked.all(), "Expected continuous lock state once lock achieved"


@pytest.mark.parametrize("test_f", ["out_of_range_low", "out_of_range_high"])
def test_lock_lost(basic_test_vector, test_f):
    """
    Check that lock is lost when out of range reference frequency is provided
    """
    df, _, input_freqs, _ = basic_test_vector

    this_df = df[df["ref_f"] == input_freqs[test_f]]
    not_locked_df = this_df[this_df["locked"] != 0]

    assert not not_locked_df.empty, "Expected lock to be lost when out of range"
    first_not_locked = not_locked_df.index[0]
    after_not_locked = this_df[first_not_locked:]["locked"] != 0
    assert (
        after_not_locked.all()
    ), "Expected continuous not locked state, however locked was found"


def test_out_of_range_limit(basic_test_vector):
    """
    Test that the mclk generated never strays beyond the limits, this checks
    the control algorithm only picks register vaues from the LUT
    """
    df, _, _, f_lut = basic_test_vector
    max_freq = f_lut[-1]
    min_freq = f_lut[0]
    recovered = df["mclk"]
    assert (
        recovered >= min_freq
    ).all(), f"Some frequencies were below the minimum {min_freq}"
    assert (
        recovered <= max_freq
    ).all(), f"Some frequencies were above the max {max_freq}"


@pytest.mark.parametrize("test_f", ["perfect", "in_range_high", "in_range_low", "recover_in_range"])
def test_locked_values_within_desirable_ppm(basic_test_vector, test_f):
    """
    When the data is locked on an in range value the ppm jitter
    should be within a desired range and not change.
    """
    df, _, input_freqs, f_lut = basic_test_vector

    # determine maximum single step in the frequency table
    # then add some wiggle room.
    max_f_step = abs(max(b - a for a,b in zip(f_lut, f_lut[1:])) * 1.5)

    # locked means lut index within range, give some more cycles for
    # the control loop to really tune in.
    loops_after_lock_when_settled = 10
    test_df = df[(df["ref_f"] == input_freqs[test_f])
                 & (df["locked"] == 0)].iloc[loops_after_lock_when_settled:]

    assert not test_df.empty, "No locked values found, expected some"
    max_diff = (test_df["mclk"] - test_df["target"]).abs().max()
    assert max_diff < max_f_step, "Frequency oscillating more that expected when locked"
