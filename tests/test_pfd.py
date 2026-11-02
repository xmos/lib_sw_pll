# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

"""Run the prebuilt PFD range test in xsim."""

from pathlib import Path
import shutil
import subprocess

import pytest


def run_pfd(tmp_path, *arguments):
    if shutil.which("xsim") is None:
        pytest.skip("PFD embedded test requires xsim on PATH")

    source_dir = Path(__file__).resolve().parent / "test_pfd"
    executable = source_dir / "bin" / "test_pfd.xe"
    assert executable.is_file(), f"Prebuilt PFD test executable not found: {executable}"

    result = subprocess.run(
        ["xsim", "--args", str(executable), *arguments],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=180,
        check=False,
    )
    return result


def test_pfd_timer_ranges(tmp_path):
    result = run_pfd(tmp_path)
    assert result.returncode == 0, result.stdout

    assert "PASS: PFD timer ranges, wraparound and reset boundaries" in result.stdout, result.stdout


@pytest.mark.parametrize("case", [
    "zero-loop", "zero-ratio", "mclk-overflow", "ref-overflow",
    "threshold-half-range", "threshold-truncation", "threshold-product-overflow",
])
def test_pfd_rejects_invalid_init(tmp_path, case):
    result = run_pfd(tmp_path, case)
    assert f"Testing invalid init: {case}" in result.stdout, result.stdout
    assert result.returncode != 0, result.stdout
    assert (
        "assert" in result.stdout.lower()
        or "Unhandled exception: ECALL, data: 0x00000000" in result.stdout
    ), result.stdout
    assert "FAIL:" not in result.stdout, result.stdout