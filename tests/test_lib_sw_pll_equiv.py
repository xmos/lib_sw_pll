# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

"""Regression checks that C LUT and MASH controllers match their Python models.

The Python model is used to explore and tune software PLL behavior, so changes
must not silently make its controller response diverge from the firmware.
This test feeds identical random error samples directly into both low-level
control APIs, bypassing port-timer sampling and the PFD. A nonzero Kii exercises
the double-integral path as well as the integral term and LUT frequency output.

The C implementation runs in xsim using the prebuilt low-level test executable;
no physical board is required. Error, integral and double-integral state, and
calculated output frequency are compared with np.allclose. Lock status and
timing are recorded but not asserted equivalent. The generated plot helps
diagnose differences; this does not validate analog PLL dynamics or jitter.

MASH equivalence uses a separate integer reference matching the firmware's Q16
gains and current windup/reset semantics. Its state and control words are
compared exactly, including lock status and counters, but not execution ticks.
Select VX-backed cases with --run-mash -m mash_xsim. xsim exposes average PLL
frequency only, so these tests do not validate the hardware modulator sequence.
"""

import pytest
import numpy as np
import copy
from dataclasses import replace

from mash_test_utils import MashDut, MashDutArgs, MashSimDut

from sw_pll.app_pll_model import pll_solution, app_pll_frac_calc
from sw_pll.sw_pll_sim import sim_sw_pll_lut

from test_lib_sw_pll import SimDut, Dut, DutArgs, solution_12288

from pathlib import Path
from matplotlib import pyplot as plt

DUT_XE_LOW_LEVEL = Path(__file__).parent / "test_app_low_level_api/bin/test_app_low_level_api.xe"
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

    pll.update_frac_reg(start_reg.astype(int) | app_pll_frac_calc.frac_enable_mask)

    input_errors = np.random.randint(-lut_size // 10, lut_size // 10, size = 40)

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
        assert np.allclose(C, Python), f"Error in low level equivalence checking of: {compare_item}"


@pytest.mark.mash_xsim
@pytest.mark.parametrize("gains", [(0.0, 2.0, 1.0), (0.5, 1.25, 0.125)])
def test_mash_low_level_equivalence(gains):
    """Compare Q16 controller states exactly; xsim models average Hz only.

    Fixed-seed errors, signed extremes and sustained errors exercise fractional
    gains, negative shifts, both accumulators, windup bounds and output clipping.
    No hardware MASH cycles or analog PLL response are inferred from this test.
    """
    args = MashDutArgs(kp=gains[0], ki=gains[1], kii=gains[2])
    errors = [int(value) for value in np.random.default_rng(2026).integers(-2000, 2001, 100)]
    errors += [32767] * 40 + [-32768] * 80 + [0] * 20
    with MashDut(args, mode="error") as actual, MashSimDut(args) as expected:
        for index, error in enumerate(errors):
            c_state = actual.do_control_from_error(error)
            python_state = expected.do_control_from_error(error)
            assert c_state.controller_state() == python_state.controller_state(), (index, error, c_state, python_state)
            assert actual.frequency_hz(c_state) == expected.frequency_hz(python_state)


@pytest.mark.mash_xsim
def test_mash_saturation_and_lock_recovery_equivalence():
    """Proportional-only errors force each rail, then permit lock recovery."""
    args = MashDutArgs(kp=32.0, ki=0.0, kii=0.0)
    with MashDut(args, mode="error") as actual, MashSimDut(args) as expected:
        states = []
        for error in [32767, -32768] + [0] * 11:
            c_state = actual.do_control_from_error(error)
            python_state = expected.do_control_from_error(error)
            assert c_state.controller_state() == python_state.controller_state()
            states.append(c_state)
    assert states[0].word == 0x1999A and states[0].lock_status == -1
    assert states[1].word == 0xE6666 and states[1].lock_status == 1
    assert all(state.lock_status == 1 for state in states[2:12])
    assert states[-1].lock_status == 0


@pytest.mark.mash_xsim
@pytest.mark.parametrize("compensated", [False, True])
def test_mash_timer_equivalence(compensated):
    """Exercise decimation, wrap, compensated timing and the deferred PFD reset."""
    args = replace(MashDutArgs(kp=0.5, ki=2.0, kii=0.125),
                   loop_rate_count=4, pll_ratio=256,
                   ref_clk_expected_inc=64 if compensated else 0)
    mclk_pt = 65000
    ref_pt = 65000
    with MashDut(args) as actual, MashSimDut(args) as expected:
        saw_reset = False
        for sample in range(160):
            jitter = (-1, 0, 1, 0)[sample % 4] if compensated else 0
            ref_pt += 64 + jitter
            # Integer reference/output ratio is four MCLKs per ref-port tick.
            mclk_pt += 256 + 4 * jitter + (1000 if sample == 60 else 0)
            c_state = actual.do_control(mclk_pt, ref_pt)
            python_state = expected.do_control(mclk_pt, ref_pt)
            assert c_state.controller_state() == python_state.controller_state(), (sample, c_state, python_state)
            if c_state.first_loop and sample > 4:
                saw_reset = True
        assert saw_reset


@pytest.mark.mash_xsim
def test_mash_batch_timer_equivalence():
    """Buffered replay must preserve every state, including timer wrapping."""
    args = replace(MashDutArgs(), loop_rate_count=2, pll_ratio=256)
    samples = [(65000 + 256 * index, 0) for index in range(32)]
    with MashSimDut(args) as reference:
        expected = [reference.do_control(*sample) for sample in samples]
    with MashDut(args, mode="timers-batch") as actual:
        states = actual.run_control_trace(samples)
    assert [state.controller_state() for state in states] == [
        state.controller_state() for state in expected]


def test_mash_integer_reference_lock_and_reset():
    """Keep a host-only sanity check even when VX xsim tests are not selected."""
    model = MashSimDut(MashDutArgs(kp=32.0, ki=0.0))
    assert model.do_control_from_error(32767).word == 0x1999A
    assert model.do_control_from_error(-32768).word == 0xE6666
    for _ in range(10):
        model.do_control_from_error(0)
    state = model.do_control_from_error(0)
    assert state.lock_status == 0
    assert model.do_control(0).first_loop == 0
    assert model.do_control(10000).first_loop == 1
    state = model.do_control(20000)
    assert state.first_loop == 0
    assert state.integral == state.double_integral == 0


def test_mash_compensated_timer_reset_recovery():
    args = replace(MashDutArgs(), loop_rate_count=4, pll_ratio=256,
                   ref_clk_expected_inc=64)
    model = MashSimDut(args)
    mclk_pt = 0
    ref_pt = 0

    def advance(samples, extra_mclk=0):
        nonlocal mclk_pt, ref_pt
        state = None
        for sample in range(samples):
            mclk_pt += 256 + (extra_mclk if sample == samples - 1 else 0)
            ref_pt += 64
            state = model.do_control(mclk_pt, ref_pt)
        return state

    advance(4)
    assert advance(4).error == 0
    assert advance(4, extra_mclk=1000).first_loop == 1
    assert advance(4).first_loop == 0
    state = advance(4)
    assert state.first_loop == 0
    assert state.error == 0
