"""Manage repository release build and verification operations."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from repo_tooling import _docker

VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def bump_version(version: str, component: str) -> str:
    """Return a semantic version incremented at the requested component."""
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(
            f"VERSION must be a semantic version in MAJOR.MINOR.PATCH form, got {version!r}."
        )

    major, minor, patch = (int(part) for part in match.groups())
    if component == "major":
        major, minor, patch = major + 1, 0, 0
    elif component == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def run_hooks(path: Path, version: str, output: Path, repo_root: Path) -> None:
    """Run a CLI target's build and verification hooks into an output directory."""
    build = path / "release" / "build.sh"
    verify = path / "release" / "verify.sh"
    if not build.is_file() or not verify.is_file():
        raise ValueError(f"CLI target {path} must provide release/build.sh and release/verify.sh.")
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(["bash", str(build), version, str(output)], cwd=repo_root, check=True)
    if not any(item.is_file() for item in output.rglob("*")):
        raise ValueError(f"CLI build hook for {path} did not create an artifact.")
    subprocess.run(["bash", str(verify), version, str(output)], cwd=repo_root, check=True)


def verify_bundle(app_output: Path, dependency_outputs: list[Path], python_version: str) -> None:
    """Install one built wheel with local artifacts to verify its release bundle."""
    wheels = list(app_output.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"Expected exactly one application wheel in {app_output}")
    with tempfile.TemporaryDirectory(prefix="release-cli-verify-") as temporary_directory:
        environment = Path(temporary_directory) / "venv"
        subprocess.run(["uv", "venv", "--python", python_version, str(environment)], check=True)
        command = ["uv", "pip", "install", "--python", str(environment), "--no-index"]
        for directory in [app_output, *dependency_outputs]:
            command.extend(["--find-links", str(directory)])
        subprocess.run([*command, str(wheels[0])], check=True)


def extract_archive(archive_path: Path, destination: Path) -> None:
    """Extract an archive after confirming every member remains in destination."""
    destination_root = destination.resolve()
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            member_path = (destination / member.name).resolve()
            if destination_root != member_path and destination_root not in member_path.parents:
                raise ValueError(f"Release archive contains an unsafe path: {member.name}")
        archive.extractall(destination)


def configured_cli_apps(path: Path) -> list[str]:
    """Return CLI application paths declared in a release environment file."""
    if not path.is_file():
        raise ValueError(f"Missing release configuration: {path}")
    for line in path.read_text().splitlines():
        match = re.match(r"^\s*RELEASE_CLI_APPS\s*=\s*(.*?)\s*$", line)
        if match is not None:
            return match.group(1).strip().strip("\"'").split()
    raise ValueError("Set RELEASE_CLI_APPS in release.env before creating a release tag.")


def cli_release_application_directory(repo_root: Path, app_path: str) -> Path:
    """Validate and return the repository-local directory for a CLI release app."""
    relative_path = PurePosixPath(app_path)
    if not relative_path.parts or relative_path.parts[0] != "apps" or ".." in relative_path.parts:
        raise ValueError(f"CLI release target must be below apps/: {app_path}")
    directory = (repo_root / relative_path).resolve()
    if not directory.is_dir() or repo_root not in directory.parents:
        raise ValueError(f"CLI release target must be below apps/: {app_path}")
    return directory


def docker_compose_release_paths(repo_root: Path, release_tag: str) -> tuple[Path, Path, Path]:
    """Return the output, bundle, and archive paths for a Docker Compose release."""
    if not release_tag or "/" in release_tag or "\\" in release_tag:
        raise ValueError("release tag must not contain a path separator")
    output_root = repo_root / "dist" / "release"
    bundle_name = f"docker-compose-{release_tag}"
    return output_root, output_root / bundle_name, output_root / f"{bundle_name}.tar.gz"


def bundle_docker_compose_release(release_tag: str, repo_root: Path) -> None:
    """Create and verify the Docker Compose release bundle for a release tag."""
    output_root, bundle_directory, archive_path = docker_compose_release_paths(
        repo_root, release_tag
    )
    project_path = _docker.configured_compose_project(repo_root / "release.env")
    project_directory = _docker.compose_project_directory(repo_root, project_path)
    compose_file = project_directory / "docker-compose.yml"
    build_environment = repo_root / "build.env"
    if not build_environment.is_file():
        raise ValueError(f"Missing build environment: {build_environment}")

    output_root.mkdir(parents=True, exist_ok=True)
    if bundle_directory.exists():
        shutil.rmtree(bundle_directory)
    archive_path.unlink(missing_ok=True)
    (bundle_directory / "images").mkdir(parents=True)

    subprocess.run(
        _docker.compose_command(build_environment, project_directory, compose_file, "config"),
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        _docker.compose_command(build_environment, project_directory, compose_file, "build"),
        check=True,
    )
    subprocess.run(
        _docker.compose_command(
            build_environment, project_directory, compose_file, "pull", "--ignore-buildable"
        ),
        check=True,
    )
    result = subprocess.run(
        _docker.compose_command(
            build_environment, project_directory, compose_file, "config", "--images"
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    images = [image for image in result.stdout.splitlines() if image]
    if not images:
        raise ValueError(f"Docker Compose project does not reference any images: {project_path}")

    shutil.copytree(project_directory, bundle_directory / "compose")
    manifest_images: list[dict[str, str]] = []
    for image in images:
        archive_name = _docker.image_archive_name(image)
        archive = bundle_directory / "images" / archive_name
        subprocess.run(["docker", "image", "inspect", image], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "save", "-o", str(archive), image], check=True)
        manifest_images.append({"image": image, "archive": f"images/{archive_name}"})

    manifest = {
        "version": release_tag,
        "commit_sha": os.environ.get("CI_COMMIT_SHA", "unknown"),
        "images": manifest_images,
    }
    (bundle_directory / "manifest.json").write_text(f"{json.dumps(manifest, indent=2)}\n")

    with tarfile.open(archive_path, "w:gz") as release_archive:
        release_archive.add(bundle_directory, arcname=bundle_directory.name)

    with tempfile.TemporaryDirectory() as temporary_directory:
        verification_root = Path(temporary_directory)
        extract_archive(archive_path, verification_root)
        verification_bundle = verification_root / bundle_directory.name
        for image_archive in sorted((verification_bundle / "images").glob("*.tar")):
            subprocess.run(
                ["docker", "load", "-i", str(image_archive)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        verification_project = verification_bundle / "compose"
        subprocess.run(
            _docker.compose_command(
                build_environment,
                verification_project,
                verification_project / "docker-compose.yml",
                "config",
            ),
            check=True,
            stdout=subprocess.DEVNULL,
        )
