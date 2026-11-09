"""Manage the root Cargo workspace manifest."""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

import tomlkit
from tomlkit.items import Array, Table

from repo_tooling import _utils


def add_workspace_member(repo_root: Path, crate_path: str) -> None:
    """Add a repository-local Rust crate to the root Cargo workspace.

    The operation is idempotent and preserves the existing manifest formatting.
    """
    repo_root = repo_root.resolve()
    workspace_manifest = repo_root / "Cargo.toml"
    requested_directory = Path(crate_path)
    crate_directory = (
        requested_directory
        if requested_directory.is_absolute()
        else repo_root / requested_directory
    ).resolve()

    try:
        crate_directory.relative_to(repo_root)
    except ValueError as error:
        raise ValueError(f"crate directory must be inside the repository: {crate_path}") from error

    if not workspace_manifest.is_file():
        raise ValueError(f"workspace manifest not found: {workspace_manifest}")
    if not crate_directory.is_dir():
        raise ValueError(f"crate directory does not exist: {crate_path}")
    if not (crate_directory / "Cargo.toml").is_file():
        raise ValueError(f"no Cargo.toml found in crate directory: {crate_path}")

    try:
        document = tomlkit.parse(workspace_manifest.read_text())
    except tomlkit.exceptions.ParseError as error:
        raise ValueError(f"could not parse {workspace_manifest}: {error}") from error

    workspace = document.get("workspace")
    if workspace is None:
        workspace = tomlkit.table()
        document["workspace"] = workspace
    if not isinstance(workspace, Table):
        raise ValueError("[workspace] must be a TOML table.")

    members = workspace.get("members")
    if members is None:
        members = tomlkit.array().multiline(True)
        workspace["members"] = members
    if not isinstance(members, Array):
        raise ValueError("workspace.members must be an array.")

    member_path = crate_directory.relative_to(repo_root).as_posix()
    if member_path in {str(member) for member in members}:
        return

    members.append(member_path)
    workspace_manifest.write_text(tomlkit.dumps(document))


def package_name(path: Path) -> str:
    """Return the validated package name declared by a Cargo manifest."""
    with path.open("rb") as file:
        package = tomllib.load(file).get("package")
    if not isinstance(package, dict) or not isinstance(package.get("name"), str):
        raise TypeError(f"Rust library has no [package].name: {path}")
    return package["name"]


def depends_on(data: dict[str, object], expected_name: str) -> bool:
    """Return whether Cargo dependency sections refer to a normalised package name."""
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        dependencies = data.get(section)
        if not isinstance(dependencies, dict):
            continue
        for dependency_name, specification in dependencies.items():
            if _utils.normalise_name(str(dependency_name)) == expected_name:
                return True
            if (
                isinstance(specification, dict)
                and _utils.normalise_name(str(specification.get("package", ""))) == expected_name
            ):
                return True
    return False


def dependants(repo_root: Path, target: Path, name: str) -> list[Path]:
    """Return repository Cargo packages that depend on the target package."""
    result: list[Path] = []
    expected_name = _utils.normalise_name(name)
    manifests = [
        *repo_root.glob("apps/*/Cargo.toml"),
        *repo_root.glob("libs/*/Cargo.toml"),
    ]
    for manifest in sorted(manifests):
        if manifest.parent == target:
            continue
        with manifest.open("rb") as file:
            if depends_on(tomllib.load(file), expected_name):
                result.append(manifest.parent.relative_to(repo_root))
    return result


def remove_workspace_member(repo_root: Path, crate_path: str) -> None:
    """Remove a repository-local crate from the root Cargo workspace if present."""
    manifest = repo_root / "Cargo.toml"
    document = tomlkit.parse(manifest.read_text())
    workspace = document.get("workspace")
    members = workspace.get("members") if isinstance(workspace, Table) else None
    if not isinstance(members, Array) or crate_path not in {str(member) for member in members}:
        return
    members.remove(crate_path)
    manifest.write_text(tomlkit.dumps(document))


def cargo_metadata(manifest: Path, repo_root: Path) -> dict[str, object]:
    """Return Cargo metadata for the package described by a manifest file."""
    command = [
        "cargo",
        "metadata",
        "--no-deps",
        "--locked",
        "--format-version=1",
        "--manifest-path",
        str(manifest),
    ]
    completed = subprocess.run(command, cwd=repo_root, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def package_metadata(metadata: dict[str, object], manifest: Path) -> dict[str, object]:
    """Return the Cargo metadata package record matching a manifest file."""
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        raise ValueError("Cargo metadata has no packages list")

    for package in packages:
        if not isinstance(package, dict):
            continue
        package_manifest = Path(str(package.get("manifest_path"))).resolve()
        if package_manifest == manifest.resolve():
            return package
    raise ValueError(f"Cargo metadata does not contain package: {manifest}")


def binary_names(package: dict[str, object]) -> list[str]:
    """Return the binary target names declared by a Cargo package record."""
    targets = package.get("targets")
    if not isinstance(targets, list):
        raise ValueError(f"Rust CLI package has no targets list: {package.get('name')}")

    names: list[str] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        name = target.get("name")
        kinds = target.get("kind")
        if isinstance(name, str) and isinstance(kinds, list) and "bin" in kinds:
            names.append(name)
    if not names:
        raise ValueError(f"Rust CLI package has no binary targets: {package.get('name')}")
    return names
