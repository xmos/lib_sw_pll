# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.

"""Isolate generated files and schedule shared simulator fixtures safely.

Use pytest -n N --dist=loadgroup to run fixture groups concurrently without
repeating a closed-loop trace for each assertion. Every worker has separate
artifact storage and every module has its own temporary working directory.
VX xsim coverage remains opt-in so XS-only runs need no VX tools.
"""

from pathlib import Path

import pytest


@pytest.fixture(scope="module", autouse=True)
def isolated_model_workdir(tmp_path_factory):
	"""Legacy models write relative headers; never share them across workers."""
	workdir = tmp_path_factory.mktemp("pll-model")
	with pytest.MonkeyPatch.context() as patch:
		patch.chdir(workdir)
		yield


@pytest.fixture(scope="module")
def bin_dir(request):
	"""Keep CSV, plots and timing reports separate even with default xdist load."""
	worker = getattr(request.config, "workerinput", {}).get("workerid", "master")
	output = Path(__file__).resolve().parent / "bin" / worker
	output.mkdir(parents=True, exist_ok=True)
	return output


def pytest_addoption(parser):
	parser.addoption("--run-mash", action="store_true", default=False,
					 help="Run MASH C/Python tests using VX xsim and test_mash.xe")


def pytest_configure(config):
	config.addinivalue_line("markers", "mash_xsim: requires the VX tools and MASH test executable")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
	skip = pytest.mark.skip(reason="VX MASH xsim tests require --run-mash")
	for item in items:
		# xdist applies these groups after collection. All assertions using the
		# same expensive fixture parameter must stay on a single worker.
		callspec = getattr(item, "callspec", None)
		if callspec is not None:
			for fixture_name in ("basic_test_vector", "mash_test_vector"):
				if fixture_name in callspec.params:
					reference_rate, adapter = callspec.params[fixture_name]
					group = f"{fixture_name}-{reference_rate}-{adapter.__name__}"
					item.add_marker(pytest.mark.xdist_group(name=group))
		if "mash_xsim" in item.keywords and not config.getoption("--run-mash"):
			item.add_marker(skip)
