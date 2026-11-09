#!/usr/bin/env python3
"""Validate that Python version and image settings stay aligned."""

from __future__ import annotations

import re
import sys
import tomllib
from glob import has_magic
from pathlib import Path
from typing import Any

from checks.project_checks import PROJECT_ROOT

# Project
BUILD_ENV_PATH = PROJECT_ROOT / "build.env"
INSTALL_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "install.sh"
PYTHON_VERSION_PATH = PROJECT_ROOT / ".python-version"
ROOT_PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
UV_LOCK_PATH = PROJECT_ROOT / "uv.lock"


def _load_env_file(path: Path) -> dict[str, str]:
    """Read simple `KEY=value` assignments from an environment file.

    Args:
        path: Environment file to parse.

    Returns:
        Mapping of environment variable names to raw string values.

    Raises:
        ValueError: If a non-empty, non-comment line is not a valid assignment.
    """
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        key, separator, value = stripped.partition("=")
        if separator != "=" or not key or not value:
            raise ValueError(f"{path.name} contains an invalid environment assignment: {line}")
        values[key] = value

    return values


def _load_toml(path: Path) -> dict[str, Any]:
    """Read TOML data from a file.

    Args:
        path: TOML file to parse.

    Returns:
        Parsed TOML data.
    """
    with path.open("rb") as file:
        return tomllib.load(file)


def _required_env_value(values: dict[str, str], key: str) -> str:
    """Read a required value from parsed environment settings.

    Args:
        values: Parsed environment values.
        key: Name of the required setting.

    Returns:
        Configured value for `key`.

    Raises:
        ValueError: If `key` is missing.
    """
    value = values.get(key)
    if value is None:
        raise ValueError(f"{BUILD_ENV_PATH.name} must define {key}")

    return value


def _root_pyproject_data() -> dict[str, Any]:
    """Read root `pyproject.toml` data."""
    return _load_toml(ROOT_PYPROJECT_PATH)


def _workspace_member_pyproject_paths() -> tuple[Path, ...]:
    """Discover uv workspace member `pyproject.toml` files from root metadata.

    Returns:
        Workspace member `pyproject.toml` paths, expanding glob-style member patterns.

    Raises:
        ValueError: If workspace members are not configured as a list.
    """
    root_data = _root_pyproject_data()
    workspace_members = (
        root_data.get("tool", {})
        .get("uv", {})
        .get("workspace", {})
        .get("members", ())
    )
    if not isinstance(workspace_members, list):
        raise ValueError(f"{ROOT_PYPROJECT_PATH} must define tool.uv.workspace.members")

    pyproject_paths: set[Path] = set()
    for member in workspace_members:
        if not isinstance(member, str):
            raise ValueError(
                f"{ROOT_PYPROJECT_PATH} tool.uv.workspace.members entries must be strings"
            )

        is_pattern = has_magic(member)
        member_paths = PROJECT_ROOT.glob(member) if is_pattern else (PROJECT_ROOT / member,)
        for member_path in member_paths:
            pyproject_path = member_path / "pyproject.toml"
            if is_pattern and not pyproject_path.is_file():
                continue
            pyproject_paths.add(pyproject_path)

    return tuple(
        sorted(pyproject_paths, key=lambda path: path.relative_to(PROJECT_ROOT).as_posix())
    )


def _python_pyproject_paths() -> tuple[Path, ...]:
    """Discover Python project metadata files that must share the pinned Python version."""
    return (ROOT_PYPROJECT_PATH, *_workspace_member_pyproject_paths())




def _python_app_requirements_paths() -> tuple[Path, ...]:
    """Discover app-local Python requirements files."""
    return tuple(sorted((PROJECT_ROOT / "apps").glob("*/requirements.txt")))






def _assert_uv_version(version: str) -> None:
    """Validate that the configured uv version is an exact semantic version.

    Args:
        version: uv version string to inspect.

    Raises:
        ValueError: If the version is not pinned exactly.
    """
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise ValueError(f"{BUILD_ENV_PATH.name} must pin UV_VERSION as '<major>.<minor>.<patch>'")




