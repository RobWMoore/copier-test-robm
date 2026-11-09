#!/usr/bin/env python3
"""Create an application under `apps/`, using the options enabled for this repository."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _apps, _config, _utils


def main(arguments: Sequence[str] | None = None, program_name: str | None = None) -> int:
    """Run the application-creation user interface."""
    if _apps.shutil.which("uv") is None:
        print(_apps.UV_NOT_FOUND, file=sys.stderr)
        return 127
    arguments = sys.argv[1:] if arguments is None else arguments
    program_name = Path(sys.argv[0]).name if program_name is None else program_name
    if arguments:
        print(f"Usage: {program_name}", file=sys.stderr)
        return 2
    repo_root = _utils.repo_root(Path(__file__))
    if _config.DEVELOPMENT_APPROACH == "application_only_development":
        return _apps.create_service_app(repo_root)
    app_kind = _apps.choose_app_kind()
    if app_kind is None:
        return 0
    if app_kind == "local-app":
        return _apps.create_local_app(repo_root)
    if app_kind == "service-app":
        return _apps.create_service_app(repo_root)
    print(f"Error: unsupported app kind: {app_kind}", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
