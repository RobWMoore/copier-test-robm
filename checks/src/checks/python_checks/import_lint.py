#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import sys
import tomllib

from checks.project_checks import PROJECT_ROOT


def _pyproject_has_import_linter_config(path: pathlib.Path) -> bool:
    """Return whether `pyproject.toml` contains Import Linter configuration."""
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"Unable to read {path.name}: {error}", file=sys.stderr)
        return False

    tool_config = data.get("tool", {})
    if not isinstance(tool_config, dict):
        return False

    import_linter_config = tool_config.get("importlinter")
    if not isinstance(import_linter_config, dict):
        return False

    contracts = import_linter_config.get("contracts")
    return isinstance(contracts, list) and bool(contracts)


def resolve_import_linter_config() -> pathlib.Path | None:
    """Return `pyproject.toml` when the repository has opted in to Import Linter."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    if pyproject_path.is_file() and _pyproject_has_import_linter_config(pyproject_path):
        return pyproject_path

    return None


def main(args: list[str]) -> int:
    """Run Import Linter when the repository provides configuration."""
    config_path = resolve_import_linter_config()
    if config_path is None:
        print("Import Linter configuration not found; skipping import lint.")
        return 0

    command = ["lint-imports", "--config", str(config_path), *args]
    print(f"Running {' '.join(command)} in {PROJECT_ROOT}")
    try:
        return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
