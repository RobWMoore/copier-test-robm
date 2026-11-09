"""Shared helpers for Rust repository checks."""

from __future__ import annotations

import pathlib
import subprocess
import sys
from collections.abc import Callable, Sequence

from checks.project_checks import PROJECT_ROOT

RUST_CODE_DIRECTORIES = ("apps", "libs", "scripts")


def _relative_path(path: pathlib.Path) -> pathlib.Path:
    """Return a project-relative path when possible.

    Args:
        path: The path to normalise.

    Returns:
        The path relative to `PROJECT_ROOT` when it is inside the repository, otherwise the
        original path.
    """
    try:
        return path.relative_to(PROJECT_ROOT)
    except ValueError:
        return path


def cargo_manifests() -> list[pathlib.Path]:
    """Discover Rust crate manifests beneath the repository code directories.

    Returns:
        A sorted list of `Cargo.toml` paths for all detected Rust crates.
    """
    manifests: list[pathlib.Path] = []
    for directory in RUST_CODE_DIRECTORIES:
        root = PROJECT_ROOT / directory
        if not root.exists():
            continue

        for manifest in root.rglob("Cargo.toml"):
            # Rust build outputs can contain copied manifests inside `target/`, which should never
            # be treated as source crates.
            if "target" not in manifest.parts:
                manifests.append(manifest)

    return sorted(manifests)


def _is_source_manifest(path: pathlib.Path) -> bool:
    """Return whether a `Cargo.toml` path refers to a source manifest.

    Args:
        path: The candidate manifest path.

    Returns:
        `True` when the file is a `Cargo.toml` outside Rust build output directories.
    """
    return path.name == "Cargo.toml" and "target" not in path.parts


def rust_manifests_for_target(target: pathlib.Path) -> list[pathlib.Path]:
    """Return Rust manifests addressed by a target path.

    Args:
        target: A file or directory path supplied on the command line.

    Returns:
        A sorted list of `Cargo.toml` files addressed by `target`.
    """
    if target.is_file():
        return [target] if _is_source_manifest(target) else []

    direct_manifest = target / "Cargo.toml"
    if direct_manifest.is_file() and _is_source_manifest(direct_manifest):
        return [direct_manifest]

    if not target.is_dir():
        return []

    manifests = [
        manifest_path
        for manifest_path in target.rglob("Cargo.toml")
        if _is_source_manifest(manifest_path)
    ]
    return sorted(manifests)


def resolve_rust_manifest_targets(targets: Sequence[str]) -> list[pathlib.Path]:
    """Resolve command-line Rust target paths into concrete manifest paths.

    Args:
        targets: File or directory paths supplied to a Rust check helper.

    Returns:
        A sorted list of unique `Cargo.toml` paths.

    Raises:
        ValueError: If any target path does not exist or does not resolve to a Rust manifest.
    """
    working_directory = pathlib.Path.cwd()
    manifests: set[pathlib.Path] = set()

    for target in targets:
        resolved_target = pathlib.Path(target)
        if not resolved_target.is_absolute():
            resolved_target = (working_directory / resolved_target).resolve()
        else:
            resolved_target = resolved_target.resolve()

        if not resolved_target.exists():
            raise ValueError(f"Rust target does not exist: {target}")

        target_manifests = rust_manifests_for_target(resolved_target)
        if not target_manifests:
            raise ValueError(f"No Cargo.toml files found for Rust target: {target}")

        manifests.update(target_manifests)

    return sorted(manifests)


def _display_path(path: pathlib.Path) -> str:
    """Render a project-relative path for command logging.

    Args:
        path: The path to render.

    Returns:
        A project-relative string when possible, otherwise the absolute path.
    """
    return str(_relative_path(path))


def run_command(command: Sequence[str], *, cwd: pathlib.Path) -> int:
    """Execute a subprocess and return its exit code.

    Args:
        command: The command and arguments to execute.
        cwd: The working directory for the subprocess.

    Returns:
        The subprocess exit code, or `1` if the command is unavailable.
    """
    print(f"Running {' '.join(command)} in {_display_path(cwd)}")
    try:
        return subprocess.run(command, cwd=cwd, check=False).returncode
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1


def run_rust_command(
    description: str,
    command_builder: Callable[[pathlib.Path], Sequence[str]],
    *,
    manifest_paths: Sequence[str] | None = None,
) -> int:
    """Run a Cargo-based validation command across every Rust crate in the repo.

    Args:
        description: Human-readable label for skip messaging.
        command_builder: A callable that constructs the command for a given manifest path.
        manifest_paths: Optional file or directory paths that narrow the Rust crates to inspect.

    Returns:
        Zero when no Rust crates are present or all commands succeed; otherwise the first non-zero
        exit code.
    """
    if manifest_paths is None:
        manifests = cargo_manifests()
        if not manifests:
            print(
                f"No Rust crates detected under apps/, libs/, or scripts/; "
                f"skipping {description}."
            )
            return 0
    else:
        try:
            manifests = resolve_rust_manifest_targets(manifest_paths)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1

    for manifest in manifests:
        exit_code = run_command(
            list(command_builder(manifest)),
            cwd=PROJECT_ROOT,
        )
        if exit_code:
            return exit_code

    return 0
