# Copyright 2023-2026 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.
from setuptools import setup, find_packages

setup(
    name="sw_pll",
    version="2.5.0",
    packages=["sw_pll"],
    package_dir={
        "": "."
    },
    install_requires=[
        "numpy==2.2.*",
        "matplotlib==3.10.*",
        "soundfile==0.14.*",
        "scipy==1.15.*",
    ]
)

