"""Run the prebuilt PFD range test in xsim."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_pfd_timer_ranges(tmp_path):
    if shutil.which("xsim") is None:
        pytest.skip("PFD embedded test requires xsim on PATH")

    source_dir = Path(__file__).resolve().parent / "test_pfd"
    executable = source_dir / "bin" / "test_pfd.xe"
    assert executable.is_file(), f"Prebuilt PFD test executable not found: {executable}"

    result = subprocess.run(
        ["xsim", str(executable)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout

    assert "PASS: PFD timer ranges, wraparound and reset boundaries" in result.stdout, result.stdout