"""Tests for repository release build and verification operations."""

from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import _release


def test_extract_archive_rejects_unsafe_members(tmp_path: Path) -> None:
    """Reject archives whose members would be extracted outside their destination."""
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("../unsafe")
        member.size = 0
        archive.addfile(member)

    with pytest.raises(ValueError, match="Release archive contains an unsafe path"):
        _release.extract_archive(archive_path, tmp_path / "destination")


def test_configured_cli_apps_reads_the_release_environment(tmp_path: Path) -> None:
    """Read configured CLI application paths from release.env."""
    release_environment = tmp_path / "release.env"
    release_environment.write_text('RELEASE_CLI_APPS="apps/alpha apps/bravo"\n')

    assert _release.configured_cli_apps(release_environment) == ["apps/alpha", "apps/bravo"]


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "Missing release configuration"), ("OTHER=value\n", "Set RELEASE_CLI_APPS")],
)
def test_configured_cli_apps_rejects_missing_configuration(
    tmp_path: Path, content: str | None, message: str
) -> None:
    environment = tmp_path / "release.env"
    if content is not None:
        environment.write_text(content)

    with pytest.raises(ValueError, match=message):
        _release.configured_cli_apps(environment)


@pytest.mark.parametrize("target", ["missing", "file", "outside-symlink"])
def test_cli_release_application_directory_rejects_invalid_resolved_targets(
    tmp_path: Path, target: str
) -> None:
    """Reject nonexistent applications and links that resolve outside the repository."""
    repo_root = tmp_path / "repository"
    apps = repo_root / "apps"
    apps.mkdir(parents=True)
    if target == "file":
        (apps / "demo").write_text("not an application directory")
    elif target == "outside-symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        (apps / "demo").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="CLI release target must be below apps/"):
        _release.cli_release_application_directory(repo_root, "apps/demo")


def test_bundle_docker_compose_release_requires_build_environment_before_changing_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed preflight must leave a previous release bundle and archive intact."""
    project = tmp_path / "compose"
    project.mkdir()
    (project / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "release.env").write_text("RELEASE_COMPOSE_PROJECT=compose\n")
    _, bundle, archive = _release.docker_compose_release_paths(tmp_path, "v1.0.0")
    bundle.mkdir(parents=True)
    marker = bundle / "keep.txt"
    marker.write_text("previous bundle")
    archive.write_bytes(b"previous archive")
    run = Mock()
    monkeypatch.setattr(_release.subprocess, "run", run)

    with pytest.raises(ValueError, match="Missing build environment"):
        _release.bundle_docker_compose_release("v1.0.0", tmp_path)

    run.assert_not_called()
    assert marker.read_text() == "previous bundle"
    assert archive.read_bytes() == b"previous archive"


def test_bundle_docker_compose_release_replaces_stale_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rebuild the same release without carrying stale files into its bundle or archive."""
    project = tmp_path / "compose"
    project.mkdir()
    (project / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "release.env").write_text("RELEASE_COMPOSE_PROJECT=compose\n")
    (tmp_path / "build.env").write_text("IMAGE=demo\n")
    _, bundle, archive = _release.docker_compose_release_paths(tmp_path, "v1.0.0")
    bundle.mkdir(parents=True)
    (bundle / "stale.txt").write_text("stale bundle")
    archive.write_bytes(b"stale archive")
    monkeypatch.setenv("CI_COMMIT_SHA", "abc123")
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[-2:] == ["config", "--images"]:
            return subprocess.CompletedProcess(command, 0, stdout="demo:latest\n")
        if command[:2] == ["docker", "save"]:
            Path(command[command.index("-o") + 1]).write_bytes(b"image data")
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr(_release.subprocess, "run", run)

    _release.bundle_docker_compose_release("v1.0.0", tmp_path)

    assert not (bundle / "stale.txt").exists()
    assert (bundle / "compose" / "docker-compose.yml").read_text() == "services: {}\n"
    assert (bundle / "images" / "demo_latest.tar").read_bytes() == b"image data"
    assert json.loads((bundle / "manifest.json").read_text()) == {
        "version": "v1.0.0",
        "commit_sha": "abc123",
        "images": [{"image": "demo:latest", "archive": "images/demo_latest.tar"}],
    }
    with tarfile.open(archive) as released:
        names = released.getnames()
        assert f"{bundle.name}/stale.txt" not in names
        assert f"{bundle.name}/images/demo_latest.tar" in names
    loads = [command for command in calls if command[:2] == ["docker", "load"]]
    assert len(loads) == 1
    assert Path(loads[0][-1]).name == "demo_latest.tar"
    assert calls[-1][-1] == "config"


