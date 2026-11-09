"""Repository-wide paths and release metadata validation."""

from __future__ import annotations

import pathlib
import re
import tomllib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
VERSION_PATH = PROJECT_ROOT / "VERSION"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
SEMVER_PATTERN = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?"
)


def canonical_version() -> str:
    """Return the single version recorded in the canonical VERSION file."""
    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError(f"{VERSION_PATH.name} must contain a semantic version, got {version!r}")
    return version


def project_version() -> str:
    """Return the root Python package version."""
    with PYPROJECT_PATH.open("rb") as file:
        project_data = tomllib.load(file)
    version = project_data.get("project", {}).get("version")
    if not isinstance(version, str):
        raise ValueError(f"{PYPROJECT_PATH.name} must define project.version")
    return version


def validate_release_version() -> None:
    """Ensure the root package version matches the canonical release version."""
    version = canonical_version()
    package_version = project_version()
    if package_version != version:
        raise ValueError(
            f"{PYPROJECT_PATH.name} project.version must match {VERSION_PATH.name}: "
            f"{package_version!r} != {version!r}"
        )
