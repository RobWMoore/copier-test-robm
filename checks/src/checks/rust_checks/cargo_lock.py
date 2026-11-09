#!/usr/bin/env python3
"""Validate or refresh the Rust workspace lockfile."""

from __future__ import annotations

import argparse
import sys

from checks.project_checks import PROJECT_ROOT
from checks.rust_checks.common import run_command


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for Cargo lockfile validation.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Refresh `Cargo.lock` instead of checking whether it is consistent.",
    )
    return parser.parse_args()


def build_command(*, apply: bool) -> list[str]:
    """Build the Cargo workspace lockfile command.

    Args:
        apply: Whether to refresh the lockfile instead of validating it.

    Returns:
        The Cargo command to execute from the workspace root.
    """
    if apply:
        return ["cargo", "update"]
    return ["cargo", "fetch", "--locked"]


def main() -> int:
    """Run Cargo workspace lockfile validation or refreshes.

    Returns:
        The Cargo exit code.
    """
    args = parse_args()
    return run_command(build_command(apply=args.apply), cwd=PROJECT_ROOT)


if __name__ == "__main__":
    sys.exit(main())
