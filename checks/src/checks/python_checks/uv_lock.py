#!/usr/bin/env python3
"""Validate or update the repository's uv lockfile."""

from __future__ import annotations

import argparse
import subprocess
import sys

from checks.project_checks import PROJECT_ROOT


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for uv lock validation.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update `uv.lock` instead of checking whether it is current.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Refresh uv package metadata before checking. This is implied by --apply so stale "
            "ignored build metadata, such as *.egg-info, cannot mask lockfile updates."
        ),
    )
    return parser.parse_args()


def main() -> int:
    """Run `uv lock` in either check or update mode.

    Returns:
        The `uv lock` exit code.
    """
    args = parse_args()
    command = ["uv", "lock"]
    if args.apply or args.refresh:
        command.append("--refresh")
    if not args.apply:
        command.append("--check")

    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
