#!/usr/bin/env python3
"""Dispatch CLI releases to the implementation for each application's language."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tooling import _cargo, _config, _pyproject, _release, _utils


def main(arguments: Sequence[str] | None = None, script_path: Path | None = None) -> int:
    """Build release artifacts for every configured CLI application."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_tag")
    parsed_arguments = parser.parse_args(arguments)
    repo_root = _utils.repo_root(Path(__file__) if script_path is None else script_path)
    output_root = repo_root / "dist" / "release" / "cli"
    try:
        _config.require_feature("gitlab_ci")
        apps = _release.configured_cli_apps(repo_root / "release.env")
        if not apps:
            raise ValueError("Set RELEASE_CLI_APPS in release.env before creating a release tag.")
        applications: list[dict[str, object]] = []
        for app_path in apps:
            app_directory = _release.cli_release_application_directory(repo_root, app_path)
            manifests = {
                "python": app_directory / "pyproject.toml",
                "rust": app_directory / "Cargo.toml",
            }
            languages = [language for language, manifest in manifests.items() if manifest.is_file()]
            if len(languages) != 1:
                found = ", ".join(languages) or "none"
                raise ValueError(
                    "CLI release target must contain exactly one supported manifest "
                    f"(pyproject.toml or Cargo.toml): {app_directory} (found {found})"
                )
            language = languages[0]
            _config.require_language(language, app_path)
            output = output_root / app_directory.name
            if language == "python":
                shutil.rmtree(output, ignore_errors=True)
                output.mkdir(parents=True)
                app_data = _pyproject.read_toml(app_directory / "pyproject.toml")
                project = app_data.get("project", {})
                if not isinstance(project, dict) or not isinstance(project.get("name"), str):
                    raise ValueError(f"CLI release target has no [project].name: {app_path}")
                workspace = _pyproject.packages(repo_root)
                dependency_outputs: list[Path] = []
                manifest_dependencies: list[dict[str, str]] = []
                local = _pyproject.local_dependencies(
                    _utils.normalise_name(project["name"]),
                    _pyproject.dependencies(app_data),
                    workspace,
                )
                for name, path in local:
                    dependency_output = output / "dependencies" / path.name
                    _release.run_hooks(
                        path, parsed_arguments.release_tag, dependency_output, repo_root
                    )
                    dependency_outputs.append(dependency_output)
                    manifest_dependencies.append(
                        {
                            "package": name,
                            "path": path.relative_to(repo_root).as_posix(),
                            "artifact_directory": dependency_output.relative_to(
                                output_root.parent
                            ).as_posix(),
                        }
                    )
                _release.run_hooks(app_directory, parsed_arguments.release_tag, output, repo_root)
                _release.verify_bundle(output, dependency_outputs, _config.PYTHON_VERSION)
                result: dict[str, object] = {
                    "app": app_path,
                    "language": "python",
                    "artifact_directory": output.relative_to(output_root.parent).as_posix(),
                    "local_dependencies": manifest_dependencies,
                }
            elif language == "rust":
                manifest = app_directory / "Cargo.toml"
                metadata = _cargo.cargo_metadata(manifest, repo_root)
                cargo_package = _cargo.package_metadata(metadata, manifest)
                package_version = cargo_package.get("version")
                if not isinstance(package_version, str):
                    raise ValueError(f"Cargo metadata has no package version: {app_path}")
                if parsed_arguments.release_tag.removeprefix("v") != package_version:
                    raise ValueError(
                        f"Release tag {parsed_arguments.release_tag} does not match "
                        f"Rust package version {package_version}"
                    )
                binaries = _cargo.binary_names(cargo_package)
                target_directory = Path(str(metadata["target_directory"]))
                subprocess.run(
                    [
                        "cargo",
                        "build",
                        "--release",
                        "--locked",
                        "--manifest-path",
                        str(manifest),
                    ],
                    cwd=repo_root,
                    check=True,
                    env={**os.environ, "CARGO_INCREMENTAL": "0"},
                )
                shutil.rmtree(output, ignore_errors=True)
                output.mkdir(parents=True)
                artifacts: list[dict[str, str]] = []
                for name in binaries:
                    source = target_directory / "release" / name
                    if not source.is_file():
                        raise ValueError(f"Cargo did not create expected binary: {source}")
                    destination = output / name
                    shutil.copy2(source, destination)
                    artifacts.append({"name": name, "sha256": _utils.sha256_checksum(destination)})
                result = {
                    "app": app_path,
                    "language": "rust",
                    "artifact_directory": output.relative_to(output_root.parent).as_posix(),
                    "artifacts": artifacts,
                }
            else:  # pragma: no cover - languages come from the supported manifest map
                raise ValueError(f"Unsupported CLI application language: {language}")
            applications.append(result)
        release_manifest = {
            "version": parsed_arguments.release_tag,
            "commit_sha": os.environ.get("CI_COMMIT_SHA", "unknown"),
            "applications": applications,
        }
        with (output_root.parent / "cli-manifest.json").open("w") as file:
            json.dump(release_manifest, file, indent=2)
            file.write("\n")
    except _config.ConfigurationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except (KeyError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Release failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - delegates to the tested main()
    raise SystemExit(main())
