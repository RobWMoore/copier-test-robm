"""Tests for Cargo manifest and workspace management."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

from repo_tooling import _cargo


def test_add_workspace_member_adds_and_deduplicates_a_crate(tmp_path: Path) -> None:
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text("[workspace]\nmembers = []\n")
    crate = tmp_path / "libs" / "demo"
    crate.mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')

    _cargo.add_workspace_member(tmp_path, "libs/demo")
    _cargo.add_workspace_member(tmp_path, "libs/demo")

    assert manifest.read_text().count('"libs/demo"') == 1


def test_add_workspace_member_creates_workspace_members(tmp_path: Path) -> None:
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text('[package]\nname = "root"\nversion = "0.1.0"\n')
    crate = tmp_path / "apps" / "demo"
    crate.mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')

    _cargo.add_workspace_member(tmp_path, "apps/demo")

    assert "[workspace]" in manifest.read_text()
    assert '"apps/demo"' in manifest.read_text()


@pytest.mark.parametrize(
    ("manifest", "crate_path", "message"),
    [
        (
            '[workspace]\nmembers = "apps/demo"\n',
            "apps/demo",
            "workspace.members must be an array",
        ),
        ("[workspace]\nmembers = []\n", "../outside", "must be inside the repository"),
    ],
)
def test_add_workspace_member_rejects_invalid_configuration(
    tmp_path: Path, manifest: str, crate_path: str, message: str
) -> None:
    (tmp_path / "Cargo.toml").write_text(manifest)
    crate = tmp_path / "apps" / "demo"
    crate.mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')

    with pytest.raises(ValueError, match=message):
        _cargo.add_workspace_member(tmp_path, crate_path)


def test_add_workspace_member_rejects_a_missing_crate_manifest(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers = []\n")
    (tmp_path / "apps" / "demo").mkdir(parents=True)

    with pytest.raises(ValueError, match="no Cargo.toml found"):
        _cargo.add_workspace_member(tmp_path, "apps/demo")


def test_add_workspace_member_rejects_a_missing_workspace_manifest(tmp_path: Path) -> None:
    crate = tmp_path / "apps" / "demo"
    crate.mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "demo"\n')

    with pytest.raises(ValueError, match="workspace manifest not found"):
        _cargo.add_workspace_member(tmp_path, "apps/demo")

    assert not (tmp_path / "Cargo.toml").exists()


def test_add_workspace_member_rejects_a_missing_crate_directory(tmp_path: Path) -> None:
    manifest = tmp_path / "Cargo.toml"
    original = "[workspace]\nmembers = []\n"
    manifest.write_text(original)

    with pytest.raises(ValueError, match="crate directory does not exist"):
        _cargo.add_workspace_member(tmp_path, "apps/missing")

    assert manifest.read_text() == original


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("[workspace\n", "could not parse"),
        ('workspace = "invalid"\n', r"\[workspace\] must be a TOML table"),
    ],
)
def test_add_workspace_member_preserves_invalid_manifests(
    tmp_path: Path, content: str, message: str
) -> None:
    """Report invalid workspace configuration without overwriting the user's manifest."""
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text(content)
    crate = tmp_path / "apps" / "demo"
    crate.mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "demo"\n')

    with pytest.raises(ValueError, match=message):
        _cargo.add_workspace_member(tmp_path, "apps/demo")

    assert manifest.read_text() == content


def test_package_name_reads_the_package_name(tmp_path: Path) -> None:
    """Read the package name from a valid Cargo manifest."""
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text('[package]\nname = "demo-library"\nversion = "0.1.0"\n')

    assert _cargo.package_name(manifest) == "demo-library"


def test_package_name_rejects_a_manifest_without_a_name(tmp_path: Path) -> None:
    """Reject Cargo manifests that do not define a package name."""
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text('[package]\nversion = "0.1.0"\n')

    with pytest.raises(TypeError, match=r"no \[package\]\.name"):
        _cargo.package_name(manifest)


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        ('[dependencies]\ndemo-library = "1.0"\n', True),
        ('[dev-dependencies]\ndemo = { package = "demo-library", version = "1.0" }\n', True),
        ('[build-dependencies]\nother = "1.0"\n', False),
    ],
)
def test_depends_on_checks_direct_and_renamed_dependencies(manifest: str, expected: bool) -> None:
    """Recognise package dependencies in Cargo's supported dependency sections."""
    assert _cargo.depends_on(tomllib.loads(manifest), "demo-library") is expected


