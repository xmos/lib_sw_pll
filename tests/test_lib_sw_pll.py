"""
Assorted tests which run the test_app in xsim 
"""

import sw_pll

from subprocess import Popen, PIPE
from pathlib import Path

DUT_XE = Path(__file__).parent / "../build/tests/test_app/test_app.xe"


class Dut:
    """
    run pll in xsim and provide access to the control function
    """
    def __init__(
        self,
        kp,
        ki,
        kii,
        loop_rate_count,
        pll_ratio,
        ref_clk_expected_inc,
        lut,
        app_pll_ctl_reg_val,
        app_pll_div_reg_val,
        nominal_lut_idx,
        ppm_range,
    ):
        args = [
            str(kp),
            str(ki),
            str(kii),
            str(loop_rate_count),
            str(pll_ratio),
            str(ref_clk_expected_inc),
            str(len(lut)),
            str(app_pll_ctl_reg_val),
            str(app_pll_div_reg_val),
            str(nominal_lut_idx),
            str(ppm_range),
        ] + [str(i) for i in lut]

        self._process = Popen(
            ["xsim", "--args", str(DUT_XE), *args],
            stdin=PIPE,
            stdout=PIPE,
            encoding="utf-8",
        )

    def do_control(self, mclk_pt, ref_pt):
        """
        returns lock_state, reg_val
        """
        self._process.stdin.write(f"{mclk_pt} {ref_pt}\n")
        self._process.stdin.flush()

        locked, reg = self._process.stdout.readline().strip().split()
        return int(locked), int(reg, 16)

    def close(self):
        self._process.stdin.close()
        self._process.wait()


def test_example():
    d = Dut(0, 0, 0, 0, 0, 0, [1, 2, 3, 4], 0, 0, 0, 0)
    for _ in range(1000):
        print(*d.do_control(0, 0))
    d.close()
