"""Tests for Docker and Docker Compose management helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_tooling import _docker


def test_configured_compose_project_reads_a_quoted_value(tmp_path: Path) -> None:
    """Read the configured Compose project path from release.env."""
    release_environment = tmp_path / "release.env"
    release_environment.write_text('RELEASE_COMPOSE_PROJECT="docker-compose-scripts/production"\n')

    assert _docker.configured_compose_project(release_environment) == (
        "docker-compose-scripts/production"
    )


def test_configured_compose_project_rejects_a_missing_value(tmp_path: Path) -> None:
    """Require the Compose release project configuration."""
    release_environment = tmp_path / "release.env"
    release_environment.write_text("OTHER=value\n")

    with pytest.raises(ValueError, match="Set RELEASE_COMPOSE_PROJECT"):
        _docker.configured_compose_project(release_environment)


def test_compose_project_directory_validates_a_repository_project(tmp_path: Path) -> None:
    """Resolve a Compose project only when it is a valid repository child."""
    project = tmp_path / "docker-compose-scripts" / "production"
    project.mkdir(parents=True)
    (project / "docker-compose.yml").write_text("services: {}\n")

    assert (
        _docker.compose_project_directory(tmp_path, "docker-compose-scripts/production")
        == project.resolve()
    )


@pytest.mark.parametrize("project_path", ["", "../outside", "/outside"])
def test_compose_project_directory_rejects_unsafe_paths(tmp_path: Path, project_path: str) -> None:
    """Reject missing and path-traversal Compose project paths."""
    with pytest.raises(ValueError, match="RELEASE_COMPOSE_PROJECT|within the repository"):
        _docker.compose_project_directory(tmp_path, project_path)


@pytest.mark.parametrize("target", ["missing", "file", "repository", "outside-symlink"])
def test_compose_project_directory_rejects_invalid_resolved_targets(
    tmp_path: Path, target: str
) -> None:
    """Check the actual filesystem target as well as the configured relative path."""
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    project_path = "project"
    if target == "file":
        (repo_root / project_path).write_text("not a directory")
    elif target == "repository":
        project_path = "."
    elif target == "outside-symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "docker-compose.yml").write_text("services: {}\n")
        (repo_root / project_path).symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="must be within the repository"):
        _docker.compose_project_directory(repo_root, project_path)


@pytest.mark.parametrize("action", ["up", "down"])
def test_choose_compose_project_handles_eof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError))

    assert (
        _docker.choose_compose_project([tmp_path / "demo" / "docker-compose.yml"], action) is None
    )

    captured = capsys.readouterr()
    assert "1) demo" in captured.out
    assert captured.err == "Error: no Docker Compose project was selected.\n"


def test_compose_command_includes_project_configuration(tmp_path: Path) -> None:
    """Build a Compose command with environment, project, and file arguments."""
    assert _docker.compose_command(
        tmp_path / "build.env",
        tmp_path / "project",
        tmp_path / "project" / "docker-compose.yml",
        "config",
    ) == [
        "docker",
        "compose",
        "--env-file",
        str(tmp_path / "build.env"),
        "--project-directory",
        str(tmp_path / "project"),
        "-f",
        str(tmp_path / "project" / "docker-compose.yml"),
        "config",
    ]


def test_image_archive_name_replaces_image_separators() -> None:
    """Produce a portable archive filename for a Docker image reference."""
    assert _docker.image_archive_name("registry/demo:latest") == "registry_demo_latest.tar"


def test_build_arguments_reads_required_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build Docker arguments from the configured environment values."""
    monkeypatch.setattr(
        _docker,
        "build_argument_environment_variables",
        lambda: (("PYTHON_IMAGE", "PYTHON_IMAGE"),),
    )
    monkeypatch.setenv("PYTHON_IMAGE", "python:3.14-slim")

    assert _docker.build_arguments() == ["--build-arg", "PYTHON_IMAGE=python:3.14-slim"]


def test_compose_projects_discovers_non_symlink_project_files(tmp_path: Path) -> None:
    """Discover Compose files from direct project directories only."""
    compose_root = tmp_path / "docker-compose-scripts"
    project = compose_root / "demo"
    project.mkdir(parents=True)
    compose_file = project / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    linked = compose_root / "linked"
    linked.symlink_to(project)

    assert _docker.compose_projects(compose_root) == [compose_file]


def test_run_compose_builds_the_requested_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run Compose with detached startup when requested."""
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_docker.subprocess, "run", run)

    _docker.run_compose(
        tmp_path / "docker-compose.yml", tmp_path / "build.env", "up", detached=True
    )

    assert calls == [
        [
            "docker",
            "compose",
            "--env-file",
            str(tmp_path / "build.env"),
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "up",
            "--build",
            "--detach",
        ]
    ]
