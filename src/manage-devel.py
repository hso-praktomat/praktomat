#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.devel')

import warnings
from django.core.cache import CacheKeyWarning
warnings.simplefilter("ignore", CacheKeyWarning)

from django.core.management import execute_from_command_line
if __name__ == "__main__":
    execute_from_command_line(sys.argv)
