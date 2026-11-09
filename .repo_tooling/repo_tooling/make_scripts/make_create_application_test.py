"""Tests for the application creation entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _apps,
    _utils,
)
from repo_tooling.make_scripts import (
    make_create_application,
)


def test_create_application_rejects_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reject command-line arguments before prompting for an application kind."""
    monkeypatch.setattr(make_create_application._apps.shutil, "which", lambda _: "/uv")
    assert make_create_application.main(["unexpected"], "create-application") == 2
    assert capsys.readouterr().err == "Usage: create-application\n"


def test_create_application_requires_uv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: None)
    choose = Mock()
    monkeypatch.setattr(_apps, "choose_app_kind", choose)

    assert make_create_application.main([]) == 127
    assert _apps.UV_NOT_FOUND in capsys.readouterr().err
    choose.assert_not_called()


@pytest.mark.parametrize("kind", ["local-app", "service-app"])
def test_create_application_dispatches_selected_kind_and_returns_its_status(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(_apps, "choose_app_kind", lambda: kind)
    create = Mock(return_value=23)
    monkeypatch.setattr(_apps, "create_local_app", create)
    monkeypatch.setattr(_apps, "create_service_app", create)
    monkeypatch.setattr("sys.argv", ["create-application"])

    assert make_create_application.main() == 23
    create.assert_called_once_with(tmp_path)


def test_create_application_quit_does_not_create_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr(_apps, "choose_app_kind", lambda: None)
    create = Mock()
    monkeypatch.setattr(_apps, "create_local_app", create)
    monkeypatch.setattr(_apps, "create_service_app", create)

    assert make_create_application.main([]) == 0
    create.assert_not_called()


def test_create_application_reports_unsupported_kind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr(_apps, "choose_app_kind", lambda: "unsupported")

    assert make_create_application.main([]) == 2
    assert "unsupported app kind: unsupported" in capsys.readouterr().err
