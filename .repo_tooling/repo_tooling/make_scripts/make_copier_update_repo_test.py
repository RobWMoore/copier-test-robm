"""Tests for the repository Copier update entry point."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _copier,
    _utils,
)
from repo_tooling.make_scripts import (
    make_copier_update_repo,
)


@pytest.fixture
def update_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("sys.argv", ["update", "--vcs-ref", "v2"])
    mocks = {
        "answers": Mock(return_value={"project_name": "demo"}),
        "conflicts": Mock(),
        "run": Mock(),
        "validate": Mock(),
    }
    monkeypatch.setattr(_copier, "require_root_answers", mocks["answers"])
    monkeypatch.setattr(_copier, "abort_if_merge_conflicts", mocks["conflicts"])
    monkeypatch.setattr(_copier, "run_update", mocks["run"])
    monkeypatch.setattr(_copier, "validate_components", mocks["validate"])
    return mocks


@pytest.mark.parametrize("vcs_ref", [None, "v2"])
def test_repository_update_builds_copier_command(
    vcs_ref: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    update_environment: dict[str, Mock],
) -> None:
    monkeypatch.setattr("sys.argv", ["update", *(["--vcs-ref", vcs_ref] if vcs_ref else [])])

    assert make_copier_update_repo.main() == 0
    update_environment["run"].assert_called_once_with(
        [
            "uv",
            "tool",
            "run",
            "copier",
            "update",
            *(["--vcs-ref", vcs_ref] if vcs_ref else []),
            str(tmp_path),
        ],
        tmp_path,
        "for the repository",
        "make copier-update-repo" + (f" VCS_REF_REPO_TEMPLATE={vcs_ref}" if vcs_ref else ""),
    )


@pytest.mark.parametrize(
    ("error", "status", "reports_error"),
    [
        (OSError("unreadable answers"), 1, True),
        (ValueError("invalid answers"), 1, True),
        (RuntimeError("conflict already reported"), 1, False),
        (subprocess.CalledProcessError(17, ["copier"]), 17, True),
    ],
)
def test_update_errors_preserve_exit_status_without_repeating_conflict_diagnostics(
    error: Exception,
    status: int,
    reports_error: bool,
    capsys: pytest.CaptureFixture[str],
    update_environment: dict[str, Mock],
) -> None:
    """RuntimeError comes from helpers that already print the conflict and recovery command."""
    update_environment["conflicts"].side_effect = error

    assert make_copier_update_repo.main() == status
    assert ("update failed:" in capsys.readouterr().err) == reports_error
    update_environment["run"].assert_not_called()
