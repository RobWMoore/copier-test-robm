#!/usr/bin/env python3
from __future__ import annotations

import sys

import checks_superstaq

if __name__ == "__main__":
    sys.exit(checks_superstaq.configs.run(*sys.argv[1:]))
