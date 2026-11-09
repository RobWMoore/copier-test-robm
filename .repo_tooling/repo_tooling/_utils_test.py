"""Test private repository-local tooling helpers."""

from pathlib import Path

import pytest

from repo_tooling import _utils


def test_repo_root_resolves_tooling_module_path(tmp_path: Path) -> None:
    """Resolve the root for a repository-local tooling module."""
    repository_root = tmp_path / "repository"

    assert (
        _utils.repo_root(repository_root / ".repo_tooling" / "repo_tooling" / "command.py")
        == repository_root
    )


def test_repo_root_resolves_nested_make_script_path(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    command = repository_root / ".repo_tooling" / "repo_tooling" / "make_scripts" / "command.py"

    assert _utils.repo_root(command) == repository_root


def test_repo_root_uses_nearest_tooling_ancestor(tmp_path: Path) -> None:
    """Resolve nested repositories against their own tooling directory."""
    repository_root = tmp_path / ".repo_tooling" / "outer" / "nested-repository"
    command = repository_root / ".repo_tooling" / "repo_tooling" / "command.py"

    assert _utils.repo_root(command) == repository_root


def test_repo_root_rejects_path_without_tooling_ancestor(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No .repo_tooling ancestor found"):
        _utils.repo_root(tmp_path / "command.py")


def test_to_kebab_case_normalises_separators_and_edges() -> None:
    assert _utils.to_kebab_case("Demo_App.Name") == "demo-app-name"
    assert _utils.to_kebab_case("--Demo  App--") == "demo-app"


def test_normalise_name_delegates_to_kebab_case() -> None:
    assert _utils.normalise_name("Demo_App.Name") == _utils.to_kebab_case("Demo_App.Name")


def test_sha256_checksum_hashes_file_contents(tmp_path: Path) -> None:
    """Calculate the standard SHA-256 digest for a file."""
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"release artifact")

    assert (
        _utils.sha256_checksum(artifact)
        == "133cfccb5b503cf4040c95f3dfad56d07c1574283a1e39066b594f6ee33711ba"
    )
