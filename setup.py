# Copyright 2023 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.
from setuptools import setup, find_packages

setup(
    name="sw_pll",
    version="2.0.0",
    packages=["sw_pll"],
    package_dir={
        "": "python"
    },
    install_requires=[
        "numpy",
        "matplotlib",
        "pyvcd"
    ]
)
