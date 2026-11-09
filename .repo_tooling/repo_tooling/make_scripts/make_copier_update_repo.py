#!/usr/bin/env python3
"""Update this repository from its Copier template."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_tooling import _copier, _utils


def main() -> int:
    arguments = _copier.parse_vcs_ref_argument(__doc__)
    repo_root = _utils.repo_root(Path(__file__))
    resume = _copier.resume_command("copier-update-repo", arguments.vcs_ref)

    try:
        _copier.require_root_answers(repo_root)
        _copier.abort_if_merge_conflicts(repo_root, "before starting", resume)
        print("Updating Copier template for the repository")
        _copier.run_update(
            [
                "uv",
                "tool",
                "run",
                "copier",
                "update",
                *_copier.vcs_ref_arguments(arguments.vcs_ref),
                str(repo_root),
            ],
            repo_root,
            "for the repository",
            resume,
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        if not isinstance(error, RuntimeError):
            print(f"Copier repository update failed: {error}", file=sys.stderr)
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
