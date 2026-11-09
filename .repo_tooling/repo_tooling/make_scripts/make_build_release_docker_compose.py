"""Build and verify an offline Docker Compose deployment release bundle."""

from __future__ import annotations

import subprocess
import sys
import tarfile
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _apps, _config, _release, _utils


def main(
    arguments: Sequence[str] | None = None,
    program_name: str | None = None,
    script_path: Path | None = None,
) -> int:
    """Build and verify one Docker Compose deployment release bundle."""
    arguments = sys.argv[1:] if arguments is None else arguments
    program_name = sys.argv[0] if program_name is None else program_name
    if len(arguments) != 1:
        print(f"Usage: {program_name} <release-tag>", file=sys.stderr)
        return 2
    try:
        _config.require_feature("gitlab_ci")
        _config.require_feature("docker")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    if not _apps.docker_available():
        return 127
    try:
        _release.bundle_docker_compose_release(
            arguments[0],
            _utils.repo_root(Path(__file__) if script_path is None else script_path),
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        ValueError,
        tarfile.TarError,
    ) as error:
        print(f"Release failed: {error}", file=sys.stderr)
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
