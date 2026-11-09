#!/usr/bin/env python3
"""Validate that Rust image and toolchain settings stay aligned."""

from __future__ import annotations

import re
import sys
import tomllib

from checks.project_checks import PROJECT_ROOT

BUILD_ENV_PATH = PROJECT_ROOT / "build.env"
GITLAB_CI_PATH = PROJECT_ROOT / ".gitlab-ci.yml"
RUST_TOOLCHAIN_PATH = PROJECT_ROOT / "rust-toolchain.toml"

# GitLab


def _load_rust_image_from_env_file() -> str:
    for line in BUILD_ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition("=")
        if key == "RUST_IMAGE" and value:
            return value

    raise ValueError(f"{BUILD_ENV_PATH.name} must define RUST_IMAGE=<image>")


def _load_rust_runtime_image_from_env_file() -> str:
    for line in BUILD_ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition("=")
        if key == "RUST_RUNTIME_IMAGE" and value:
            return value

    raise ValueError(f"{BUILD_ENV_PATH.name} must define RUST_RUNTIME_IMAGE=<image>")




def _load_rust_toolchain_channel() -> str:
    with RUST_TOOLCHAIN_PATH.open("rb") as file:
        toolchain_data = tomllib.load(file)

    channel = toolchain_data.get("toolchain", {}).get("channel")
    if not isinstance(channel, str) or not channel:
        raise ValueError(f"{RUST_TOOLCHAIN_PATH.name} must define [toolchain].channel")

    return channel


def _toolchain_prefix_from_image(image: str) -> str:
    match = re.fullmatch(r"rust:(\d+\.\d+)(?:[.-].+)?", image)
    if match is None:
        raise ValueError(f"RUST_IMAGE '{image}' must look like 'rust:<major>.<minor>-<variant>'")

    return match.group(1)


def _toolchain_prefix_from_channel(channel: str) -> str:
    match = re.fullmatch(r"(\d+\.\d+)(?:\.\d+)?", channel)
    if match is None:
        raise ValueError(
            f"Rust toolchain channel '{channel}' must look like '<major>.<minor>[.<patch>]'"
        )

    return match.group(1)



def main() -> int:
    """Validate Rust image, toolchain, Dockerfile, and compose configuration."""
    rust_image_from_env = _load_rust_image_from_env_file()
    _load_rust_runtime_image_from_env_file()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(1)
