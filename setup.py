#!/usr/bin/env python
from setuptools import setup, find_packages

setup(name="twitblob",
      version="0.0.1",
      description="A tiny JSON bin for every Twitter user.",
      author="Atul Varma",
      author_email="atul@mozilla.com",
      url="http://hg.toolness.com/twitblob",
      packages = find_packages(),
      install_requires = ['oauth2', 'simplejson'],
      license = "MIT License",
      zip_safe = True,
      tests_require=['nose', 'webtest'])
