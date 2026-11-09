"""Tests for interactive Docker application builds and runs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _apps,
    _config,
    _docker,
)
from repo_tooling.make_scripts import (
    make_docker_app,
)


class CommandRecorder:
    def __init__(self, return_codes: list[int] | None = None) -> None:
        self.calls: list[tuple[list[str], Path | None]] = []
        self.return_codes = iter(return_codes or [])

    def __call__(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        check: bool = False,
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, cwd))
        return_code = next(self.return_codes, 0)
        if check and return_code:
            raise subprocess.CalledProcessError(return_code, command)
        return subprocess.CompletedProcess(command, return_code)


def create_docker_application(repo_root: Path, name: str, language: str = "python") -> Path:
    application = repo_root / "apps" / name
    application.mkdir(parents=True)
    (application / "Dockerfile").write_text("")
    manifest = "pyproject.toml" if language == "python" else "Cargo.toml"
    (application / manifest).write_text("")
    return application


def tooling_module(repo_root: Path) -> Path:
    return repo_root / ".repo_tooling" / "repo_tooling" / "make_scripts" / "make_docker_app.py"


def test_invalid_action_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        make_docker_app.main(
            [],
            "docker-app",
            Path("/repo/.repo_tooling/repo_tooling/make_scripts/make_docker_app.py"),
        )
        == 2
    )
    assert capsys.readouterr().err == "Usage: docker-app {build|run}\n"


def test_missing_docker_returns_127(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: None)

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 127
    assert "docker is required" in capsys.readouterr().err


def test_unusable_docker_returns_127(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", CommandRecorder(return_codes=[1]))

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 127
    assert "Docker is unavailable" in capsys.readouterr().err


def test_no_docker_applications_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", CommandRecorder())

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 1
    assert _docker.NO_APPLICATIONS == capsys.readouterr().err


@pytest.mark.parametrize("action", ["build", "run"])
def test_apps_missing_dockerfile_or_manifest_are_not_selectable(
    action: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dockerfile_only = tmp_path / "apps" / "service"
    dockerfile_only.mkdir(parents=True)
    (dockerfile_only / "Dockerfile").write_text("")
    manifest_only = tmp_path / "apps" / "local"
    manifest_only.mkdir()
    (manifest_only / "pyproject.toml").write_text("")
    recorder = CommandRecorder()
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("unexpected prompt")))

    assert make_docker_app.main([action], "docker-app", tooling_module(tmp_path)) == 1
    assert capsys.readouterr().err == _docker.NO_APPLICATIONS
    assert recorder.calls == [(["docker", "version"], None)]


def test_quitting_selection_returns_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_docker_application(tmp_path, "demo")
    recorder = CommandRecorder()
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "q")

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 0
    assert recorder.calls == [(["docker", "version"], None)]


def test_invalid_selection_reprompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    create_docker_application(tmp_path, "demo")
    recorder = CommandRecorder()
    selections = iter(["0", "q"])
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: next(selections))

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 0
    assert "Invalid selection: 0" in capsys.readouterr().err
    assert recorder.calls == [(["docker", "version"], None)]


def test_build_runs_expected_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = create_docker_application(tmp_path, "Demo_App")
    recorder = CommandRecorder()
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr(
        _docker,
        "build_argument_environment_variables",
        lambda: (("PYTHON_IMAGE", "PYTHON_IMAGE"), ("UV_VERSION", "UV_VERSION")),
    )
    monkeypatch.setenv("PYTHON_IMAGE", "python:3.14-slim")
    monkeypatch.setenv("UV_VERSION", "0.11.28")

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 0
    assert recorder.calls == [
        (["docker", "version"], None),
        (
            [
                "docker",
                "build",
                "--build-arg",
                "PYTHON_IMAGE=python:3.14-slim",
                "--build-arg",
                "UV_VERSION=0.11.28",
                "-f",
                str(application / "Dockerfile"),
                "-t",
                "Demo_App:local",
                str(tmp_path),
            ],
            None,
        ),
    ]


@pytest.mark.parametrize("action", ["build", "run"])
def test_rust_app_is_selectable_after_manifestless_app(
    action: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = tmp_path / "apps" / "alpha_service"
    service.mkdir(parents=True)
    (service / "Dockerfile").write_text("")
    application = create_docker_application(tmp_path, "bravo", "rust")
    recorder = CommandRecorder()
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", recorder)
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python", "rust"))
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr(_docker, "build_argument_environment_variables", lambda: ())

    assert make_docker_app.main([action], "docker-app", tooling_module(tmp_path)) == 0
    assert "1) bravo" in capsys.readouterr().out
    assert recorder.calls[1][0] == [
        "docker",
        "build",
        "-f",
        str(application / "Dockerfile"),
        "-t",
        "bravo:local",
        str(tmp_path),
    ]
    if action == "run":
        assert recorder.calls[2][0] == [
            "docker", "run", "--rm", "--name", "bravo", "bravo:local"
        ]


def test_run_builds_then_starts_removable_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = create_docker_application(tmp_path, "demo")
    recorder = CommandRecorder()
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr(_docker, "build_argument_environment_variables", lambda: ())

    assert make_docker_app.main(["run"], "docker-app", tooling_module(tmp_path)) == 0
    assert recorder.calls == [
        (["docker", "version"], None),
        (
            [
                "docker",
                "build",
                "-f",
                str(application / "Dockerfile"),
                "-t",
                "demo:local",
                str(tmp_path),
            ],
            None,
        ),
        (["docker", "run", "--rm", "--name", "demo", "demo:local"], None),
    ]


def test_missing_build_variable_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    create_docker_application(tmp_path, "demo")
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", CommandRecorder())
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr(
        _docker,
        "build_argument_environment_variables",
        lambda: (("PYTHON_IMAGE", "PYTHON_IMAGE"),),
    )
    monkeypatch.delenv("PYTHON_IMAGE", raising=False)

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 1
    assert "PYTHON_IMAGE must be set" in capsys.readouterr().err


def test_docker_failure_returns_its_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_docker_application(tmp_path, "demo")
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", CommandRecorder(return_codes=[0, 42]))
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr(_docker, "build_argument_environment_variables", lambda: ())

    assert make_docker_app.main(["build"], "docker-app", tooling_module(tmp_path)) == 42


@pytest.mark.parametrize(
    ("error", "status"),
    [(OSError("docker disappeared"), 1), (subprocess.CalledProcessError(43, ["docker"]), 43)],
)
def test_failed_build_does_not_launch_container(
    error: Exception, status: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_docker_application(tmp_path, "demo")
    monkeypatch.setattr(_apps, "docker_available", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr(_docker, "build_arguments", lambda: [])
    monkeypatch.setattr(make_docker_app._utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("sys.argv", ["docker-app", "run"])
    run = Mock(side_effect=error)
    monkeypatch.setattr(make_docker_app.subprocess, "run", run)

    assert make_docker_app.main() == status
    run.assert_called_once()
    assert run.call_args.args[0][:2] == ["docker", "build"]
