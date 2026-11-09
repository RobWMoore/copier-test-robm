"""Tests for the interactive library creation command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _config,
    _libs,
    _utils,
)
from repo_tooling.make_scripts import (
    make_create_library,
)


@pytest.fixture
def creation_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setattr(make_create_library.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    run = Mock()
    monkeypatch.setattr(make_create_library.subprocess, "run", run)
    return run


def test_creation_requires_uv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_create_library.shutil, "which", lambda _: None)

    assert make_create_library.main([]) == 127
    assert capsys.readouterr().err == make_create_library.UV_NOT_FOUND


@pytest.mark.parametrize(
    "arguments",
    [
        ["--language"],
        ["--vcs-ref"],
        ["--language="],
        ["--vcs-ref="],
        ["--language", "python", "--language", "rust"],
        ["--vcs-ref", "v1", "--vcs-ref", "v2"],
        ["first", "second"],
    ],
)
def test_malformed_arguments_report_usage_without_running_copier(
    arguments: list[str],
    creation_environment: Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert make_create_library.main(arguments, "create-library") == 2
    assert "Usage: create-library" in capsys.readouterr().err
    creation_environment.assert_not_called()


def test_disabled_language_reports_enabled_options(
    creation_environment: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert make_create_library.main(["demo", "--language=unsupported"]) == 2
    error = capsys.readouterr().err
    assert "language must be one of:" in error
    assert all(config.language in error for config in _libs.configs())
    creation_environment.assert_not_called()


@pytest.mark.parametrize("config", _libs.configs(), ids=lambda config: config.language)
@pytest.mark.parametrize("option_style", ["separate", "equals"])
def test_creation_normalises_name_and_registers_library_in_selected_workspace(
    config: _libs.LibraryConfig,
    option_style: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    creation_environment: Mock,
) -> None:
    """Check the Copier contract and workspace registration without invoking either tool."""
    register = Mock()
    monkeypatch.setattr(make_create_library._cargo, "add_workspace_member", register)
    options = (
        ["--language", config.language, "--vcs-ref", "v2"]
        if option_style == "separate"
        else [f"--language={config.language}", "--vcs-ref=v2"]
    )

    assert make_create_library.main(["Demo Library", *options]) == 0
    destination = tmp_path / "libs" / "demo_library"
    assert destination.parent.is_dir()
    creation_environment.assert_any_call(
        [
            "uv",
            "tool",
            "run",
            "copier",
            "copy",
            "--vcs-ref",
            "v2",
            "--data",
            f"programming_language={config.language}",
            "--data",
            "package_name=demo_library",
            "--data",
            config.version_data,
            _config.COPIER_LIB_TEMPLATE_URL,
            str(destination),
        ],
        check=True,
    )
    if config.language == "python":
        creation_environment.assert_any_call(
            ["uv", "add", "--workspace", "libs/demo_library"], cwd=tmp_path, check=True
        )
        register.assert_not_called()
    else:
        register.assert_called_once_with(tmp_path, "libs/demo_library")
        assert creation_environment.call_count == 1


def test_interactive_creation_uses_default_name_and_no_revision_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, creation_environment: Mock
) -> None:
    config = _libs.configs()[0]
    choose = Mock(return_value=config)
    monkeypatch.setattr(_libs, "choose_config", choose)
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr("sys.argv", ["create-library"])
    monkeypatch.setattr(make_create_library._cargo, "add_workspace_member", Mock())

    assert make_create_library.main() == 0
    choose.assert_called_once_with(_libs.configs())
    command = creation_environment.call_args_list[0].args[0]
    assert "--vcs-ref" not in command
    assert f"package_name={config.default_name}" in command
    assert command[-1] == str(tmp_path / "libs" / config.default_name)


def test_creation_rejects_empty_normalised_name(
    monkeypatch: pytest.MonkeyPatch,
    creation_environment: Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _libs.configs()[0]
    monkeypatch.setattr(_libs, "choose_config", lambda _: config)

    assert make_create_library.main(["!!!"]) == 2
    assert config.empty_name_error in capsys.readouterr().err
    creation_environment.assert_not_called()


def test_creation_preserves_existing_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    creation_environment: Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "libs" / "demo"
    destination.mkdir(parents=True)
    marker = destination / "keep.txt"
    marker.write_text("keep")
    monkeypatch.setattr(_libs, "choose_config", lambda _: _libs.configs()[0])

    assert make_create_library.main(["demo"]) == 1
    assert str(destination) in capsys.readouterr().err
    assert marker.read_text() == "keep"
    creation_environment.assert_not_called()


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (OSError("missing copier"), 1),
        (ValueError("bad workspace"), 1),
        (subprocess.CalledProcessError(19, ["copier"]), 19),
    ],
)
def test_creation_returns_tool_failure_status_without_registering_library(
    error: Exception,
    status: int,
    monkeypatch: pytest.MonkeyPatch,
    creation_environment: Mock,
) -> None:
    monkeypatch.setattr(_libs, "choose_config", lambda _: _libs.configs()[0])
    creation_environment.side_effect = error

    assert make_create_library.main(["demo"]) == status
    assert creation_environment.call_count == 1
