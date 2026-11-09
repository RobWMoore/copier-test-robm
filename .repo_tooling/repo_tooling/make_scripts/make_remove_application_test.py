"""Tests for the application removal entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _apps,
    _utils,
)
from repo_tooling.make_scripts import (
    make_remove_application,
)


def test_remove_application_handles_eof_without_removing_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Leave applications intact when selection ends at end-of-file."""
    application = tmp_path / "apps" / "demo"
    application.mkdir(parents=True)
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError))

    assert make_remove_application.main([], "remove-application") == 0
    assert application.is_dir()
    assert capsys.readouterr().err == "Error: no application was selected.\n"


def test_remove_application_rejects_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert make_remove_application.main(["unexpected"], "remove-application") == 2
    assert capsys.readouterr().err == "Usage: remove-application\n"


def test_remove_application_dispatches_selection_and_returns_its_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "apps" / "demo"
    application.mkdir(parents=True)
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr("sys.argv", ["remove-application"])
    remove = Mock(return_value=17)
    monkeypatch.setattr(_apps, "remove_application", remove)

    assert make_remove_application.main() == 17
    assert remove.call_args.args[0] == tmp_path
    assert remove.call_args.args[1] == application
