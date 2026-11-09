"""Tests for Docker Compose project management."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _apps,
    _config,
)
from repo_tooling.make_scripts import (
    make_docker_compose,
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


def create_compose_project(repo_root: Path, name: str) -> Path:
    compose_file = repo_root / "docker-compose-scripts" / name / "docker-compose.yml"
    compose_file.parent.mkdir(parents=True)
    compose_file.write_text("services: {}\n")
    return compose_file


def tooling_module(repo_root: Path) -> Path:
    return repo_root / ".repo_tooling" / "repo_tooling" / "make_scripts" / "make_docker_compose.py"


def test_invalid_action_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        make_docker_compose.main(
            [],
            "compose",
            Path("/repo/.repo_tooling/repo_tooling/make_scripts/make_docker_compose.py"),
        )
        == 2
    )
    assert capsys.readouterr().err == "Usage: compose {up|down|example}\n"


@pytest.mark.parametrize("action", ["up", "down"])
def test_missing_docker_returns_127(
    action: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: None)

    assert make_docker_compose.main([action], "compose", tooling_module(tmp_path)) == 127
    assert "docker is required" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["up", "down"])
def test_unavailable_compose_returns_127(
    action: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", CommandRecorder(return_codes=[1]))

    assert make_docker_compose.main([action], "compose", tooling_module(tmp_path)) == 127
    assert "Docker Compose is required" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["up", "down"])
def test_no_compose_projects_returns_1(
    action: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", CommandRecorder())

    assert make_docker_compose.main([action], "compose", tooling_module(tmp_path)) == 1
    assert make_docker_compose.NO_PROJECTS == capsys.readouterr().err


@pytest.mark.parametrize("action", ["up", "down"])
def test_missing_build_environment_returns_1(
    action: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    create_compose_project(tmp_path, "demo")
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", CommandRecorder())

    assert make_docker_compose.main([action], "compose", tooling_module(tmp_path)) == 1
    assert "build.env" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("action", "suffix"),
    [
        ("up", ["up", "--build"]),
        ("down", ["down"]),
    ],
)
def test_selected_compose_project_runs_expected_command(
    action: str,
    suffix: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose_file = create_compose_project(tmp_path, "demo")
    env_file = tmp_path / "build.env"
    env_file.write_text("")
    recorder = CommandRecorder()
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "1")

    assert make_docker_compose.main([action], "compose", tooling_module(tmp_path)) == 0
    assert recorder.calls[-1] == (
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            *suffix,
        ],
        None,
    )


def test_all_compose_projects_start_detached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose_files = [create_compose_project(tmp_path, name) for name in ("alpha", "beta")]
    env_file = tmp_path / "build.env"
    env_file.write_text("")
    recorder = CommandRecorder()
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "a")

    assert make_docker_compose.main(["up"], "compose", tooling_module(tmp_path)) == 0
    assert [call[0] for call in recorder.calls[1:]] == [
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "up",
            "--build",
            "--detach",
        ]
        for compose_file in compose_files
    ]


@pytest.mark.parametrize("action", ["up", "down"])
def test_quit_does_not_run_a_project(
    action: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_compose_project(tmp_path, "demo")
    (tmp_path / "build.env").write_text("")
    recorder = CommandRecorder()
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "q")

    assert make_docker_compose.main([action], "compose", tooling_module(tmp_path)) == 0
    assert len(recorder.calls) == 1


def test_invalid_selection_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    compose_file = create_compose_project(tmp_path, "demo")
    env_file = tmp_path / "build.env"
    env_file.write_text("")
    selections = iter(["invalid", "1"])
    recorder = CommandRecorder()
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: next(selections))

    assert make_docker_compose.main(["down"], "compose", tooling_module(tmp_path)) == 0
    assert "Invalid selection: invalid" in capsys.readouterr().err
    assert recorder.calls[-1][0] == [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "down",
    ]


def test_example_builds_expected_copier_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "apps" / "Demo_App"
    application.mkdir(parents=True)
    (application / "Dockerfile").write_text("")
    (application / "pyproject.toml").write_text("")
    recorder = CommandRecorder()
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setenv("VCS_REF", "legacy-ref")
    monkeypatch.setenv("VCS_REF_REPO_TEMPLATE", "repo-ref")
    monkeypatch.setenv("VCS_REF_LIB_TEMPLATE", "lib-ref")
    monkeypatch.setenv("VCS_REF_APP_TEMPLATE", "app-ref")
    monkeypatch.setenv("VCS_REF_COMPOSE_TEMPLATE", "v1.2.3")

    assert make_docker_compose.main(["example"], "compose", tooling_module(tmp_path)) == 0
    destination = tmp_path / "docker-compose-scripts" / "Demo_App_example"
    assert recorder.calls == [
        (
            [
                "uv",
                "tool",
                "run",
                "copier",
                "copy",
                "--vcs-ref",
                "v1.2.3",
                "--data",
                "app_name=Demo_App",
                "--data",
                "app_language=python",
                "--data",
                "build_context=../..",
                "--data",
                "dockerfile=apps/Demo_App/Dockerfile",
                "--data",
                "image_name=demo-app:local",
                "--data",
                "service_name=demo-app",
                _config.COPIER_DOCKER_COMPOSE_TEMPLATE_URL,
                str(destination),
            ],
            None,
        )
    ]


def test_example_rejects_existing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    application = tmp_path / "apps" / "demo"
    application.mkdir(parents=True)
    (application / "Dockerfile").write_text("")
    (application / "Cargo.toml").write_text("")
    destination = tmp_path / "docker-compose-scripts" / "demo_example"
    destination.mkdir(parents=True)
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr("builtins.input", lambda _: "1")

    assert make_docker_compose.main(["example"], "compose", tooling_module(tmp_path)) == 1
    assert str(destination) in capsys.readouterr().err


def test_example_reports_when_no_docker_apps_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/uv")

    assert make_docker_compose.main(["example"], "compose", tooling_module(tmp_path)) == 1
    assert capsys.readouterr().err == make_docker_compose.NO_APPLICATIONS


def test_example_skips_unrecognised_docker_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    application = tmp_path / "apps" / "container"
    application.mkdir(parents=True)
    (application / "Dockerfile").write_text("")
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/usr/bin/uv")

    assert make_docker_compose.main(["example"], "compose", tooling_module(tmp_path)) == 1
    assert capsys.readouterr().err == (
        "Skipping application without a recognised language: container\n"
        + make_docker_compose.NO_APPLICATIONS
    )


def test_all_compose_projects_stop_without_detach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects = [create_compose_project(tmp_path, name) for name in ("alpha", "beta")]
    (tmp_path / "build.env").write_text("")
    recorder = CommandRecorder()
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", recorder)
    monkeypatch.setattr("builtins.input", lambda _: "a")

    assert make_docker_compose.main(["down"], script_path=tooling_module(tmp_path)) == 0
    assert [command[-3:] for command, _ in recorder.calls[1:]] == [
        ["-f", str(project), "down"] for project in projects
    ]


@pytest.mark.parametrize("action", ["up", "down"])
def test_unreadable_build_environment_prevents_compose_action(
    action: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create_compose_project(tmp_path, "demo")
    (tmp_path / "build.env").write_text("")
    recorder = CommandRecorder()
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", recorder)
    monkeypatch.setattr(make_docker_compose.os, "access", lambda *_: False)

    assert make_docker_compose.main([action], script_path=tooling_module(tmp_path)) == 1
    assert "missing or unreadable" in capsys.readouterr().err
    assert recorder.calls == [(["docker", "compose", "version"], None)]


@pytest.mark.parametrize("action", ["up", "down"])
@pytest.mark.parametrize(
    ("error", "status"),
    [(OSError("permission denied"), 1), (subprocess.CalledProcessError(31, ["docker"]), 31)],
)
def test_compose_failure_stops_processing_remaining_projects(
    action: str,
    error: Exception,
    status: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unsuccessful action must not continue to later projects in an all-project selection."""
    create_compose_project(tmp_path, "alpha")
    create_compose_project(tmp_path, "beta")
    (tmp_path / "build.env").write_text("")
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/docker")
    monkeypatch.setattr(make_docker_compose.subprocess, "run", CommandRecorder())
    monkeypatch.setattr("builtins.input", lambda _: "a")
    run = Mock(side_effect=error)
    monkeypatch.setattr(make_docker_compose._docker, "run_compose", run)

    assert make_docker_compose.main([action], script_path=tooling_module(tmp_path)) == status
    assert run.call_count == 1


