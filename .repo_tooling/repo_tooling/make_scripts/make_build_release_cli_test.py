"""Tests for language dispatch and CLI release artifact manifests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _config,
    _pyproject,
    _release,
    _utils,
)
from repo_tooling.make_scripts import (
    make_build_release_cli,
)


@pytest.fixture
def release_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    (tmp_path / "release.env").write_text('RELEASE_CLI_APPS="apps/demo"\n')
    (tmp_path / "apps" / "demo").mkdir(parents=True)
    return tmp_path


def test_release_requires_configured_applications(
    release_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (release_root / "release.env").write_text("RELEASE_CLI_APPS=\n")

    assert make_build_release_cli.main(["v1.0.0"]) == 1
    assert "Set RELEASE_CLI_APPS" in capsys.readouterr().err
    assert not (release_root / "dist").exists()


@pytest.mark.parametrize(
    "manifests",
    [[], ["pyproject.toml", "Cargo.toml"]],
)
def test_release_rejects_missing_or_ambiguous_manifests(
    manifests: list[str], release_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for manifest in manifests:
        (release_root / "apps" / "demo" / manifest).write_text("")

    assert make_build_release_cli.main(["v1.0.0"]) == 1
    assert "exactly one supported manifest" in capsys.readouterr().err
    assert not (release_root / "dist" / "release" / "cli-manifest.json").exists()


@pytest.mark.parametrize(
    "project", ['project = "invalid"\n', "[project]\n", "[project]\nname = 7\n"]
)
def test_python_release_requires_project_name(
    project: str, release_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (release_root / "apps" / "demo" / "pyproject.toml").write_text(project)

    assert make_build_release_cli.main(["v1.0.0"]) == 1
    assert "has no [project].name" in capsys.readouterr().err


@pytest.mark.parametrize("with_dependency", [False, True])
def test_python_release_builds_dependencies_before_application_and_records_artifacts(
    with_dependency: bool, release_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = release_root / "apps" / "demo"
    (app / "pyproject.toml").write_text(
        '[project]\nname = "Demo_App"\ndependencies = ["local-lib"]\n'
    )
    dependency = release_root / "libs" / "local_lib"
    workspace = {"local-lib": (dependency, ())} if with_dependency else {}
    monkeypatch.setattr(_pyproject, "packages", lambda _: workspace)
    hooks = Mock()
    verify = Mock()
    monkeypatch.setattr(_release, "run_hooks", hooks)
    monkeypatch.setattr(_release, "verify_bundle", verify)
    monkeypatch.setenv("CI_COMMIT_SHA", "abc123")
    monkeypatch.setattr("sys.argv", ["release-cli", "v1.0.0"])
    output = release_root / "dist" / "release" / "cli" / "demo"
    output.mkdir(parents=True)
    (output / "stale.whl").write_text("old")

    assert make_build_release_cli.main() == 0
    assert not (output / "stale.whl").exists()
    dependency_output = output / "dependencies" / "local_lib"
    expected_hooks = (
        [(dependency, "v1.0.0", dependency_output, release_root)] if with_dependency else []
    )
    expected_hooks.append((app, "v1.0.0", output, release_root))
    assert [call.args for call in hooks.call_args_list] == expected_hooks
    verify.assert_called_once_with(
        output,
        [dependency_output] if with_dependency else [],
        _config.PYTHON_VERSION,
    )
    manifest = json.loads((output.parent.parent / "cli-manifest.json").read_text())
    assert manifest == {
        "version": "v1.0.0",
        "commit_sha": "abc123",
        "applications": [
            {
                "app": "apps/demo",
                "language": "python",
                "artifact_directory": "cli/demo",
                "local_dependencies": [
                    {
                        "package": "local-lib",
                        "path": "libs/local_lib",
                        "artifact_directory": "cli/demo/dependencies/local_lib",
                    }
                ]
                if with_dependency
                else [],
            }
        ],
    }


@pytest.fixture
def rust_release(release_root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    (release_root / "apps" / "demo" / "Cargo.toml").write_text("")
    package: dict[str, object] = {"version": "1.0.0"}
    monkeypatch.setattr(
        make_build_release_cli._cargo,
        "cargo_metadata",
        lambda *_: {"target_directory": str(release_root / "target")},
    )
    monkeypatch.setattr(make_build_release_cli._cargo, "package_metadata", lambda *_: package)
    monkeypatch.setattr(make_build_release_cli._cargo, "binary_names", lambda _: ["demo"])
    return package


@pytest.mark.parametrize(
    ("version", "message"), [(None, "no package version"), ("2.0.0", "does not match")]
)
def test_rust_release_rejects_invalid_or_mismatched_package_version(
    version: object,
    message: str,
    rust_release: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    rust_release["version"] = version

    assert make_build_release_cli.main(["v1.0.0"]) == 1
    assert message in capsys.readouterr().err


def test_rust_release_reports_missing_binary(
    rust_release: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(make_build_release_cli.subprocess, "run", Mock())

    assert make_build_release_cli.main(["v1.0.0"]) == 1
    assert "did not create expected binary" in capsys.readouterr().err


def test_rust_release_builds_locked_binary_and_records_checksum(
    release_root: Path,
    rust_release: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = release_root / "target" / "release" / "demo"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"compiled binary")
    source.chmod(0o755)
    run = Mock()
    monkeypatch.setattr(make_build_release_cli.subprocess, "run", run)
    monkeypatch.delenv("CI_COMMIT_SHA", raising=False)

    assert make_build_release_cli.main(["v1.0.0"]) == 0
    run.assert_called_once()
    assert run.call_args.args[0] == [
        "cargo",
        "build",
        "--release",
        "--locked",
        "--manifest-path",
        str(release_root / "apps" / "demo" / "Cargo.toml"),
    ]
    assert run.call_args.kwargs["cwd"] == release_root
    assert run.call_args.kwargs["check"] is True
    assert run.call_args.kwargs["env"]["CARGO_INCREMENTAL"] == "0"
    destination = release_root / "dist" / "release" / "cli" / "demo" / "demo"
    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_mode == source.stat().st_mode
    manifest = json.loads((destination.parents[2] / "cli-manifest.json").read_text())
    assert manifest == {
        "version": "v1.0.0",
        "commit_sha": "unknown",
        "applications": [
            {
                "app": "apps/demo",
                "language": "rust",
                "artifact_directory": "cli/demo",
                "artifacts": [
                    {"name": "demo", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "error",
    [
        OSError("unreadable configuration"),
        KeyError("missing metadata"),
        subprocess.CalledProcessError(5, ["cargo"]),
    ],
)
def test_release_errors_report_failure_without_publishing_manifest(
    error: Exception,
    release_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_release, "configured_cli_apps", Mock(side_effect=error))

    assert make_build_release_cli.main(["v1.0.0"]) == 1
    assert "Release failed:" in capsys.readouterr().err
    assert not (release_root / "dist" / "release" / "cli-manifest.json").exists()