def _assert_pyproject_requires_python(path: Path, version: str) -> None:
    """Validate one pyproject declares the pinned Python requirement.

    Args:
        path: `pyproject.toml` file to inspect.
        version: Required Python version.

    Raises:
        ValueError: If `project.requires-python` is not pinned to `version`.
    """
    pyproject_data = _load_toml(path)
    requires_python = pyproject_data.get("project", {}).get("requires-python")
    expected = f"=={version}"
    if requires_python != expected:
        raise ValueError(f"{path} must set project.requires-python to '{expected}'")


def _assert_root_ruff_target(version: str) -> None:
    """Validate the root Ruff target matches the pinned Python version.

    Args:
        version: Required Python version.

    Raises:
        ValueError: If `tool.ruff.target-version` is not aligned.
    """
    pyproject_data = _root_pyproject_data()
    major, minor, _patch = version.split(".")
    expected = f"py{major}{minor}"
    target_version = pyproject_data.get("tool", {}).get("ruff", {}).get("target-version")
    if target_version != expected:
        raise ValueError(f"{ROOT_PYPROJECT_PATH} must set tool.ruff.target-version to '{expected}'")


def _assert_file_contains(path: Path, expected: str) -> None:
    """Validate that a file contains required text.

    Args:
        path: File to inspect.
        expected: Exact text expected inside the file.

    Raises:
        ValueError: If `expected` is missing.
    """
    content = path.read_text(encoding="utf-8")
    if expected not in content:
        raise ValueError(f"{path} must contain: {expected}")


def _assert_file_does_not_contain(path: Path, forbidden: str) -> None:
    """Validate that a file does not contain forbidden text.

    Args:
        path: File to inspect.
        forbidden: Exact text that must be absent from the file.

    Raises:
        ValueError: If `forbidden` is present.
    """
    content = path.read_text(encoding="utf-8")
    if forbidden in content:
        raise ValueError(f"{path} must not contain: {forbidden}")








def _assert_python_app_dependencies_are_packaged() -> None:
    """Validate app containers use package metadata instead of app-local requirements files.

    Raises:
        ValueError: If an app-level `requirements.txt` file exists.
    """
    for path in _python_app_requirements_paths():
        raise ValueError(f"{path} must be represented by package metadata instead")



def _assert_install_script_uses_locked_sync() -> None:
    """Validate `scripts/install.sh` installs from the existing lockfile.

    Raises:
        ValueError: If the install script updates dependency metadata or omits locked sync.
    """
    _assert_file_contains(INSTALL_SCRIPT_PATH, "set -euo pipefail")
    _assert_file_contains(INSTALL_SCRIPT_PATH, "uv sync --locked")
    _assert_file_contains(INSTALL_SCRIPT_PATH, "uv cache prune --ci")
    _assert_file_does_not_contain(INSTALL_SCRIPT_PATH, "uv lock --upgrade")
    _assert_file_does_not_contain(INSTALL_SCRIPT_PATH, "uv add")




def main() -> int:
    """Validate the repository's pinned Python version settings.

    Returns:
        Process exit code. A successful validation returns `0`.
    """
    env_values = _load_env_file(BUILD_ENV_PATH)
    version = _required_env_value(env_values, "PYTHON_VERSION")
    uv_version = _required_env_value(env_values, "UV_VERSION")

    if PYTHON_VERSION_PATH.read_text(encoding="utf-8").strip() != version:
        raise ValueError(f"{PYTHON_VERSION_PATH.name} must contain exactly {version}")

    _assert_uv_version(uv_version)

    for path in _python_pyproject_paths():
        _assert_pyproject_requires_python(path, version)

    _assert_root_ruff_target(version)
    _assert_file_contains(UV_LOCK_PATH, f'requires-python = "=={version}"')
    _assert_python_app_dependencies_are_packaged()
    _assert_install_script_uses_locked_sync()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(1)
