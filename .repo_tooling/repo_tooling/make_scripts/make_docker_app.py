"""Build or run a selected Docker-enabled application."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _apps, _config, _docker, _utils


def main(
    arguments: Sequence[str] | None = None,
    program_name: str | None = None,
    script_path: Path | None = None,
) -> int:
    """Dispatch the Docker build or run action."""
    arguments = sys.argv[1:] if arguments is None else arguments
    program_name = sys.argv[0] if program_name is None else program_name
    if len(arguments) != 1 or arguments[0] not in {"build", "run"}:
        print(
            f"Usage: {program_name} " + "{" + "build|run" + "}",
            file=sys.stderr,
        )
        return 2
    try:
        _config.require_feature("docker")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    repo_root = _utils.repo_root(Path(__file__) if script_path is None else script_path)
    if not _apps.docker_available():
        return 127
    applications = [
        application
        for application in _apps.docker_applications(repo_root / "apps")
        if application.language is not None
    ]
    if not applications:
        print(_docker.NO_APPLICATIONS, end="", file=sys.stderr)
        return 1
    application = _apps.choose_application(
        applications,
        f"Select an application to {arguments[0]}:",
        lambda application: application.name,
    )
    if application is None:
        return 0
    try:
        _apps.validate_application_language(repo_root, application.dockerfile.parent)
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    build_arguments = _docker.build_arguments()
    if build_arguments is None:
        return 1
    image_name = f"{application.name}:local"
    build_command = [
        "docker",
        "build",
        *build_arguments,
        "-f",
        str(application.dockerfile),
        "-t",
        image_name,
        str(repo_root),
    ]
    try:
        subprocess.run(build_command, check=True)
        if arguments[0] == "run":
            subprocess.run(
                ["docker", "run", "--rm", "--name", application.name, image_name],
                check=True,
            )
    except (OSError, subprocess.CalledProcessError) as error:
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
