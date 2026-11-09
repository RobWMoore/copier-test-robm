"""Shared helpers for generated Copier management scripts."""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

from repo_tooling import _config


def parse_vcs_ref_argument(description: str | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--vcs-ref", help="Copier template revision to use for this update")
    return parser.parse_args()


def vcs_ref_arguments(vcs_ref: str | None) -> list[str]:
    if not vcs_ref:
        return []
    return ["--vcs-ref", vcs_ref]


def resume_command(target: str, vcs_ref: str | None) -> str:
    variable = {
        "copier-update-repo": "VCS_REF_REPO_TEMPLATE",
        "copier-update-libs": "VCS_REF_LIB_TEMPLATE",
        "copier-update-apps": "VCS_REF_APP_TEMPLATE",
        "copier-update-docker-compose-scripts": "VCS_REF_COMPOSE_TEMPLATE",
    }[target]
    command = f"make {target}"
    if vcs_ref:
        command = f"{command} {variable}={shlex.quote(vcs_ref)}"
    return command


def read_answer(answers_file: Path, key: str) -> str:
    expression = re.compile(rf"^{re.escape(key)}\s*[:=]\s*(.*)$")
    for line in answers_file.read_text().splitlines():
        match = expression.match(line)
        if match is None:
            continue
        value = match.group(1).split(" #", maxsplit=1)[0].strip().strip("\"'")
        if value:
            return value
        break
    raise ValueError(f"{key} is missing from {answers_file}")


def require_root_answers(repo_root: Path) -> Path:
    root_answers = repo_root / ".copier-answers.yml"
    if not root_answers.is_file():
        raise ValueError("the repository has no .copier-answers.yml file.")
    return root_answers


def component_directories(repo_root: Path, directory_name: str) -> list[Path]:
    component_root = repo_root / directory_name
    if not component_root.is_dir():
        return []
    answers_files = component_root.glob("*/.copier-answers.yml")
    return sorted(answers_file.parent for answers_file in answers_files)


def abort_if_merge_conflicts(repo_root: Path, context: str, resume: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--name-only", "--diff-filter=U"],
        check=True,
        capture_output=True,
        text=True,
    )
    conflicted_files = result.stdout.strip()
    if not conflicted_files:
        return

    if context == "before starting":
        print(
            "Cannot start Copier update; unresolved merge conflicts remain in:",
            file=sys.stderr,
        )
    else:
        print(
            f"Copier update {context} left unresolved merge conflicts in:",
            file=sys.stderr,
        )
    print(conflicted_files, file=sys.stderr)
    print(
        f"Resolve and stage the conflicted files, then rerun '{resume}'.",
        file=sys.stderr,
    )
    raise RuntimeError("unresolved merge conflicts")


def run_update(command: list[str], repo_root: Path, context: str, resume: str) -> None:
    result = subprocess.run(command, check=False)
    abort_if_merge_conflicts(repo_root, context, resume)
    result.check_returncode()


def _component_update_command(vcs_ref: str | None) -> list[str]:
    return [
        "uv",
        "tool",
        "run",
        "copier",
        "update",
        "--skip-answered",
        "--defaults",
        *vcs_ref_arguments(vcs_ref),
    ]


def is_service_application(component: Path) -> bool:
    """Identify third-party service configuration without requiring application-language support."""
    answers = component / ".copier-answers.yml"
    if not answers.is_file():
        return False
    try:
        return read_answer(answers, "app_kind") == "service-app"
    except ValueError:
        return False


def component_language(component: Path, repo_root: Path) -> str | None:
    """Return a supported component language, treating service applications as language-neutral."""
    if is_service_application(component):
        return None
    language = read_answer(component / ".copier-answers.yml", "programming_language")
    if language not in ("python", "rust"):
        relative_component = component.relative_to(repo_root).as_posix()
        raise ValueError(f"unsupported programming language for {relative_component}: {language}")
    return language


def validate_components(components: list[Path], repo_root: Path) -> None:
    """Report every disabled-language component before starting a batch of Copier updates."""
    errors: list[str] = []
    for component in components:
        language = component_language(component, repo_root)
        if language is None:
            continue
        try:
            _config.require_language(language, component.relative_to(repo_root).as_posix())
        except _config.ConfigurationError as error:
            errors.append(str(error))
    if errors:
        raise _config.ConfigurationError("\n".join(errors))


def _language_update_data(component: Path, repo_root: Path) -> list[str]:
    """Build language-specific Copier arguments using the current generated settings."""
    language = component_language(component, repo_root)
    if language is None:
        return []
    _config.require_language(language, component.relative_to(repo_root).as_posix())
    if language == "python":
        return [
            "--data",
            f"python_version={_config.PYTHON_VERSION}",
        ]
    return ["--data", f"rust_msrv={_config.RUST_MSRV}"]


def _run_component_update(
    component: Path,
    repo_root: Path,
    vcs_ref: str | None,
    target: str,
    command: list[str],
) -> None:
    relative_component = component.relative_to(repo_root).as_posix()
    print(f"Updating Copier template for {relative_component}")
    run_update(
        [*command, str(component)],
        repo_root,
        f"for {relative_component}",
        resume_command(target, vcs_ref),
    )


def update_library(library: Path, repo_root: Path, vcs_ref: str | None) -> None:
    """Update an enabled library using current repository settings."""
    _config.require_feature("libraries")
    command = _component_update_command(vcs_ref)
    command.extend(_language_update_data(library, repo_root))
    _run_component_update(library, repo_root, vcs_ref, "copier-update-libs", command)


def update_application(
    application: Path,
    repo_root: Path,
    vcs_ref: str | None,
) -> None:
    """Update local or service application configuration from its Copier template."""
    command = _component_update_command(vcs_ref)
    command.extend(
        (
            "--data",
            f"allow_docker={_config.DOCKER_ENABLED}",
            "--data",
            f"uv_version={_config.UV_VERSION}",
        )
    )
    command.extend(_language_update_data(application, repo_root))
    _run_component_update(application, repo_root, vcs_ref, "copier-update-apps", command)


def update_compose_project(compose_project: Path, repo_root: Path, vcs_ref: str | None) -> None:
    _config.require_feature("docker")
    _run_component_update(
        compose_project,
        repo_root,
        vcs_ref,
        "copier-update-docker-compose-scripts",
        _component_update_command(vcs_ref),
    )
