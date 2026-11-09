#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys


def main(args: list[str]) -> int:
    """Build the MkDocs site."""
    return subprocess.call(["mkdocs", "build", "--clean", *args])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