@pytest.mark.parametrize("app_path", ["library/demo", "../apps/demo"])
def test_cli_release_application_directory_rejects_unsafe_targets(
    tmp_path: Path, app_path: str
) -> None:
    """Require CLI release targets to be direct repository app paths."""
    with pytest.raises(ValueError, match="CLI release target must be below apps/"):
        _release.cli_release_application_directory(tmp_path, app_path)


def test_docker_compose_release_paths_reject_path_separators(tmp_path: Path) -> None:
    """Reject release tags that could escape the release output directory."""
    with pytest.raises(ValueError, match="must not contain a path separator"):
        _release.docker_compose_release_paths(tmp_path, "../unsafe")


@pytest.mark.parametrize(
    ("version", "component", "expected"),
    [
        ("1.2.3", "major", "2.0.0"),
        ("1.2.3", "minor", "1.3.0"),
        ("1.2.3", "patch", "1.2.4"),
    ],
)
def test_bump_version_increments_the_requested_component(
    version: str, component: str, expected: str
) -> None:
    """Increment one semantic-version component and reset lower components."""
    assert _release.bump_version(version, component) == expected


@pytest.mark.parametrize("version", ["1.2", "01.2.3", "1.2.3-dev"])
def test_bump_version_rejects_invalid_semantic_versions(version: str) -> None:
    """Reject versions that do not use the supported three-part format."""
    with pytest.raises(ValueError, match="VERSION must be a semantic version"):
        _release.bump_version(version, "patch")


def test_run_hooks_runs_build_and_verify_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run both hooks after confirming that the build created an artifact."""
    target = tmp_path / "apps" / "demo"
    hooks = target / "release"
    hooks.mkdir(parents=True)
    build = hooks / "build.sh"
    verify = hooks / "verify.sh"
    build.write_text("")
    verify.write_text("")
    output = tmp_path / "output"
    output.mkdir()
    (output / "demo.whl").write_text("")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_release.subprocess, "run", run)

    _release.run_hooks(target, "v1.2.3", output, tmp_path)

    assert calls == [
        (["bash", str(build), "v1.2.3", str(output)], {"cwd": tmp_path, "check": True}),
        (["bash", str(verify), "v1.2.3", str(output)], {"cwd": tmp_path, "check": True}),
    ]


def test_run_hooks_rejects_missing_hooks(tmp_path: Path) -> None:
    """Require both release hook scripts before running a target."""
    with pytest.raises(ValueError, match="must provide release/build.sh and release/verify.sh"):
        _release.run_hooks(tmp_path, "v1.0.0", tmp_path / "output", tmp_path)


def test_run_hooks_rejects_builds_without_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a successful hook process that creates no release artifact."""
    hooks = tmp_path / "release"
    hooks.mkdir()
    (hooks / "build.sh").write_text("")
    (hooks / "verify.sh").write_text("")
    monkeypatch.setattr(
        _release.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
    )

    with pytest.raises(ValueError, match="did not create an artifact"):
        _release.run_hooks(tmp_path, "v1.0.0", tmp_path / "output", tmp_path)


def test_verify_bundle_creates_a_venv_and_installs_local_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify one application wheel against application and dependency artifacts."""
    application_output = tmp_path / "application"
    application_output.mkdir()
    wheel = application_output / "demo-1.0.0-py3-none-any.whl"
    wheel.write_text("")
    dependency_output = tmp_path / "dependency"
    dependency_output.mkdir()
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_release.subprocess, "run", run)

    _release.verify_bundle(application_output, [dependency_output], "3.14")

    assert calls[0][:4] == ["uv", "venv", "--python", "3.14"]
    assert calls[1] == [
        "uv",
        "pip",
        "install",
        "--python",
        calls[0][-1],
        "--no-index",
        "--find-links",
        str(application_output),
        "--find-links",
        str(dependency_output),
        str(wheel),
    ]


@pytest.mark.parametrize("wheel_names", [[], ["one.whl", "two.whl"]])
def test_verify_bundle_requires_exactly_one_application_wheel(
    tmp_path: Path, wheel_names: list[str]
) -> None:
    """Reject release directories without exactly one application wheel."""
    for wheel_name in wheel_names:
        (tmp_path / wheel_name).write_text("")

    with pytest.raises(ValueError, match="Expected exactly one application wheel"):
        _release.verify_bundle(tmp_path, [], "3.14")
