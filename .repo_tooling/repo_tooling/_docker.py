"""Manage Docker and Docker Compose project operations."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Literal

from repo_tooling import _config

NO_APPLICATIONS = """No Docker-enabled Python or Rust applications found.

Create an application with a Dockerfile and either pyproject.toml or
Cargo.toml, then run this command again.
"""


def build_argument_environment_variables() -> tuple[tuple[str, str], ...]:
    """Return build argument mappings for the currently enabled application languages."""
    language_arguments = {
        "python": (("PYTHON_IMAGE", "PYTHON_IMAGE"), ("UV_VERSION", "UV_VERSION")),
        "rust": (("RUST_IMAGE", "RUST_IMAGE"), ("RUST_RUNTIME_IMAGE", "RUST_RUNTIME_IMAGE")),
    }
    return tuple(
        argument
        for language in _config.ENABLED_PROGRAMMING_LANGUAGES
        for argument in language_arguments[language]
    )


def configured_compose_project(release_environment: Path) -> str:
    """Read RELEASE_COMPOSE_PROJECT from a release environment file."""
    if not release_environment.is_file():
        raise ValueError(f"Missing release configuration: {release_environment}")
    for line in release_environment.read_text().splitlines():
        match = re.match(r"^\s*RELEASE_COMPOSE_PROJECT\s*=\s*(.*?)\s*$", line)
        if match is not None:
            return match.group(1).strip().strip("\"'")
    raise ValueError("Set RELEASE_COMPOSE_PROJECT in release.env before creating a release tag.")


def compose_project_directory(repo_root: Path, project_path: str) -> Path:
    """Return a repository-contained Docker Compose project directory."""
    if not project_path:
        raise ValueError(
            "Set RELEASE_COMPOSE_PROJECT in release.env before creating a release tag."
        )
    relative_path = PurePosixPath(project_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(
            f"Docker Compose release target must be within the repository: {project_path}"
        )
    directory = (repo_root / relative_path).resolve()
    if not directory.is_dir() or repo_root.resolve() not in directory.parents:
        raise ValueError(
            f"Docker Compose release target must be within the repository: {project_path}"
        )
    if not (directory / "docker-compose.yml").is_file():
        raise ValueError(f"Docker Compose release target has no docker-compose.yml: {project_path}")
    return directory


def compose_command(
    build_environment: Path,
    project_directory: Path,
    compose_file: Path,
    *arguments: str,
) -> list[str]:
    """Return a Docker Compose command for a project."""
    return [
        "docker",
        "compose",
        "--env-file",
        str(build_environment),
        "--project-directory",
        str(project_directory),
        "-f",
        str(compose_file),
        *arguments,
    ]


def image_archive_name(image: str) -> str:
    """Return the archive filename for a Docker image in a release bundle."""
    return f"{image.replace('/', '_').replace(':', '_')}.tar"


def build_arguments() -> list[str] | None:
    """Return Docker build arguments from required environment variables."""
    arguments: list[str] = []
    for argument_name, environment_variable in build_argument_environment_variables():
        value = os.environ.get(environment_variable)
        if value is None:
            print(
                f"Error: required environment variable {environment_variable} must be set.",
                file=sys.stderr,
            )
            return None
        arguments.extend(["--build-arg", f"{argument_name}={value}"])
    return arguments


def compose_projects(compose_root: Path) -> list[Path]:
    """Return sorted Compose files from valid project directories."""
    if not compose_root.is_dir():
        return []
    return [
        compose_file
        for directory in sorted(compose_root.iterdir())
        if directory.is_dir()
        and not directory.is_symlink()
        and (compose_file := directory / "docker-compose.yml").is_file()
    ]


def choose_compose_project(projects: Sequence[Path], action: str) -> Path | Literal["all"] | None:
    """Select one Compose project, all projects, or quit."""
    action_label = "start" if action == "up" else "stop"
    all_label = "start all projects in detached mode" if action == "up" else "stop all projects"
    print(f"Select a Docker Compose project to {action_label}:")
    print(f"Enter a to {all_label}.")
    print("Enter q to quit.")
    for index, compose_file in enumerate(projects, start=1):
        print(f"{index}) {compose_file.parent.name}")
    while True:
        try:
            selection = input("Project number: ")
        except EOFError:
            print("Error: no Docker Compose project was selected.", file=sys.stderr)
            return None
        if selection.lower() == "q":
            return None
        if selection.lower() == "a":
            return "all"
        try:
            index = int(selection)
            if 1 <= index <= len(projects):
                return projects[index - 1]
        except ValueError:
            pass
        print(f"Invalid selection: {selection}", file=sys.stderr)


def run_compose(compose_file: Path, env_file: Path, action: str, detached: bool) -> None:
    """Run one Docker Compose project."""
    command = ["docker", "compose", "--env-file", str(env_file), "-f", str(compose_file)]
    if action == "up":
        command.extend(["up", "--build"])
        if detached:
            command.append("--detach")
    else:
        command.append("down")
    subprocess.run(command, check=True)
