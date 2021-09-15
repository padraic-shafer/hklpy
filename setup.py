#!/usr/bin/env python
from setuptools import setup, find_packages
import versioneer


description = (
    "Controls for using diffractometers within the"
    " Bluesky Framework: https://blueskyproject.io"
)

setup(
    name="hklpy",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description=description,
    long_description=description,
    maintainer="prjemian",
    maintainer_email="prjemian+hklpy@gmail.com",
    url="https://github.com/bluesky/hklpy",
    license="BSD",
    packages=find_packages(),
)
