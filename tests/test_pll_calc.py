# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

"""Host-side regression tests for PLL register calculation and MASH DCO setup new features.

These tests guard against generating misleading or unusable clock settings when
extending pll_calc.py, while preserving a known legacy PWM register encoding (version 2.5.0 of lib_sw_pll and before).
They call the calculator directly, inspect its printed output, and invoke its
command-line interface in Python subprocesses; neither hardware nor xsim is used.

Coverage includes:
- Reproducing the existing LUT example's control, final-divider, and PWM words,
    including the physical-ratio-to-register minus-one encoding.
- Generating 12.288 MHz from 24 MHz within an explicit 0.01 ppm tolerance and
    with at least +/-1000 ppm tuning headroom. Results are checked for ordering,
    both fixed divide-by-two stages, Hz-per-LSB resolution, and tuning endpoints
    inside the 0.1..0.9 MASH window and average VCO/PLL-output limits.
- Independently recomputing nominal error using rational arithmetic, rejecting
    inexact 12.288 MHz settings at zero tolerance, and accepting exactly
    representable 12.375 MHz settings. Printed errors must distinguish exact from
    rounded results and must not display tiny nonzero errors as zero.
- Carrying fractional rounding through 1.0 into the integer feedback divider
    without overflowing the 20-bit MASH payload, and rejecting impossible tuning
    requirements, invalid arguments, and incompatible command-line options.
- Producing a raw nominal MASH payload without a redundant PWM definition,
    since MASH initialization disables PWM internally.

This is not a simulation of the MASH output sequence or the analog PLL. It does
not establish jitter, phase noise, crystal accuracy, or software-loop stability,
and the legacy encoding case is not exhaustive coverage of the PWM search.
"""

import math
from fractions import Fraction
from pathlib import Path
import subprocess
import sys

import pytest

from sw_pll.pll_calc import find_mash_pll, print_mash_solution, print_regs


SCALE = 1 << 20
SCRIPT = Path(__file__).resolve().parents[1] / "python/sw_pll/pll_calc.py"


def test_legacy_pwm_register_encoding(capsys):
    # These physical ratios must reproduce app_simple_lut/register_setup.h.
    # Both PWM fields and the integer dividers are minus-one encoded.
    print_regs(2, [204.8, 4, 5], 2, 25, app=1)
    assert capsys.readouterr().out == (
        "APP_PLL_CTL_REG 0x0880CB01\n"
        "APP_PLL_DIV_REG 0x80000018\n"
        "APP_PLL_FRAC_REG 0x80000304\n"
    )


def test_mash_nominal_and_symmetric_range(capsys):
    solutions = find_mash_pll(maxsol=1000, tuning_ppm=1000, ppm_error_max=0.01)
    assert solutions
    assert solutions == sorted(solutions, key=lambda solution: (
        -solution['tuning_ppm'], abs(solution['ppm_error']),
        solution['ref_div'], -solution['op_div']))
    for solution in solutions:
        base_div = int(solution['fb_div'][0])
        effective_div = base_div + solution['mash_word'] / SCALE
        pc_freq = 24 / solution['ref_div']
        divisor = 4 * solution['op_div'] * solution['fin_op_div']
        assert solution['out_freq'] == pytest.approx(pc_freq * effective_div / divisor)
        assert abs(solution['ppm_error']) <= 0.01
        # Check acceptance independently, without the implementation's float
        # reporting values or a numerical tolerance that could mask real error.
        exact_out = Fraction(24, solution['ref_div'] * divisor) * (
            base_div + Fraction(solution['mash_word'], SCALE))
        exact_error = (exact_out / Fraction('12.288') - 1) * 1000000
        assert abs(exact_error) <= Fraction('0.01')
        assert solution['exact'] == (exact_error == 0)
        assert solution['tuning_ppm'] >= 1000
        assert solution['step_hz'] == pytest.approx(pc_freq * 1e6 / (divisor * SCALE))
        for word in (solution['mash_min_word'], solution['mash_max_word']):
            assert math.ceil(0.1 * SCALE) <= word <= math.floor(0.9 * SCALE)
            vco_freq = pc_freq * (base_div + word / SCALE)
            assert 720 <= vco_freq <= 3600
            assert vco_freq / (2 * solution['op_div']) <= 800

    # Explicitly check the example discussed in the design, including the
    # second fixed /2 and the raw (not minus-one encoded) MASH payload.
    example = next(solution for solution in solutions
                   if (solution['ref_div'], solution['op_div'], solution['fin_op_div']) == (1, 8, 4))
    assert example['mash_word'] == 0x89375
    output = capsys.readouterr().out
    assert "APP_PLL_FRAC_REG" not in output
    assert "APP_PLL_MASH_REG 0x89375" in output
    assert "(rounded)" in output


