#!/usr/bin/env python3
from __future__ import annotations

import sys

import checks_superstaq

from checks.python_checks.common import COMMON_EXCLUDES

if __name__ == "__main__":
    args = [
        *sys.argv[1:],
        "--sysmon",
    ]
    if COMMON_EXCLUDES:
        args += ["--exclude", *COMMON_EXCLUDES]
    sys.exit(checks_superstaq.coverage_.run(*args))
