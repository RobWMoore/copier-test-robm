#!/usr/bin/env python3
"""Interactively create and register a library under `libs/`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _cargo, _config, _libs, _utils

UV_NOT_FOUND = """Error: uv is required but was not found on PATH.

Install uv on macOS or Linux with:

    curl -LsSf https://astral.sh/uv/install.sh | sh

After installation, restart your shell or ensure uv is on PATH.
"""


def main(arguments: Sequence[str] | None = None, program_name: str | None = None) -> int:
    """Create a library using the selected language configuration."""
    try:
        _config.require_feature("libraries")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    program_name = Path(sys.argv[0]).name if program_name is None else program_name
    library_name: str | None = None
    language: str | None = None
    vcs_ref: str | None = None
    argument_index = 0
    while argument_index < len(arguments):
        argument = arguments[argument_index]
        if argument in {"--language", "--vcs-ref"}:
            argument_index += 1
            if argument_index == len(arguments):
                break
            value = arguments[argument_index]
            if argument == "--language" and language is None:
                language = value
            elif argument == "--vcs-ref" and vcs_ref is None:
                vcs_ref = value
            else:
                break
        elif argument.startswith("--language=") and language is None:
            language = argument.removeprefix("--language=")
            if not language:
                break
        elif argument.startswith("--vcs-ref=") and vcs_ref is None:
            vcs_ref = argument.removeprefix("--vcs-ref=")
            if not vcs_ref:
                break
        elif library_name is None:
            library_name = argument
        else:
            break
        argument_index += 1
    else:
        config: _libs.LibraryConfig
        if language is not None:
            selected_config = next(
                (item for item in _libs.configs() if item.language == language), None
            )
            if selected_config is None:
                print(
                    "Error: language must be one of: "
                    f"{', '.join(config.language for config in _libs.configs())}.",
                    file=sys.stderr,
                )
                return 2
            config = selected_config
        try:
            if language is not None:
                _config.require_language(language)
            elif not _libs.configs(enabled_only=True):
                raise _config.ConfigurationError("language not enabled: python or rust.")
        except _config.ConfigurationError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        if shutil.which("uv") is None:
            print(UV_NOT_FOUND, end="", file=sys.stderr)
            return 127
        if language is None:
            config = _libs.choose_config(_libs.configs(enabled_only=True))
        if library_name is None:
            library_name = (
                input(f"{config.prompt} [{config.default_name}]: ") or config.default_name
            )
        library_name = _libs.to_snake_case(library_name)
        if not library_name:
            print(f"Error: {config.empty_name_error}", file=sys.stderr)
            return 2
        repo_root = _utils.repo_root(Path(__file__))
        destination_directory = repo_root / "libs" / library_name
        if destination_directory.exists():
            print(
                f"Error: {config.existing_directory_error}: {destination_directory}",
                file=sys.stderr,
            )
            return 1
        destination_directory.parent.mkdir(parents=True, exist_ok=True)
        copier_command = [
            "uv",
            "tool",
            "run",
            "copier",
            "copy",
            *(["--vcs-ref", vcs_ref] if vcs_ref is not None else []),
            "--data",
            f"programming_language={config.language}",
            "--data",
            f"package_name={library_name}",
            "--data",
            config.version_data,
            _config.COPIER_LIB_TEMPLATE_URL,
            str(destination_directory),
        ]
        library_path = f"libs/{library_name}"
        try:
            subprocess.run(copier_command, check=True)
            if config.language == "python":
                subprocess.run(
                    ["uv", "add", "--workspace", library_path], cwd=repo_root, check=True
                )
            else:
                _cargo.add_workspace_member(repo_root, library_path)
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            return error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
        return 0
    print(
        f"Usage: {program_name} [library_name] [--language python|rust] [--vcs-ref REVISION]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
