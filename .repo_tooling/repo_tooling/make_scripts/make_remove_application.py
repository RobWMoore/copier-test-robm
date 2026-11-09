#!/usr/bin/env python3
"""Interactively remove an application under `apps/`."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _apps, _utils


def main(arguments: Sequence[str] | None = None, program_name: str | None = None) -> int:
    """Run the application-removal user interface."""
    arguments = sys.argv[1:] if arguments is None else arguments
    program_name = Path(sys.argv[0]).name if program_name is None else program_name
    if arguments:
        print(f"Usage: {program_name}", file=sys.stderr)
        return 2
    repo_root = _utils.repo_root(Path(__file__))
    selected_application = _apps.choose_application(
        _apps.applications(repo_root / "apps"),
        "Select an application to remove:",
        lambda application: application.name,
    )
    if selected_application is None:
        return 0
    return _apps.remove_application(repo_root, selected_application)


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
