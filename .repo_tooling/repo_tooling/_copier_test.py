"""Tests for shared Copier management helpers."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tooling import _config, _copier


def test_vcs_ref_arguments_and_resume_command() -> None:
    assert _copier.vcs_ref_arguments(None) == []
    assert _copier.vcs_ref_arguments("v1.2.3") == ["--vcs-ref", "v1.2.3"]
    assert _copier.resume_command("copier-update-apps", "feature branch") == (
        "make copier-update-apps VCS_REF_APP_TEMPLATE='feature branch'"
    )


@pytest.mark.parametrize(
    ("target", "variable"),
    [
        ("copier-update-repo", "VCS_REF_REPO_TEMPLATE"),
        ("copier-update-libs", "VCS_REF_LIB_TEMPLATE"),
        ("copier-update-apps", "VCS_REF_APP_TEMPLATE"),
        ("copier-update-docker-compose-scripts", "VCS_REF_COMPOSE_TEMPLATE"),
    ],
)
@pytest.mark.parametrize("vcs_ref", [None, "", "HEAD", "feature; echo unsafe"])
def test_resume_command_selects_only_its_template_revision(
    target: str, variable: str, vcs_ref: str | None
) -> None:
    """Keep recovery selections scoped to one template and shell quoted."""
    assert shlex.split(_copier.resume_command(target, vcs_ref)) == [
        "make",
        target,
        *([f"{variable}={vcs_ref}"] if vcs_ref else []),
    ]


def test_read_answer_handles_quotes_and_comments(tmp_path: Path) -> None:
    answers = tmp_path / ".copier-answers.yml"
    answers.write_text('project_name: "demo" # generated project\n')

    assert _copier.read_answer(answers, "project_name") == "demo"


def test_read_answer_rejects_missing_or_empty_values(tmp_path: Path) -> None:
    answers = tmp_path / ".copier-answers.yml"
    answers.write_text("project_name: \n")

    with pytest.raises(ValueError, match="project_name is missing"):
        _copier.read_answer(answers, "project_name")


def test_component_directories_returns_sorted_answer_parents(tmp_path: Path) -> None:
    for name in ("zebra", "alpha"):
        answers = tmp_path / "apps" / name / ".copier-answers.yml"
        answers.parent.mkdir(parents=True)
        answers.write_text("_src_path: template\n")

    assert _copier.component_directories(tmp_path, "apps") == [
        tmp_path / "apps" / "alpha",
        tmp_path / "apps" / "zebra",
    ]


def test_require_root_answers_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no .copier-answers.yml"):
        _copier.require_root_answers(tmp_path)


def test_abort_if_merge_conflicts_accepts_a_clean_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout="\n"))
    monkeypatch.setattr(_copier.subprocess, "run", run)

    _copier.abort_if_merge_conflicts(tmp_path, "before starting", "make copier-update-repo")

    run.assert_called_once_with(
        ["git", "-C", str(tmp_path), "diff", "--name-only", "--diff-filter=U"],
        check=True,
        capture_output=True,
        text=True,
    )
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize(
    ("context", "message"),
    [
        ("before starting", "Cannot start Copier update; unresolved merge conflicts remain in:"),
        ("for apps/demo", "Copier update for apps/demo left unresolved merge conflicts in:"),
    ],
)
def test_abort_if_merge_conflicts_reports_files_and_recovery_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    context: str,
    message: str,
) -> None:
    monkeypatch.setattr(
        _copier.subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess([], 0, stdout="apps/demo/file.py\nVERSION\n")
        ),
    )
    resume = "make copier-update-apps VCS_REF_APP_TEMPLATE=v2"

    with pytest.raises(RuntimeError, match="unresolved merge conflicts"):
        _copier.abort_if_merge_conflicts(tmp_path, context, resume)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"{message}\napps/demo/file.py\nVERSION\n"
        f"Resolve and stage the conflicted files, then rerun '{resume}'.\n"
    )


@pytest.mark.parametrize("returncode", [0, 17])
@pytest.mark.parametrize("conflicted", [False, True])
def test_run_update_checks_conflicts_before_propagating_process_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    returncode: int,
    conflicted: bool,
) -> None:
    """Prioritise actionable conflict diagnostics even when Copier also exits nonzero."""
    command = ["uv", "tool", "run", "copier", "update", str(tmp_path)]
    run = Mock(
        side_effect=[
            subprocess.CompletedProcess(command, returncode),
            subprocess.CompletedProcess([], 0, stdout="VERSION\n" if conflicted else ""),
        ]
    )
    monkeypatch.setattr(_copier.subprocess, "run", run)

    if conflicted:
        with pytest.raises(RuntimeError, match="unresolved merge conflicts"):
            _copier.run_update(command, tmp_path, "for the repository", "make copier-update-repo")
    elif returncode:
        with pytest.raises(subprocess.CalledProcessError) as error:
            _copier.run_update(command, tmp_path, "for the repository", "make copier-update-repo")
        assert error.value.returncode == returncode
        assert error.value.cmd == command
    else:
        _copier.run_update(command, tmp_path, "for the repository", "make copier-update-repo")

    assert run.call_count == 2
    assert run.call_args_list[0].args == (command,)
    assert run.call_args_list[0].kwargs == {"check": False}
    assert run.call_args_list[1].args == (
        ["git", "-C", str(tmp_path), "diff", "--name-only", "--diff-filter=U"],
    )
    assert ("Resolve and stage" in capsys.readouterr().err) is conflicted


@pytest.mark.parametrize(
    ("language", "version_data"),
    [("python", "python_version=3.13.1"), ("rust", "rust_msrv=1.85.0")],
)
def test_update_library_passes_language_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str, version_data: str
) -> None:
    monkeypatch.setattr(_config, "PYTHON_VERSION", "3.13.1")
    monkeypatch.setattr(_config, "RUST_MSRV", "1.85.0")
    library = tmp_path / "libs" / "example"
    library.mkdir(parents=True)
    (library / ".copier-answers.yml").write_text(f"programming_language: {language}\n")
    calls: list[tuple[list[str], Path, str, str]] = []
    monkeypatch.setattr(_copier, "run_update", lambda *args: calls.append(args))

    _copier.update_library(library, tmp_path, "v1")

    assert calls == [
        (
            [
                "uv",
                "tool",
                "run",
                "copier",
                "update",
                "--skip-answered",
                "--defaults",
                "--vcs-ref",
                "v1",
                "--data",
                version_data,
                str(library),
            ],
            tmp_path,
            "for libs/example",
            "make copier-update-libs VCS_REF_LIB_TEMPLATE=v1",
        )
    ]


@pytest.mark.parametrize(
    ("language", "version_data"),
    [("python", "python_version=3.13.1"), ("rust", "rust_msrv=1.85.0")],
)
def test_update_application_passes_template_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str, version_data: str
) -> None:
    monkeypatch.setattr(_config, "PYTHON_VERSION", "3.13.1")
    monkeypatch.setattr(_config, "RUST_MSRV", "1.85.0")
    monkeypatch.setattr(_config, "UV_VERSION", "0.11.28")
    application = tmp_path / "apps" / "example"
    application.mkdir(parents=True)
    (application / ".copier-answers.yml").write_text(f"programming_language: {language}\n")
    calls: list[tuple[list[str], Path, str, str]] = []
    monkeypatch.setattr(_copier, "run_update", lambda *args: calls.append(args))

    _copier.update_application(application, tmp_path, None)

    assert calls == [
        (
            [
                "uv",
                "tool",
                "run",
                "copier",
                "update",
                "--skip-answered",
                "--defaults",
                "--data",
                "allow_docker=True",
                "--data",
                "uv_version=0.11.28",
                "--data",
                version_data,
                str(application),
            ],
            tmp_path,
            "for apps/example",
            "make copier-update-apps",
        )
    ]


def test_update_compose_project_uses_shared_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose_project = tmp_path / "docker-compose-scripts" / "example"
    calls: list[tuple[list[str], Path, str, str]] = []
    monkeypatch.setattr(_copier, "run_update", lambda *args: calls.append(args))

    _copier.update_compose_project(compose_project, tmp_path, None)

    assert calls == [
        (
            [
                "uv",
                "tool",
                "run",
                "copier",
                "update",
                "--skip-answered",
                "--defaults",
                str(compose_project),
            ],
            tmp_path,
            "for docker-compose-scripts/example",
            "make copier-update-docker-compose-scripts",
        )
    ]


def test_update_library_rejects_unsupported_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "libs" / "example"
    library.mkdir(parents=True)
    (library / ".copier-answers.yml").write_text("programming_language: go\n")
    monkeypatch.setattr(_copier, "run_update", lambda *args: pytest.fail("unexpected update"))

    with pytest.raises(ValueError, match="unsupported programming language for libs/example: go"):
        _copier.update_library(library, tmp_path, None)
