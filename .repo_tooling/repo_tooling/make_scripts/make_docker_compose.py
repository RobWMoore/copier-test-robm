"""Run Docker Compose projects or generate a single-service example."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _apps, _config, _docker, _utils

NO_PROJECTS = """No Docker Compose projects found.

Add services to the main Compose project, then run this command again.
"""
NO_APPLICATIONS = """No Docker-enabled applications found.

Create an application with a Dockerfile first, then run this command again.
"""
UV_NOT_FOUND = """Error: uv is required but was not found on PATH.

Install uv on macOS or Linux with:

    curl -LsSf https://astral.sh/uv/install.sh | sh

After installation, restart your shell or ensure uv is on PATH.
"""


def _up(repo_root: Path) -> int:
    """Interactively start one or all Docker Compose projects."""
    if shutil.which("docker") is None:
        print("Error: docker is required but was not found on PATH.", file=sys.stderr)
        return 127
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        print(
            "Error: Docker Compose is required but 'docker compose' is unavailable.",
            file=sys.stderr,
        )
        return 127
    projects = _docker.compose_projects(repo_root / "docker-compose-scripts")
    if not projects:
        print(NO_PROJECTS, end="", file=sys.stderr)
        return 1
    env_file = repo_root / "build.env"
    if not env_file.is_file() or not os.access(env_file, os.R_OK):
        print(
            f"Error: required environment file is missing or unreadable: {env_file}",
            file=sys.stderr,
        )
        return 1
    selected = _docker.choose_compose_project(projects, "up")
    if selected is None:
        return 0
    try:
        if selected == "all":
            for compose_file in projects:
                print(f"Starting {compose_file.parent.name}...")
                _docker.run_compose(compose_file, env_file, "up", detached=True)
        else:
            _docker.run_compose(selected, env_file, "up", detached=False)
    except (OSError, subprocess.CalledProcessError) as error:
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


def _down(repo_root: Path) -> int:
    """Interactively stop one or all Docker Compose projects."""
    if shutil.which("docker") is None:
        print("Error: docker is required but was not found on PATH.", file=sys.stderr)
        return 127
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        print(
            "Error: Docker Compose is required but 'docker compose' is unavailable.",
            file=sys.stderr,
        )
        return 127
    projects = _docker.compose_projects(repo_root / "docker-compose-scripts")
    if not projects:
        print(NO_PROJECTS, end="", file=sys.stderr)
        return 1
    env_file = repo_root / "build.env"
    if not env_file.is_file() or not os.access(env_file, os.R_OK):
        print(
            f"Error: required environment file is missing or unreadable: {env_file}",
            file=sys.stderr,
        )
        return 1
    selected = _docker.choose_compose_project(projects, "down")
    if selected is None:
        return 0
    try:
        if selected == "all":
            for compose_file in projects:
                print(f"Stopping {compose_file.parent.name}...")
                _docker.run_compose(compose_file, env_file, "down", detached=False)
        else:
            _docker.run_compose(selected, env_file, "down", detached=False)
    except (OSError, subprocess.CalledProcessError) as error:
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


def _example(repo_root: Path) -> int:
    """Interactively generate a single-service Docker Compose example."""
    if shutil.which("uv") is None:
        print(UV_NOT_FOUND, end="", file=sys.stderr)
        return 127
    applications = []
    for candidate in _apps.docker_applications(repo_root / "apps"):
        if candidate.language is None:
            print(
                f"Skipping application without a recognised language: {candidate.name}",
                file=sys.stderr,
            )
            continue
        applications.append(candidate)
    if not applications:
        print(NO_APPLICATIONS, end="", file=sys.stderr)
        return 1
    application = _apps.choose_application(
        applications,
        "Select an application to create a Docker Compose project for:",
        lambda application: f"{application.language}/{application.name}",
    )
    if application is None:
        return 0
    try:
        if application.language is not None:
            _config.require_language(application.language, f"apps/{application.name}")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    compose_root = repo_root / "docker-compose-scripts"
    destination = compose_root / f"{application.name}_example"
    if destination.exists() or destination.is_symlink():
        print(
            f"Error: Docker Compose project directory already exists: {destination}",
            file=sys.stderr,
        )
        return 1
    compose_root.mkdir(parents=True, exist_ok=True)
    print(f"Creating Docker Compose project directory: {destination}")
    service_name = _utils.to_kebab_case(application.name)
    vcs_ref = os.environ.get("VCS_REF_COMPOSE_TEMPLATE")
    command = [
        "uv",
        "tool",
        "run",
        "copier",
        "copy",
        *(["--vcs-ref", vcs_ref] if vcs_ref else []),
        "--data",
        f"app_name={application.name}",
        "--data",
        f"app_language={application.language}",
        "--data",
        "build_context=../..",
        "--data",
        f"dockerfile=apps/{application.name}/Dockerfile",
        "--data",
        f"image_name={service_name}:local",
        "--data",
        f"service_name={service_name}",
        _config.COPIER_DOCKER_COMPOSE_TEMPLATE_URL,
        str(destination),
    ]
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


def main(
    arguments: Sequence[str] | None = None,
    program_name: str | None = None,
    script_path: Path | None = None,
) -> int:
    """Dispatch one Docker Compose action."""
    arguments = sys.argv[1:] if arguments is None else arguments
    program_name = sys.argv[0] if program_name is None else program_name
    if len(arguments) != 1 or arguments[0] not in {"up", "down", "example"}:
        print(
            f"Usage: {program_name} " + "{" + "up|down|example" + "}",
            file=sys.stderr,
        )
        return 2
    repo_root = _utils.repo_root(Path(__file__) if script_path is None else script_path)
    try:
        _config.require_feature("docker")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    actions = {"up": _up, "down": _down, "example": _example}
    return actions[arguments[0]](repo_root)


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
