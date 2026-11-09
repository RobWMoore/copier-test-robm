#!/usr/bin/env python3
"""Run Rust linting for every crate in the repository."""

from __future__ import annotations

import argparse
import pathlib
import sys

from checks.rust_checks.common import run_rust_command


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for Rust linting.

    Returns:
        The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest_paths",
        metavar="MANIFEST_PATH",
        nargs="*",
        help="Optional file or directory paths to lint instead of scanning all Rust crates.",
    )
    return parser.parse_args()


def build_command(manifest_path: pathlib.Path) -> list[str]:
    """Build the Cargo clippy command for a crate manifest.

    Args:
        manifest_path: The `Cargo.toml` file for the crate.

    Returns:
        The lint command to execute.
    """
    return [
        "cargo",
        "clippy",
        "--manifest-path",
        str(manifest_path),
        "--all-targets",
        "--all-features",
        "--locked",
        "--",
        "-D",
        "warnings",
        "-W",
        "clippy::pedantic",
    ]


def main() -> int:
    """Run Cargo clippy across the repository.

    Returns:
        The linter exit code.
    """
    args = parse_args()
    return run_rust_command(
        "Rust linting",
        build_command,
        manifest_paths=args.manifest_paths or None,
    )


if __name__ == "__main__":
    sys.exit(main())
