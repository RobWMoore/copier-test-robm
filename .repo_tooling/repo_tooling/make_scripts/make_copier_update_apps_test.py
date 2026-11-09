"""Tests for the application Copier update entry point."""

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
    make_copier_update_apps,
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


@pytest.mark.parametrize("has_components", [False, True])
def test_component_update_passes_revision_to_each_component(
    has_components: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    update_environment: dict[str, Mock],
) -> None:
    """Each component receives the same revision; an empty discovery reports a no-op."""
    components = [tmp_path / "apps" / name for name in ("alpha", "beta")] if has_components else []
    discover = Mock(return_value=components)
    update = Mock()
    monkeypatch.setattr(_copier, "component_directories", discover)
    monkeypatch.setattr(_copier, "update_application", update)

    assert make_copier_update_apps.main() == 0
    discover.assert_called_once_with(tmp_path, "apps")
    update_environment["conflicts"].assert_called_once_with(
        tmp_path, "before starting", "make copier-update-apps VCS_REF_APP_TEMPLATE=v2"
    )
    expected_calls = []
    for component in components:
        arguments: list[object] = [component, tmp_path]
        arguments.append("v2")
        expected_calls.append(tuple(arguments))
    assert [call.args for call in update.call_args_list] == expected_calls
    assert ("No generated" in capsys.readouterr().out) == (not has_components)


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

    assert make_copier_update_apps.main() == status
    assert ("update failed:" in capsys.readouterr().err) == reports_error
    update_environment["run"].assert_not_called()
