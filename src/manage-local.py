#!/usr/bin/env python
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.local')

import warnings

from django.core.cache import CacheKeyWarning

warnings.simplefilter("ignore", CacheKeyWarning)

from django.core.management import (  # noqa: E402  # Configure Django settings before importing its command runner.
    execute_from_command_line,
)

if __name__ == "__main__":
    execute_from_command_line(sys.argv)