def test_dependants_finds_apps_and_libraries_that_use_a_package(tmp_path: Path) -> None:
    """Find dependants across both repository application and library directories."""
    target = tmp_path / "libs" / "target"
    target.mkdir(parents=True)
    (target / "Cargo.toml").write_text('[package]\nname = "target-library"\n')
    app = tmp_path / "apps" / "client"
    app.mkdir(parents=True)
    (app / "Cargo.toml").write_text('[dependencies]\ntarget-library = "1.0"\n')
    library = tmp_path / "libs" / "helper"
    library.mkdir(parents=True)
    (library / "Cargo.toml").write_text(
        '[dependencies]\ntarget = { package = "target-library", version = "1.0" }\n'
    )

    assert _cargo.dependants(tmp_path, target, "target-library") == [
        Path("apps/client"),
        Path("libs/helper"),
    ]


def test_remove_workspace_member_removes_an_existing_member(tmp_path: Path) -> None:
    """Remove a workspace member without changing other members."""
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text('[workspace]\nmembers = ["apps/client", "libs/demo"]\n')

    _cargo.remove_workspace_member(tmp_path, "libs/demo")
    after_removal = manifest.read_text()
    _cargo.remove_workspace_member(tmp_path, "libs/demo")

    assert '"apps/client"' in after_removal
    assert '"libs/demo"' not in after_removal
    assert manifest.read_text() == after_removal


def test_cargo_metadata_runs_cargo_with_the_requested_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Request locked, dependency-free Cargo metadata for one manifest."""
    manifest = tmp_path / "apps" / "demo" / "Cargo.toml"
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '{"packages": []}', "")

    monkeypatch.setattr(_cargo.subprocess, "run", run)

    assert _cargo.cargo_metadata(manifest, tmp_path) == {"packages": []}
    assert calls == [
        (
            [
                "cargo",
                "metadata",
                "--no-deps",
                "--locked",
                "--format-version=1",
                "--manifest-path",
                str(manifest),
            ],
            {"cwd": tmp_path, "check": True, "capture_output": True, "text": True},
        )
    ]


def test_package_metadata_selects_the_matching_manifest(tmp_path: Path) -> None:
    """Select the metadata package entry for the requested manifest."""
    manifest = tmp_path / "apps" / "demo" / "Cargo.toml"
    package = {"manifest_path": str(manifest), "name": "demo"}

    assert _cargo.package_metadata({"packages": [{}, package]}, manifest) == package


@pytest.mark.parametrize("invalid_entry", [None, "invalid"])
def test_package_metadata_skips_malformed_entries(tmp_path: Path, invalid_entry: object) -> None:
    manifest = tmp_path / "Cargo.toml"
    package = {"manifest_path": str(manifest), "name": "demo"}

    assert _cargo.package_metadata({"packages": [invalid_entry, package]}, manifest) == package


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({}, "has no packages list"),
        ({"packages": []}, "does not contain package"),
    ],
)
def test_package_metadata_rejects_missing_package_data(
    tmp_path: Path, metadata: dict[str, object], message: str
) -> None:
    """Reject malformed metadata and metadata without the requested package."""
    with pytest.raises(ValueError, match=message):
        _cargo.package_metadata(metadata, tmp_path / "Cargo.toml")


def test_binary_names_selects_binary_targets() -> None:
    """Return only binary target names from a Cargo package record."""
    package: dict[str, object] = {
        "name": "demo",
        "targets": [
            {"name": "demo", "kind": ["bin"]},
            {"name": "demo-lib", "kind": ["lib"]},
            {"name": "tool", "kind": ["bin", "test"]},
        ],
    }

    assert _cargo.binary_names(package) == ["demo", "tool"]


@pytest.mark.parametrize("invalid_entry", [None, "invalid"])
def test_binary_names_skips_malformed_targets(invalid_entry: object) -> None:
    package: dict[str, object] = {"targets": [invalid_entry, {"name": "demo", "kind": ["bin"]}]}

    assert _cargo.binary_names(package) == ["demo"]


@pytest.mark.parametrize(
    ("package", "message"),
    [
        ({"name": "demo"}, "has no targets list"),
        ({"name": "demo", "targets": [{"name": "demo", "kind": ["lib"]}]}, "no binary targets"),
    ],
)
def test_binary_names_rejects_packages_without_binaries(
    package: dict[str, object], message: str
) -> None:
    """Reject package records that do not declare executable targets."""
    with pytest.raises(ValueError, match=message):
        _cargo.binary_names(package)
