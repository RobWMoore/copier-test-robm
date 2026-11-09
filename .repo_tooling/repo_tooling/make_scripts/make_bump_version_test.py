"""Tests for version bump commands and lockfile refreshes."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling.make_scripts import (
    make_bump_version,
)


@pytest.mark.parametrize(
    ("component", "expected"), [("major", "2.0.0"), ("minor", "1.3.0"), ("patch", "1.2.4")]
)
@pytest.mark.parametrize(
    ("python", "rust"), [(False, False), (True, False), (False, True), (True, True)]
)
def test_bump_updates_current_template_revision_and_refreshes_present_lockfiles(
    component: str,
    expected: str,
    python: bool,
    rust: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pinning Copier to :current: avoids an unintended template upgrade during a bump."""
    (tmp_path / "VERSION").write_text("1.2.3\n")
    for present, manifest in [(python, "pyproject.toml"), (rust, "Cargo.toml")]:
        if present:
            (tmp_path / manifest).write_text("")
    monkeypatch.setattr(make_bump_version, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["bump-version", component])
    run = Mock()
    monkeypatch.setattr(make_bump_version.subprocess, "run", run)

    make_bump_version.main()

    expected_commands = [
        [
            "uv",
            "tool",
            "run",
            "copier",
            "update",
            "--defaults",
            "--vcs-ref",
            ":current:",
            "--data",
            f"project_version={expected}",
        ]
    ]
    if python:
        expected_commands.append(["uv", "lock"])
    if rust:
        expected_commands.append(["cargo", "generate-lockfile"])
    assert [call.args[0] for call in run.call_args_list] == expected_commands
    assert all(call.kwargs == {"cwd": tmp_path, "check": True} for call in run.call_args_list)
    output = capsys.readouterr().out
    assert f"1.2.3 -> {expected}" in output
    assert ("Regenerated uv.lock" in output) == python
    assert ("Regenerated Cargo.lock" in output) == rust


def test_failed_template_update_does_not_refresh_lockfiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "VERSION").write_text("1.2.3")
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.setattr(make_bump_version, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["bump-version", "patch"])
    run = Mock(side_effect=subprocess.CalledProcessError(7, ["copier"]))
    monkeypatch.setattr(make_bump_version.subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError):
        make_bump_version.main()
    assert run.call_count == 1


def test_invalid_component_is_rejected_before_reading_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(make_bump_version, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["bump-version", "invalid"])

    with pytest.raises(SystemExit) as error:
        make_bump_version.main()
    assert error.value.code == 2
