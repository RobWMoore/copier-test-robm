#!/usr/bin/env python3
"""Update generated libraries from their Copier template."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_tooling import _config, _copier, _utils


def main() -> int:
    arguments = _copier.parse_vcs_ref_argument(__doc__)
    repo_root = _utils.repo_root(Path(__file__))
    resume = _copier.resume_command("copier-update-libs", arguments.vcs_ref)

    try:
        _config.require_feature("libraries")
        _copier.require_root_answers(repo_root)
        libraries = _copier.component_directories(repo_root, "libs")
        _copier.validate_components(libraries, repo_root)
        _copier.abort_if_merge_conflicts(repo_root, "before starting", resume)
        for library in libraries:
            _copier.update_library(library, repo_root, arguments.vcs_ref)
        if not libraries:
            print("No generated libraries with .copier-answers.yml were found.")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        if not isinstance(error, RuntimeError):
            print(f"Copier library update failed: {error}", file=sys.stderr)
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
