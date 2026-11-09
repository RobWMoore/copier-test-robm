#!/usr/bin/env python3
"""Run Rust type checking for every crate in the repository."""

from __future__ import annotations

import argparse
import pathlib
import sys

from checks.rust_checks.common import run_rust_command


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for Rust type checking.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest_paths",
        metavar="MANIFEST_PATH",
        nargs="*",
        help="Optional file or directory paths to type-check instead of scanning all Rust crates.",
    )
    return parser.parse_args()


def build_command(manifest_path: pathlib.Path) -> list[str]:
    """Build the Cargo type-check command for a crate manifest.

    Args:
        manifest_path: The `Cargo.toml` file for the crate.

    Returns:
        The type-check command to execute.
    """
    return [
        "cargo",
        "check",
        "--manifest-path",
        str(manifest_path),
        "--all-targets",
        "--all-features",
        "--locked",
    ]


def main() -> int:
    """Run Cargo check across the repository.

    Returns:
        The type-check exit code.
    """
    args = parse_args()
    return run_rust_command(
        "Rust type checks",
        build_command,
        manifest_paths=args.manifest_paths or None,
    )


if __name__ == "__main__":
    sys.exit(main())
