#!/usr/bin/env python3
"""Run Rust tests for every crate in the repository."""

from __future__ import annotations

import argparse
import pathlib
import sys

from checks.rust_checks.common import run_rust_command


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for Rust test execution.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest_paths",
        metavar="MANIFEST_PATH",
        nargs="*",
        help="Optional `Cargo.toml` paths to test instead of scanning all Rust crates.",
    )
    return parser.parse_args()


def build_command(manifest_path: pathlib.Path) -> list[str]:
    """Build the Cargo test command for a crate manifest.

    Args:
        manifest_path: The `Cargo.toml` file for the crate.

    Returns:
        The test command to execute.
    """
    return [
        "cargo",
        "test",
        "--manifest-path",
        str(manifest_path),
        "--all-features",
        "--locked",
    ]


def main() -> int:
    """Run Cargo test across the repository.

    Returns:
        The test exit code.
    """
    args = parse_args()
    return run_rust_command(
        "Rust tests",
        build_command,
        manifest_paths=args.manifest_paths or None,
    )


if __name__ == "__main__":
    sys.exit(main())
