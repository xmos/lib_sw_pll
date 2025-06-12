# Copyright 2023-2025 XMOS LIMITED.
# This Software is subject to the terms of the XMOS Public Licence: Version 1.
from setuptools import setup, find_packages

setup(
    name="sw_pll",
    version="3.2.1",
    packages=["sw_pll"],
    package_dir={
        "": "."
    },
    install_requires=[
        "numpy==2.1.*",
        "matplotlib==3.9.*",
        "soundfile==0.12.*",
        "scipy==1.14.*",
    ]
)

