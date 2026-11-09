#!/usr/bin/env python3
"""Shared implementation for creating and removing applications."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import tomlkit
from tomlkit.items import Array, Table

from repo_tooling import _cargo, _config, _copier, _utils

UV_NOT_FOUND = """Error: uv is required but was not found on PATH.

Install uv on macOS or Linux with:

    curl -LsSf https://astral.sh/uv/install.sh | sh

After installation, restart your shell or ensure uv is on PATH.
"""
Application = TypeVar("Application")


@dataclass(frozen=True)
class Library:
    name: str
    language: str


@dataclass(frozen=True)
class DockerApplication:
    """A direct application directory containing a Dockerfile."""

    name: str
    dockerfile: Path
    language: str | None


def docker_available() -> bool:
    """Return whether Docker is installed and can contact a usable daemon."""
    if shutil.which("docker") is None:
        print("Error: docker is required but was not found on PATH.", file=sys.stderr)
        return False
    try:
        subprocess.run(
            ["docker", "version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        print(
            "Error: Docker is unavailable; start Docker and try again.",
            file=sys.stderr,
        )
        return False
    return True


def docker_applications(apps_root: Path) -> list[DockerApplication]:
    """Return sorted direct, non-symlink applications with Dockerfiles."""
    if not apps_root.is_dir():
        return []
    applications: list[DockerApplication] = []
    for directory in sorted(apps_root.iterdir()):
        dockerfile = directory / "Dockerfile"
        if not directory.is_dir() or directory.is_symlink() or not dockerfile.is_file():
            continue
        language = (
            "python"
            if (directory / "pyproject.toml").is_file()
            else "rust"
            if (directory / "Cargo.toml").is_file()
            else None
        )
        applications.append(DockerApplication(directory.name, dockerfile, language))
    return applications


def applications(apps_root: Path) -> list[Path]:
    """Return removable application directories."""
    if not apps_root.is_dir():
        return []
    return [path for path in sorted(apps_root.iterdir()) if path.is_dir() and not path.is_symlink()]


def choose_application(
    available_applications: Sequence[Application],
    prompt: str,
    label: Callable[[Application], str],
) -> Application | None:
    """Prompt for an application, or return None when the user quits."""
    print(prompt)
    print("Enter q to quit.")
    for index, application in enumerate(available_applications, start=1):
        print(f"{index}) {label(application)}")
    while True:
        try:
            selection = input("Application number: ")
        except EOFError:
            print("Error: no application was selected.", file=sys.stderr)
            return None
        if selection.lower() == "q":
            return None
        try:
            index = int(selection)
            if 1 <= index <= len(available_applications):
                return available_applications[index - 1]
        except ValueError:
            pass
        print(f"Invalid selection: {selection}", file=sys.stderr)


def requirement_name(value: str) -> str | None:
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", value)
    return _utils.normalise_name(match.group(1)) if match else None


def remove_from_workspaces(repo_root: Path, app_directory: Path, app_path: str) -> None:
    """Remove an application from Python and Rust workspace manifests when present."""
    root_manifest = repo_root / "pyproject.toml"
    app_manifest = app_directory / "pyproject.toml"
    if root_manifest.is_file() and app_manifest.is_file():
        root = tomlkit.parse(root_manifest.read_text())
        application = tomlkit.parse(app_manifest.read_text())
        project = application.get("project")
        application_name = project.get("name") if isinstance(project, Table) else None
        workspace = root.get("tool", {}).get("uv", {}).get("workspace", {})
        members = workspace.get("members") if isinstance(workspace, Table) else None
        changed = False
        if isinstance(members, Array) and app_path in {str(member) for member in members}:
            members.remove(app_path)
            changed = True
        dependencies = root.get("project", {}).get("dependencies")
        if isinstance(application_name, str) and isinstance(dependencies, Array):
            for dependency in list(dependencies):
                if requirement_name(str(dependency)) == _utils.normalise_name(application_name):
                    dependencies.remove(dependency)
                    changed = True
        sources = root.get("tool", {}).get("uv", {}).get("sources", {})
        if isinstance(application_name, str) and isinstance(sources, Table):
            for source_name in list(sources):
                if _utils.normalise_name(str(source_name)) == _utils.normalise_name(
                    application_name
                ):
                    del sources[source_name]
                    changed = True
        if changed:
            root_manifest.write_text(tomlkit.dumps(root))
    workspace_manifest = repo_root / "Cargo.toml"
    if workspace_manifest.is_file():
        document = tomlkit.parse(workspace_manifest.read_text())
        workspace = document.get("workspace")
        members = workspace.get("members") if isinstance(workspace, Table) else None
        if isinstance(members, Array) and app_path in {str(member) for member in members}:
            members.remove(app_path)
            workspace_manifest.write_text(tomlkit.dumps(document))


def libraries(libs_root: Path) -> list[Library]:
    if not libs_root.is_dir():
        return []
    result: list[Library] = []
    for directory in sorted(libs_root.iterdir()):
        if not directory.is_dir():
            continue
        if (directory / "pyproject.toml").is_file():
            result.append(Library(directory.name, "python"))
        elif (directory / "Cargo.toml").is_file():
            result.append(Library(directory.name, "rust"))
    return result


def print_no_libraries_error(repo_root: Path) -> None:
    print("No Python or Rust libraries found.\n", file=sys.stderr)
    if _config.feature_enabled("libraries"):
        print("    make create-library", file=sys.stderr)
    print("\nLocal apps are created from library directories under:\n    libs/", file=sys.stderr)


def choose_app_kind() -> str | None:
    print("Select the kind of app to create:")
    print("Enter q to quit.")
    choices = [
        ("local-app", "Local app: runnable code owned by this repository"),
        ("service-app", "Service app: configuration for a third-party service"),
    ]
    for index, (_value, label) in enumerate(choices, start=1):
        print(f"{index}) {label}")

    while True:
        selection = input("App kind number: ")
        if selection.lower() == "q":
            return None
        try:
            index = int(selection)
            if 1 <= index <= len(choices):
                return choices[index - 1][0]
            raise ValueError
        except ValueError:
            print(f"Invalid selection: {selection}", file=sys.stderr)


def choose_library(available_libraries: list[Library]) -> Library | None:
    print("Select a Python or Rust library to create an application for:")
    print("Enter q to quit.")
    for index, library in enumerate(available_libraries, start=1):
        print(f"{index}) {library.name} ({library.language.capitalize()})")

    while True:
        selection = input("Library number: ")
        if selection.lower() == "q":
            return None
        try:
            index = int(selection)
            if 1 <= index <= len(available_libraries):
                return available_libraries[index - 1]
            raise ValueError
        except ValueError:
            print(f"Invalid selection: {selection}", file=sys.stderr)


def to_snake_case(value: str) -> str:
    return re.sub(r"_+$", "", re.sub(r"^_+", "", re.sub(r"[^a-z0-9]+", "_", value.lower())))


def prompt_snake_case_name(prompt: str, default: str) -> str:
    name = to_snake_case(input(f"{prompt} [{default}]: ") or default)
    if not name:
        raise ValueError("application name must contain at least one letter or digit.")
    return name


def local_application_name(library_name: str) -> str:
    wrapped_library_name = to_snake_case(library_name)
    if not wrapped_library_name:
        raise ValueError("wrapped library name must contain at least one letter or digit.")
    return prompt_snake_case_name("Application name", f"{wrapped_library_name}_app")


def service_application_name() -> str:
    return prompt_snake_case_name("Service app name", "service_app")


def ensure_available_app_directory(repo_root: Path, app_name: str) -> Path:
    application_directory = repo_root / "apps" / app_name
    if application_directory.exists() or application_directory.is_symlink():
        raise ValueError(f"application directory already exists: {application_directory}")
    return application_directory


def run_copier(command: list[str]) -> None:
    subprocess.run(command, check=True)


def add_release_target(release_environment: Path, variable: str, app_path: str) -> None:
    """Add an application path to a quoted, space-separated release target list."""
    if not release_environment.is_file():
        raise ValueError(f"Missing release configuration: {release_environment}")
    pattern = re.compile(rf"^(\s*{re.escape(variable)}\s*=\s*)([\"'])(.*)\2\s*$")
    with release_environment.open(newline="") as release_file:
        lines = release_file.readlines()
    for index, line in enumerate(lines):
        match = pattern.match(line.rstrip("\r\n"))
        if match is None:
            continue
        targets = match.group(3).split()
        if app_path not in targets:
            targets.append(app_path)
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        value = " ".join(targets)
        lines[index] = f"{match.group(1)}{match.group(2)}{value}{match.group(2)}{ending}"
        with release_environment.open("w", newline="") as release_file:
            release_file.writelines(lines)
        return
    raise ValueError(f"Missing {variable} in release.env")


def remove_release_target(release_environment: Path, variable: str, app_path: str) -> None:
    """Remove an application path from a release target list when present."""
    if not release_environment.is_file():
        raise ValueError(f"Missing release configuration: {release_environment}")
    pattern = re.compile(rf"^(\s*{re.escape(variable)}\s*=\s*)([\"'])(.*)\2\s*$")
    with release_environment.open(newline="") as release_file:
        lines = release_file.readlines()
    for index, line in enumerate(lines):
        match = pattern.match(line.rstrip("\r\n"))
        if match is None:
            continue
        targets = [target for target in match.group(3).split() if target != app_path]
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        lines[index] = (
            f"{match.group(1)}{match.group(2)}{' '.join(targets)}{match.group(2)}{ending}"
        )
        with release_environment.open("w", newline="") as release_file:
            release_file.writelines(lines)
        return


def create_local_app(repo_root: Path, language: str | None = None) -> int:
    """Create a local app, optionally restricted to one language."""
    try:
        if language is not None:
            _config.require_language(language)
        if not _config.ENABLED_PROGRAMMING_LANGUAGES:
            raise _config.ConfigurationError("language not enabled: python or rust.")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    available_libraries = libraries(repo_root / "libs")
    available_libraries = [
        library
        for library in available_libraries
        if library.language in _config.ENABLED_PROGRAMMING_LANGUAGES
    ]
    if language is not None:
        available_libraries = [
            library for library in available_libraries if library.language == language
        ]
    if not available_libraries:
        print_no_libraries_error(repo_root)
        return 1
    library = choose_library(available_libraries)
    if library is None:
        return 0

    try:
        app_name = local_application_name(library.name)
        application_directory = ensure_available_app_directory(repo_root, app_name)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    wrapped_library_name = to_snake_case(library.name)
    language_data = (
        ["--data", f"python_version={_config.PYTHON_VERSION}"]
        if library.language == "python"
        else [
            "--data",
            f"rust_msrv={_config.RUST_MSRV}",
            "--data",
            f"path_to_wrapped_library=../../libs/{library.name}",
        ]
    )
    application_directory.parent.mkdir(parents=True, exist_ok=True)
    print(f"Creating application directory: {application_directory}")
    command = [
        "uv",
        "tool",
        "run",
        "copier",
        "copy",
        *_copier.vcs_ref_arguments(os.environ.get("VCS_REF_APP_TEMPLATE")),
        "--data",
        "app_kind=local-app",
        "--data",
        f"wrapped_library_name={wrapped_library_name}",
        "--data",
        f"app_name={app_name}",
        "--data",
        f"programming_language={library.language}",
        "--data",
        f"allow_docker={str(_config.DOCKER_ENABLED).lower()}",
        "--data",
        f"uv_version={_config.UV_VERSION}",
        *language_data,
        _config.COPIER_APP_TEMPLATE_URL,
        str(application_directory),
    ]
    try:
        run_copier(command)
        if library.language == "python":
            subprocess.run(
                ["uv", "add", "--workspace", f"apps/{app_name}"],
                cwd=repo_root,
                check=True,
            )
        else:
            _cargo.add_workspace_member(repo_root, f"apps/{app_name}")
        if _config.GITLAB_CI_ENABLED:
            app_path = f"apps/{app_name}"
            add_release_target(repo_root / "release.env", "RELEASE_CLI_APPS", app_path)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Application creation failed: {error}", file=sys.stderr)
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


def create_service_app(repo_root: Path) -> int:
    try:
        app_name = service_application_name()
        application_directory = ensure_available_app_directory(repo_root, app_name)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    application_directory.parent.mkdir(parents=True, exist_ok=True)
    print(f"Creating service app directory: {application_directory}")
    command = [
        "uv",
        "tool",
        "run",
        "copier",
        "copy",
        *_copier.vcs_ref_arguments(os.environ.get("VCS_REF_APP_TEMPLATE")),
        "--data",
        "app_kind=service-app",
        "--data",
        f"app_name={app_name}",
        "--data",
        "programming_language=python",
        _config.COPIER_APP_TEMPLATE_URL,
        str(application_directory),
    ]
    try:
        run_copier(command)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Service app creation failed: {error}", file=sys.stderr)
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


def validate_application_language(repo_root: Path, application: Path) -> None:
    """Validate local application manifests while leaving service applications language-neutral."""
    if _copier.is_service_application(application):
        return
    for language, manifest in (("python", "pyproject.toml"), ("rust", "Cargo.toml")):
        if (application / manifest).is_file():
            _config.require_language(language, application.relative_to(repo_root).as_posix())


def remove_application(repo_root: Path, application: Path) -> int:
    """Remove one application after updating workspace configuration."""
    try:
        validate_application_language(repo_root, application)
        app_path = application.relative_to(repo_root).as_posix()
        remove_from_workspaces(repo_root, application, app_path)
        if _config.GITLAB_CI_ENABLED:
            remove_release_target(repo_root / "release.env", "RELEASE_CLI_APPS", app_path)
        shutil.rmtree(application)
        print(f"Removed application: {app_path}")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, tomlkit.exceptions.ParseError) as error:
        print(f"Application removal failed: {error}", file=sys.stderr)
        return 1
    return 0