def test_example_requires_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: None)

    assert make_docker_compose.main(["example"], script_path=tooling_module(tmp_path)) == 127
    assert capsys.readouterr().err == make_docker_compose.UV_NOT_FOUND


def test_example_quit_does_not_generate_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr(
        _apps,
        "docker_applications",
        lambda _: [
            _apps.DockerApplication("demo", tmp_path / "apps" / "demo" / "Dockerfile", "python")
        ],
    )
    monkeypatch.setattr("builtins.input", lambda _: "q")

    assert make_docker_compose.main(["example"], script_path=tooling_module(tmp_path)) == 0
    assert not (tmp_path / "docker-compose-scripts").exists()


@pytest.mark.parametrize("broken_symlink", [False, True])
def test_example_rejects_symlink_destination(
    broken_symlink: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A dangling link still reserves the destination and must not be overwritten by Copier."""
    target = tmp_path / "target"
    if not broken_symlink:
        target.mkdir()
    destination = tmp_path / "docker-compose-scripts" / "demo_example"
    destination.parent.mkdir()
    destination.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr(
        _apps,
        "docker_applications",
        lambda _: [
            _apps.DockerApplication("demo", tmp_path / "apps" / "demo" / "Dockerfile", "python")
        ],
    )
    monkeypatch.setattr("builtins.input", lambda _: "1")

    assert make_docker_compose.main(["example"], script_path=tooling_module(tmp_path)) == 1
    assert str(destination) in capsys.readouterr().err
    assert destination.is_symlink()


@pytest.mark.parametrize(
    ("error", "status"),
    [(OSError("missing copier"), 1), (subprocess.CalledProcessError(37, ["copier"]), 37)],
)
def test_example_propagates_copier_failure_status(
    error: Exception, status: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr(
        _apps,
        "docker_applications",
        lambda _: [
            _apps.DockerApplication("demo", tmp_path / "apps" / "demo" / "Dockerfile", "python")
        ],
    )
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setenv("VCS_REF", "legacy-ref")
    monkeypatch.setenv("VCS_REF_APP_TEMPLATE", "app-ref")
    monkeypatch.delenv("VCS_REF_COMPOSE_TEMPLATE", raising=False)
    run = Mock(side_effect=error)
    monkeypatch.setattr(make_docker_compose.subprocess, "run", run)

    assert make_docker_compose.main(["example"], script_path=tooling_module(tmp_path)) == status
    assert "--vcs-ref" not in run.call_args.args[0]
