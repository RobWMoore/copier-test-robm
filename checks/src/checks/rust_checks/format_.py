#!/usr/bin/env python3
"""Run Rust formatting checks for every crate in the repository."""

from __future__ import annotations

import argparse
import pathlib
import sys

from checks.rust_checks.common import run_rust_command


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Rust formatter.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Validate formatting and make any fixes",
    )
    return parser.parse_args()


def build_command(manifest_path: pathlib.Path, *, check: bool) -> list[str]:
    """Build the Cargo formatter command for a crate manifest.

    Args:
        manifest_path: The `Cargo.toml` file for the crate.
        check: Whether to run in check-only mode.

    Returns:
        The formatter command to execute.
    """
    command = ["cargo", "fmt", "--manifest-path", str(manifest_path)]
    if check:
        command.append("--check")
    return command


def main() -> int:
    """Run Rust formatting across the repository.

    Returns:
        The formatter exit code.
    """
    args = parse_args()
    description = "Rust formatting with fixes" if args.fix else "Rust formatting"
    return run_rust_command(
        description,
        lambda manifest_path: build_command(manifest_path, check=not args.fix),
    )


if __name__ == "__main__":
    sys.exit(main())
