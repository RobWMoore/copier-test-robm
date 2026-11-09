"""Select an Application-and-Library Development library and dispatch its removal."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _cargo, _config, _libs, _pyproject, _utils


def main(
    arguments: Sequence[str] | None = None,
    program_name: str | None = None,
    script_path: Path | None = None,
) -> int:
    """Run the interactive library-removal command."""
    try:
        _config.require_feature("libraries")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    arguments = sys.argv[1:] if arguments is None else arguments
    program_name = Path(sys.argv[0]).name if program_name is None else program_name
    if arguments:
        print(f"Usage: {program_name}", file=sys.stderr)
        return 2
    repo_root = _utils.repo_root(Path(__file__) if script_path is None else script_path)
    available_libraries = _libs.libraries(repo_root / "libs", _libs.configs())
    if not available_libraries:
        print("No Python or Rust libraries found under libs/.", file=sys.stderr)
        return 1
    library = _libs.choose_library(available_libraries)
    if library is None:
        return 0
    try:
        config = _libs.library_config(library, _libs.configs())
        library_path = library.relative_to(repo_root).as_posix()
        _config.require_language(config.language, library_path)
        if config.language == "python":
            name = _pyproject.project_name(library / "pyproject.toml")
            users = _pyproject.dependants(repo_root, library, name)
            if users:
                paths = ", ".join(path.as_posix() for path in users)
                raise ValueError(f"Cannot remove {name}; it is required by: {paths}")
            _pyproject.remove_from_root_project(repo_root, library_path, name)
            subprocess.run(["uv", "lock"], cwd=repo_root, check=True)
        elif config.language == "rust":
            name = _cargo.package_name(library / "Cargo.toml")
            users = _cargo.dependants(repo_root, library, name)
            if users:
                paths = ", ".join(path.as_posix() for path in users)
                raise ValueError(f"Cannot remove {name}; it is required by: {paths}")
            _cargo.remove_workspace_member(repo_root, library_path)
            if (repo_root / "Cargo.lock").is_file():
                subprocess.run(["cargo", "generate-lockfile"], cwd=repo_root, check=True)
        else:  # pragma: no cover - library_config returns an enabled language
            raise ValueError(f"Unsupported library language: {config.language}")
        shutil.rmtree(library)
        print(f"Removed {config.language.title()} library: {library_path}")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except (
        OSError,
        subprocess.CalledProcessError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        print(f"Library removal failed: {error}", file=sys.stderr)
        return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
    return 0


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