def test_mash_zero_tolerance_requires_exact_frequency():
    # The factor of 125 in 12.288/24 cannot be cancelled by any legal output
    # divider product at this target and VCO range, so a rounded word is needed.
    assert find_mash_pll(output_target=12.288, ppm_error_max=0) == []
    solutions = find_mash_pll(output_target=12.375, ppm_error_max=0)
    assert solutions
    assert all(solution['exact'] and solution['ppm_error'] == 0 for solution in solutions)


def test_mash_search_rounds_within_legal_fraction_window(capsys):
    solutions = find_mash_pll(output_target=12, ppm_error_max=1000, maxsol=10000)
    solution = next(solution for solution in solutions
                    if (solution['ref_div'], int(solution['fb_div'][0]),
                        solution['op_div'], solution['fin_op_div']) == (1, 128, 4, 16))
    assert solution['mash_word'] == 0x1999A
    assert solution['out_freq'] == pytest.approx(12.009375036)
    assert solution['ppm_error'] == pytest.approx(781.253)
    capsys.readouterr()


def test_mash_error_reporting_preserves_tiny_nonzero_values(capsys):
    solution = find_mash_pll(output_target=12.375, maxsol=1)[0]
    capsys.readouterr()
    print_mash_solution(solution)
    assert "ERR +0 ppm (exact)" in capsys.readouterr().out
    # Isolate formatting from the search: a tiny error must not print as zero
    # or acquire an exact label merely because its magnitude is small.
    print_mash_solution(dict(solution, ppm_error=1e-12, exact=False))
    assert "ERR +1e-12 ppm (rounded)" in capsys.readouterr().out


def test_mash_carry_normalization():
    # A value just below an integer rounds through fractional 1.0. It must
    # become the next base divider with a zero word, never a 21-bit payload.
    target = 24 * (66 - 0.25 / SCALE) / 128
    solutions = find_mash_pll(output_target=target, ppm_error_max=1,
                              mash_min=0, mash_max=1, maxsol=10000, raw=True)
    example = next(solution for solution in solutions
                   if (solution['ref_div'], solution['op_div'], solution['fin_op_div']) == (1, 8, 4))
    assert example['mash_word'] == 0
    assert example['fb_div'][0] == 66
    assert all(0 <= solution['mash_word'] < SCALE for solution in solutions)


def test_mash_range_rejection():
    # Even a full unit of fractional headroom cannot provide +/-100% tuning
    # while keeping a legal, fixed integer feedback divider.
    assert find_mash_pll(tuning_ppm=1e6, ppm_error_max=0.01) == []


@pytest.mark.parametrize("arguments", [
    {'input_freq': 0}, {'output_target': -1}, {'output_target': float('nan')},
    {'ppm_error_max': -1}, {'pfcmin': 0.1}, {'maxsol': 0},
    {'mash_min': 0.9, 'mash_max': 0.1}, {'mash_max': 1.1},
    {'tuning_ppm': -1}, {'mash_min': 0.5 + 1e-10, 'mash_max': 0.5 + 1e-9},
])
def test_mash_invalid_arguments(arguments):
    with pytest.raises(ValueError):
        find_mash_pll(**arguments)


@pytest.mark.parametrize("arguments", [
    ['--mash'], ['--app', '--mash', '--denmax', '8'],
    ['--app', '--mash', '--header'], ['--app', '--mash', '--fracmin', '0.2'],
    ['--app', '--tuning-ppm', '1000'],
    ['--error', '0.01'],
])
def test_mash_cli_rejects_incompatible_modes(arguments):
    result = subprocess.run([sys.executable, str(SCRIPT), *arguments],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "error:" in result.stderr


def test_mash_cli_generation():
    result = subprocess.run([
        sys.executable, str(SCRIPT), '--app', '--mash', '--target', '12.288',
        '--tuning-ppm', '1000', '--maxsol', '1', '--error', '0.01',
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "APP_PLL_MASH_REG" in result.stdout
    assert "APP_PLL_FRAC_REG" not in result.stdout
    assert "(rounded)" in result.stdout