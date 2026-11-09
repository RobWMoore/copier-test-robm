"""Tests for Docker Compose deployment release bundles."""

from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _apps,
)
from repo_tooling.make_scripts import (
    make_build_release_docker_compose,
)


class CommandRecorder:
    def __init__(self, images: str = "registry/demo:latest\n") -> None:
        self.calls: list[list[str]] = []
        self.images = images

    def __call__(
        self, command: list[str], *, check: bool = False, **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if command[:3] == ["docker", "compose", "--env-file"] and command[-2:] == [
            "config",
            "--images",
        ]:
            return subprocess.CompletedProcess(command, 0, stdout=self.images)
        if command[:2] == ["docker", "save"]:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("image archive")
        return subprocess.CompletedProcess(command, 0, stdout="")


def create_release_project(repo_root: Path) -> Path:
    project = repo_root / "docker-compose-scripts" / "production"
    project.mkdir(parents=True)
    (project / "docker-compose.yml").write_text("services: {}\n")
    (project / "runtime.env").write_text("MODE=production\n")
    (repo_root / "build.env").write_text("IMAGE=demo\n")
    (repo_root / "release.env").write_text(
        'RELEASE_COMPOSE_PROJECT="docker-compose-scripts/production"\n'
    )
    return project


def tooling_module(repo_root: Path) -> Path:
    return (
        repo_root
        / ".repo_tooling"
        / "repo_tooling"
        / "make_scripts"
        / "make_build_release_docker_compose.py"
    )


def configure_docker(monkeypatch: pytest.MonkeyPatch, recorder: CommandRecorder) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(make_build_release_docker_compose.subprocess, "run", recorder)


def test_invalid_arguments_print_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        make_build_release_docker_compose.main(
            [],
            "release",
            Path(
                "/repo/.repo_tooling/repo_tooling/make_scripts/make_build_release_docker_compose.py"
            ),
        )
        == 2
    )
    assert capsys.readouterr().err == "Usage: release <release-tag>\n"


def test_missing_docker_returns_127(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: None)

    assert (
        make_build_release_docker_compose.main(["v1.0.0"], "release", tooling_module(tmp_path))
        == 127
    )
    assert "docker is required" in capsys.readouterr().err


def test_unusable_docker_returns_127(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        make_build_release_docker_compose.subprocess,
        "run",
        lambda command, **_: (_ for _ in ()).throw(subprocess.CalledProcessError(1, command)),
    )

    assert (
        make_build_release_docker_compose.main(["v1.0.0"], "release", tooling_module(tmp_path))
        == 127
    )
    assert "Docker is unavailable" in capsys.readouterr().err


def test_missing_release_configuration_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = CommandRecorder()
    configure_docker(monkeypatch, recorder)

    assert (
        make_build_release_docker_compose.main(["v1.0.0"], "release", tooling_module(tmp_path)) == 1
    )
    assert "Missing release configuration" in capsys.readouterr().err


def test_missing_compose_project_value_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "release.env").write_text("RELEASE_COMPOSE_PROJECT=\n")
    recorder = CommandRecorder()
    configure_docker(monkeypatch, recorder)

    assert (
        make_build_release_docker_compose.main(["v1.0.0"], "release", tooling_module(tmp_path)) == 1
    )
    assert "Set RELEASE_COMPOSE_PROJECT" in capsys.readouterr().err


def test_missing_compose_file_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "release.env").write_text(
        'RELEASE_COMPOSE_PROJECT="docker-compose-scripts/production"\n'
    )
    (tmp_path / "docker-compose-scripts" / "production").mkdir(parents=True)
    recorder = CommandRecorder()
    configure_docker(monkeypatch, recorder)

    assert (
        make_build_release_docker_compose.main(["v1.0.0"], "release", tooling_module(tmp_path)) == 1
    )
    assert "has no docker-compose.yml" in capsys.readouterr().err


def test_empty_image_list_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    create_release_project(tmp_path)
    recorder = CommandRecorder(images="")
    configure_docker(monkeypatch, recorder)

    assert (
        make_build_release_docker_compose.main(["v1.0.0"], "release", tooling_module(tmp_path)) == 1
    )
    assert "does not reference any images" in capsys.readouterr().err


def test_builds_and_verifies_release_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = create_release_project(tmp_path)
    recorder = CommandRecorder(images="registry/demo:latest\nsecond/image:2\n")
    configure_docker(monkeypatch, recorder)
    monkeypatch.setenv("CI_COMMIT_SHA", "abc123")

    assert (
        make_build_release_docker_compose.main(["v1.0.0"], "release", tooling_module(tmp_path)) == 0
    )

    output_root = tmp_path / "dist" / "release"
    bundle = output_root / "docker-compose-v1.0.0"
    archive = output_root / "docker-compose-v1.0.0.tar.gz"
    assert archive.is_file()
    assert (bundle / "compose" / "runtime.env").read_text() == "MODE=production\n"
    assert json.loads((bundle / "manifest.json").read_text()) == {
        "version": "v1.0.0",
        "commit_sha": "abc123",
        "images": [
            {
                "image": "registry/demo:latest",
                "archive": "images/registry_demo_latest.tar",
            },
            {"image": "second/image:2", "archive": "images/second_image_2.tar"},
        ],
    }
    with tarfile.open(archive) as tar:
        assert f"{bundle.name}/manifest.json" in tar.getnames()

    compose_prefix = [
        "docker",
        "compose",
        "--env-file",
        str(tmp_path / "build.env"),
        "--project-directory",
        str(project),
        "-f",
        str(project / "docker-compose.yml"),
    ]
    assert recorder.calls[:5] == [
        ["docker", "version"],
        [*compose_prefix, "config"],
        [*compose_prefix, "build"],
        [*compose_prefix, "pull", "--ignore-buildable"],
        [*compose_prefix, "config", "--images"],
    ]
    assert ["docker", "image", "inspect", "registry/demo:latest"] in recorder.calls
    assert any(command[:3] == ["docker", "load", "-i"] for command in recorder.calls)
    assert sum(command[-1:] == ["config"] for command in recorder.calls) == 2


def test_rejects_release_tag_with_path_separator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = CommandRecorder()
    configure_docker(monkeypatch, recorder)

    assert (
        make_build_release_docker_compose.main(["../unsafe"], "release", tooling_module(tmp_path))
        == 1
    )
    assert "must not contain a path separator" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (OSError("unreadable archive"), 1),
        (tarfile.TarError("corrupt archive"), 1),
        (subprocess.CalledProcessError(41, ["docker"]), 41),
    ],
)
def test_bundle_failure_reports_diagnostic_and_preserves_tool_exit_status(
    error: Exception,
    status: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_apps, "docker_available", lambda: True)
    monkeypatch.setattr(make_build_release_docker_compose._utils, "repo_root", lambda _: tmp_path)
    bundle = Mock(side_effect=error)
    monkeypatch.setattr(
        make_build_release_docker_compose._release, "bundle_docker_compose_release", bundle
    )
    monkeypatch.setattr("sys.argv", ["release-compose", "v1.0.0"])

    assert make_build_release_docker_compose.main() == status
    bundle.assert_called_once_with("v1.0.0", tmp_path)
    assert "Release failed:" in capsys.readouterr().err
