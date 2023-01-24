"""
Assorted tests which run the test_app in xsim 
"""

import pandas
import pytest
from typing import Any
from sw_pll.sw_pll_sim import pll_solution, app_pll_frac_calc, sw_pll_ctrl, get_frequency_from_error
from dataclasses import dataclass, asdict
from subprocess import Popen, PIPE
from itertools import product
from pathlib import Path
from matplotlib import pyplot as plt

DUT_XE = Path(__file__).parent / "../build/tests/test_app/test_app.xe"


@dataclass
class DutArgs:
    kp: int
    ki: int
    kii: int
    loop_rate_count: int
    pll_ratio: int
    ref_clk_expected_inc: int
    lut: Any
    app_pll_ctl_reg_val: int
    app_pll_div_reg_val: int
    nominal_lut_idx: int
    ppm_range: int

class SimDut:
    """wrapper around sw_pll_ctrl so it works nicely with the tests"""

    def __init__(self, args: DutArgs, pll):
        self.pll = pll
        self.args = DutArgs(**asdict(args)) # copies the values
        self.lut = self.args.lut
        self.args.lut = len(self.lut.get_lut())
        self.ctrl = sw_pll_ctrl(
                self.lut_func,
                len(self.lut.get_lut()),
                args.loop_rate_count,
                args.pll_ratio, # args.ref_clk_expected_inc,
                args.kp,
                args.ki,
                args.kii,
                base_lut_index=args.nominal_lut_idx,
                verbose=True)

    def lut_func(self, error):
        return get_frequency_from_error(error, self.lut.get_lut(), self.pll)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        """Nothing to do"""

    def do_control(self, mclk_pt, _ref_pt):
        f, l = self.ctrl.do_control(mclk_pt)
        
        return l, f


def q_number(f, frac_bits):
    """float to fixed point"""
    return int(f * (2**frac_bits))


q16 = lambda n: q_number(n, 16)

class Dut:
    """
    run pll in xsim and provide access to the control function
    """

    def __init__(self, args: DutArgs, pll):
        self.pll = pll
        self.args = DutArgs(**asdict(args)) # copies the values
        self.args.kp = q16(self.args.kp)
        self.args.ki = q16(self.args.ki)
        self.args.kii = q16(self.args.kii)
        lut = self.args.lut.get_lut()
        self.args.lut = len(args.lut.get_lut())
        list_args = [*(str(i) for i in asdict(self.args).values())] + [str(i) for i in lut]

        cmd = ["xsim", "--args", str(DUT_XE), *list_args]

        print(" ".join(cmd))

        self.lut = lut
        self._process = Popen(
            cmd,
            stdin=PIPE,
            stdout=PIPE,
            encoding="utf-8",
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def do_control(self, mclk_pt, ref_pt):
        """
        returns lock_state, reg_val
        """
        self._process.stdin.write(f"{mclk_pt % 2**16} {ref_pt % 2**16}\n")
        self._process.stdin.flush()

        locked, reg = self._process.stdout.readline().strip().split()

        self.pll.update_pll_frac_reg(int(reg, 16))
        return int(locked), self.pll.get_output_frequency()

    def close(self):
        # send EOF
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

BASIC_TEST_PARAMS = list(product([16000, 48000], [Dut, SimDut]))

@pytest.fixture(scope="module", params=BASIC_TEST_PARAMS, ids=[str(i) for i in BASIC_TEST_PARAMS])
def basic_test_vector(request, solution_12288):
    """
    Generate some test vectors that can be tested
    """
    _, xtal_freq, target_mclk_f, sol = solution_12288
    lrclk_f = request.param[0]
    dut_class = request.param[1]
    bclk_per_lrclk = 64
    target_ref_f = lrclk_f * bclk_per_lrclk  # 64 bclk per sample
    
    # call the function every 512 samples rather than
    ref_pt_per_loop = bclk_per_lrclk * 512

    # every sample to speed things up.
    exp_mclk_per_loop = ref_pt_per_loop * (target_mclk_f / target_ref_f)
    loop_rate_count = 1

    # Generate init parameters
    start_reg = sol.lut.get_lut()[0]
    args = DutArgs(
        kp=0,
        ki=1,
        kii=0,
        loop_rate_count=loop_rate_count,  # copied from ed's setup in 3800
        # have to call 512 times to do 1
        # control update
        pll_ratio=int(target_mclk_f / (target_ref_f / ref_pt_per_loop)),
        ref_clk_expected_inc=ref_pt_per_loop,
        app_pll_ctl_reg_val=0,  # TODO maybe we should check this somehow
        app_pll_div_reg_val=start_reg,
        nominal_lut_idx=0,  # start low so there is some control to do
        ppm_range=int(len(sol.lut.get_lut())/2),
        lut=sol.lut,
    )

    pll = app_pll_frac_calc(xtal_freq, sol.F, sol.R, sol.OD, sol.ACD, 1, 2)
    pll.update_pll_frac_reg(start_reg)

    in_range_ppm_error = 1  # number that is less that 2
    input_freqs = {
        "perfect": target_ref_f,
        "out_of_range_low": target_ref_f * (1 - ((args.ppm_range * 3)/1e6)),
        "in_range_low": target_ref_f * (1 - ((args.ppm_range / 2)/1e6)),
        "out_of_range_high": target_ref_f * (1 + ((args.ppm_range * 3)/1e6)),
        "in_range_high": target_ref_f * (1 + ((args.ppm_range / 2)/1e6))
    }

    results = {
        "target": [],
        "mclk": [],
        "locked": [],
        "time": [],
        "exp_mclk_count": [],
        "mclk_count": [],
        "ref_f": [],
    }
    with dut_class(args, pll) as dut:
        _, mclk_f = dut.do_control(0, 0)

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
            locked, mclk_f = dut.do_control(
                int(mclk_pt), int(ref_pt)
            )

            results["target"].append(ref_f * (target_mclk_f/target_ref_f))
            results["ref_f"].append(ref_f)
            results["mclk"].append(mclk_f)
            time += loop_time
            results["time"].append(time)
            results["locked"].append(locked)
            results["exp_mclk_count"].append(exp_mclk_per_loop)
            results["mclk_count"].append(mclk_count)

    df = pandas.DataFrame(results)
    df = df.set_index("time")
    plt.figure()
    df[["target", "mclk", "locked"]].plot(secondary_y=["locked"])
    plt.savefig(
        f"basic-test-vector-{request.param}-freqs.png"
    )

    plt.figure()
    df[["exp_mclk_count", "mclk_count"]].plot()
    plt.savefig(
        f"basic-test-vector-{request.param}-counts.png"
    )
    df.to_csv(f"basic-test-vector-{request.param}.csv")

    return df, args, input_freqs

@pytest.mark.parametrize("test_f", ["perfect", "in_range_high", "in_range_low"])
def test_lock_acquired(basic_test_vector, test_f):
    """
    check that lock is achieved and then not lost for each in range
    reference frequency.
    """
    df, _, input_freqs = basic_test_vector

    this_df = df[df["ref_f"] == input_freqs[test_f]]
    # assert 0 != this_df["locked"].iloc[0], "first 'locked' value was locked, didn't expect to be locked"
    # find first locked
    locked_df = this_df[this_df["locked"] == 0]
    assert not locked_df.empty, "Expected lock to be achieved"
    first_locked = locked_df.index[0]
    after_locked = this_df[first_locked:]["locked"] == 0
    assert after_locked.all(), (
            "Expected continuous lock state once lock achieved")



