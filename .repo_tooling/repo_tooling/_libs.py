"""Shared helpers for creating and removing Python and Rust libraries."""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_tooling import _config


@dataclass(frozen=True)
class LibraryConfig:
    """Language-specific values used to manage a library."""

    language: str
    prompt: str
    default_name: str
    empty_name_error: str
    existing_directory_error: str
    version_data: str
    manifest_name: str

    @classmethod
    def python(cls, version: str) -> LibraryConfig:
        return cls(
            "python",
            "Package name",
            "my_python_library",
            "package name must contain at least one letter or digit.",
            "package directory already exists",
            f"python_version={version}",
            "pyproject.toml",
        )

    @classmethod
    def rust(cls, version: str) -> LibraryConfig:
        return cls(
            "rust",
            "Rust library name",
            "my_rust_library",
            "Rust library name must contain at least one letter or digit.",
            "Rust library directory already exists",
            f"rust_msrv={version}",
            "Cargo.toml",
        )


def configs(enabled_only: bool = False) -> list[LibraryConfig]:
    """Build current language configurations, optionally filtering creation choices."""
    available = [
        LibraryConfig.python(_config.PYTHON_VERSION),
        LibraryConfig.rust(_config.RUST_MSRV),
    ]
    if enabled_only:
        return [
            item for item in available if item.language in _config.ENABLED_PROGRAMMING_LANGUAGES
        ]
    return available


def choose_config(configs: Sequence[LibraryConfig]) -> LibraryConfig:
    """Return the only language configuration or prompt for one of several."""
    if not configs:
        raise _config.ConfigurationError("language not enabled: python or rust.")
    if len(configs) == 1:
        return configs[0]
    print("Select a library language to create:")
    for index, config in enumerate(configs, start=1):
        print(f"{index}) {config.language.title()}")
    while True:
        selection = input("Language number: ")
        try:
            index = int(selection)
            if 1 <= index <= len(configs):
                return configs[index - 1]
            raise ValueError
        except ValueError:
            print(f"Invalid selection: {selection}", file=sys.stderr)


def to_snake_case(value: str) -> str:
    """Return the shell generators' ASCII snake-case representation of a name."""
    return re.sub(r"_+$", "", re.sub(r"^_+", "", re.sub(r"[^a-z0-9]+", "_", value.lower())))


def library_config(library: Path, configs: Sequence[LibraryConfig]) -> LibraryConfig:
    """Return the one language configuration matching a library manifest."""
    matches = [config for config in configs if (library / config.manifest_name).is_file()]
    if len(matches) != 1:
        found = ", ".join(config.language for config in matches) or "none"
        raise ValueError(
            "Library must contain exactly one supported manifest "
            f"(pyproject.toml or Cargo.toml): {library} (found {found})"
        )
    return matches[0]


def libraries(libraries_root: Path, configs: Sequence[LibraryConfig]) -> list[Path]:
    """Return direct, non-symlink library directories with one supported manifest."""
    if not libraries_root.is_dir():
        return []
    result: list[Path] = []
    for directory in sorted(libraries_root.iterdir()):
        if not directory.is_dir() or directory.is_symlink():
            continue
        try:
            library_config(directory, configs)
        except ValueError:
            continue
        result.append(directory)
    return result


def library_directory(repo_root: Path, value: str, config: LibraryConfig) -> Path:
    """Validate that value identifies a direct library child of the expected language."""
    directory = (repo_root / value).resolve()
    if directory.parent != (repo_root / "libs").resolve() or not directory.is_dir():
        raise ValueError(f"Library must be an existing direct child of libs/: {value}")
    if not (directory / config.manifest_name).is_file():
        raise ValueError(
            f"{config.language.title()} library has no {config.manifest_name}: {value}"
        )
    return directory


def choose_library(available_libraries: Sequence[Path]) -> Path | None:
    """Prompt for one library to remove, or return None when the user quits."""
    print("Select a library to remove:")
    print("Enter q to quit.")
    for index, library in enumerate(available_libraries, start=1):
        print(f"{index}) {library.name}")
    while True:
        selection = input("Library number: ")
        if selection.lower() == "q":
            return None
        try:
            index = int(selection)
            if 1 <= index <= len(available_libraries):
                return available_libraries[index - 1]
            raise ValueError
        except ValueError:
            print(f"Invalid selection: {selection}", file=sys.stderr)
