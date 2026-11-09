#!/usr/bin/env python3
"""Update only this project's release version at its current Copier revision."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from repo_tooling import _config, _release, _utils

PROJECT_ROOT = _utils.repo_root(Path(__file__))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bump the project version and apply the Copier template update."
    )
    parser.add_argument("component", choices=("major", "minor", "patch"))
    args = parser.parse_args()

    try:
        _config.require_feature("gitlab_ci")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    current_version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    new_version = _release.bump_version(current_version, args.component)
    print(f"Bumping version: {current_version} -> {new_version}")
    subprocess.run(
        [
            "uv",
            "tool",
            "run",
            "copier",
            "update",
            "--defaults",
            "--vcs-ref",
            ":current:",
            "--data",
            f"project_version={new_version}",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    if (PROJECT_ROOT / "pyproject.toml").is_file():
        subprocess.run(["uv", "lock"], cwd=PROJECT_ROOT, check=True)
        print("Regenerated uv.lock")
    if (PROJECT_ROOT / "Cargo.toml").is_file():
        subprocess.run(["cargo", "generate-lockfile"], cwd=PROJECT_ROOT, check=True)
        print("Regenerated Cargo.lock")
    return 0


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    raise SystemExit(main())
