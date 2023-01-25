from setuptools import setup, find_packages

setup(
    name="sw_pll",
    version="0.0.1",
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
