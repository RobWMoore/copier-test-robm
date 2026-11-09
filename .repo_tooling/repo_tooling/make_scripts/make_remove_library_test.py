"""Tests for the generic library-removal entry point."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _libs,
    _pyproject,
)
from repo_tooling.make_scripts import (
    make_remove_library,
)


def tooling_module(repo_root: Path) -> Path:
    """Return a module path that resolves to repo_root."""
    return repo_root / ".repo_tooling" / "repo_tooling" / "make_scripts" / "make_remove_library.py"


def test_remove_python_library_inlines_language_specific_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove a Python library without launching another tooling module."""
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    (library / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    calls: list[tuple[list[str], Path | None]] = []
    removals: list[tuple[Path, str, str]] = []
    monkeypatch.setattr(_libs, "choose_library", lambda _: library)
    monkeypatch.setattr(_pyproject, "project_name", lambda _: "demo")
    monkeypatch.setattr(_pyproject, "dependants", lambda *_: [])
    monkeypatch.setattr(
        _pyproject,
        "remove_from_root_project",
        lambda root, path, name: removals.append((root, path, name)),
    )
    monkeypatch.setattr(
        make_remove_library.subprocess,
        "run",
        lambda command, *, cwd, check: calls.append((command, cwd)),
    )

    assert make_remove_library.main([], script_path=tooling_module(tmp_path)) == 0
    assert not library.exists()
    assert removals == [(tmp_path, "libs/demo", "demo")]
    assert calls == [(["uv", "lock"], tmp_path)]


def test_removal_rejects_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert make_remove_library.main(["extra"], "remove-library") == 2
    assert capsys.readouterr().err == "Usage: remove-library\n"


def test_removal_reports_no_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_remove_library._utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("sys.argv", ["remove-library"])

    assert make_remove_library.main() == 1
    assert "No Python or Rust libraries found" in capsys.readouterr().err


def test_removal_quit_preserves_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    monkeypatch.setattr(_libs, "libraries", lambda *_: [library])
    monkeypatch.setattr(_libs, "choose_library", lambda _: None)

    assert make_remove_library.main([], script_path=tooling_module(tmp_path)) == 0
    assert library.is_dir()


@pytest.fixture(params=_libs.configs(), ids=lambda config: config.language)
def selected_library(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, _libs.LibraryConfig, Mock, Mock]:
    config = request.param
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    (library / config.manifest_name).write_text("")
    monkeypatch.setattr(_libs, "choose_library", lambda _: library)
    if config.language == "python":
        manager: ModuleType = _pyproject
        name_function = "project_name"
        remove_function = "remove_from_root_project"
    else:
        manager = make_remove_library._cargo
        name_function = "package_name"
        remove_function = "remove_workspace_member"
    monkeypatch.setattr(manager, name_function, lambda _: "demo")
    monkeypatch.setattr(manager, "dependants", lambda *_: [])
    remove = Mock()
    monkeypatch.setattr(manager, remove_function, remove)
    run = Mock()
    monkeypatch.setattr(make_remove_library.subprocess, "run", run)
    return library, config, run, remove


def test_removal_refuses_libraries_with_dependants(
    selected_library: tuple[Path, _libs.LibraryConfig, Mock, Mock],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dependency checks must prevent both manifest mutation and directory deletion."""
    library, config, run, remove = selected_library
    manager = _pyproject if config.language == "python" else make_remove_library._cargo
    monkeypatch.setattr(manager, "dependants", lambda *_: [Path("apps/consumer")])

    assert make_remove_library.main([], script_path=tooling_module(tmp_path)) == 1
    assert "required by: apps/consumer" in capsys.readouterr().err
    assert library.is_dir()
    run.assert_not_called()
    remove.assert_not_called()


@pytest.mark.parametrize(
    ("error", "status"),
    [(OSError("permission denied"), 1), (subprocess.CalledProcessError(29, ["lock"]), 29)],
)
def test_lockfile_failure_preserves_library_directory(
    error: Exception,
    status: int,
    selected_library: tuple[Path, _libs.LibraryConfig, Mock, Mock],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library, _, run, _ = selected_library
    (tmp_path / "Cargo.lock").write_text("")
    run.side_effect = error

    assert make_remove_library.main([], script_path=tooling_module(tmp_path)) == status
    assert "Library removal failed:" in capsys.readouterr().err
    assert library.is_dir()


def test_rust_removal_refreshes_existing_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    (library / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')
    (tmp_path / "Cargo.lock").write_text("")
    monkeypatch.setattr(_libs, "choose_library", lambda _: library)
    monkeypatch.setattr(make_remove_library._cargo, "dependants", lambda *_: [])
    monkeypatch.setattr(make_remove_library._cargo, "remove_workspace_member", Mock())
    run = Mock()
    monkeypatch.setattr(make_remove_library.subprocess, "run", run)

    assert make_remove_library.main([], script_path=tooling_module(tmp_path)) == 0
    run.assert_called_once_with(["cargo", "generate-lockfile"], cwd=tmp_path, check=True)
    assert not library.exists()


def test_remove_rust_library_inlines_language_specific_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove a Rust library without launching another tooling module."""
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    (library / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')
    removals: list[tuple[Path, str]] = []
    monkeypatch.setattr(_libs, "choose_library", lambda _: library)
    monkeypatch.setattr(make_remove_library._cargo, "package_name", lambda _: "demo")
    monkeypatch.setattr(make_remove_library._cargo, "dependants", lambda *_: [])
    monkeypatch.setattr(
        make_remove_library._cargo,
        "remove_workspace_member",
        lambda root, path: removals.append((root, path)),
    )

    assert make_remove_library.main([], script_path=tooling_module(tmp_path)) == 0
    assert not library.exists()
    assert removals == [(tmp_path, "libs/demo")]
