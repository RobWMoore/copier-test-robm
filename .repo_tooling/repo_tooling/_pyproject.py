"""Manage repository Python projects through their pyproject.toml files."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import tomlkit
from tomlkit.items import Array, Table

from repo_tooling import _utils


def requirement_name(value: str) -> str | None:
    """Return the normalised distribution name at the start of a requirement."""
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", value)
    return _utils.normalise_name(match.group(1)) if match else None


def read_toml(path: Path) -> dict[str, object]:
    """Load and return the TOML document at a path."""
    with path.open("rb") as file:
        return tomllib.load(file)


def mapping(value: object, name: str) -> dict[str, object]:
    """Return a TOML mapping or raise a clear configuration error."""
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid {name} configuration")
    return value


def dependencies(data: dict[str, object]) -> tuple[str, ...]:
    """Return validated dependency declarations from project metadata."""
    project = data.get("project", {})
    values = project.get("dependencies", []) if isinstance(project, dict) else []
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError("project.dependencies must be a list of strings")
    return tuple(values)


def project_name(path: Path) -> str:
    """Return the validated project name declared by a pyproject.toml file."""
    with path.open("rb") as file:
        project = tomllib.load(file).get("project")
    if not isinstance(project, dict) or not isinstance(project.get("name"), str):
        raise TypeError(f"Python library has no [project].name: {path}")
    return project["name"]


def packages(repo_root: Path) -> dict[str, tuple[Path, tuple[str, ...]]]:
    """Index Python uv-workspace packages by normalised distribution name."""
    root = read_toml(repo_root / "pyproject.toml")
    tool = mapping(root.get("tool"), "[tool]")
    uv = mapping(tool.get("uv"), "[tool.uv]")
    workspace = mapping(uv.get("workspace"), "[tool.uv.workspace]")
    members = workspace.get("members")
    if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
        raise ValueError("[tool.uv.workspace].members must be a list of strings")
    result: dict[str, tuple[Path, tuple[str, ...]]] = {}
    for pattern in members:
        for directory in repo_root.glob(pattern):
            pyproject = directory / "pyproject.toml"
            if not pyproject.is_file():
                continue
            data = read_toml(pyproject)
            project = data.get("project", {})
            if not isinstance(project, dict) or not isinstance(project.get("name"), str):
                continue
            name = _utils.normalise_name(project["name"])
            if name in result:
                raise ValueError(f"Workspace contains duplicate package name: {name}")
            result[name] = (directory.resolve(), dependencies(data))
    return result


def local_dependencies(
    app_name: str,
    app_dependencies: tuple[str, ...],
    workspace: dict[str, tuple[Path, tuple[str, ...]]],
) -> list[tuple[str, Path]]:
    """Return an app's local transitive dependencies in installation order."""
    result: list[tuple[str, Path]] = []
    visiting: set[str] = set()
    completed: set[str] = set()

    def visit(name: str, requirements: tuple[str, ...]) -> None:
        """Traverse one package's local requirements while detecting cycles."""
        if name in completed:
            return
        if name in visiting:
            raise ValueError(f"Local workspace dependency cycle includes {name}")
        visiting.add(name)
        for requirement in requirements:
            dependency = requirement_name(requirement)
            if dependency is None:
                raise ValueError(f"Invalid dependency declaration: {requirement!r}")
            if dependency in workspace:
                path, child_requirements = workspace[dependency]
                visit(dependency, child_requirements)
                if dependency != app_name:
                    result.append((dependency, path))
        visiting.remove(name)
        completed.add(name)

    visit(app_name, app_dependencies)
    return list(dict.fromkeys(result))


def dependants(repo_root: Path, target: Path, name: str) -> list[Path]:
    """Return repository Python projects that depend on the target distribution."""
    result: list[Path] = []
    expected_name = _utils.normalise_name(name)
    manifests = [
        *repo_root.glob("apps/*/pyproject.toml"),
        *repo_root.glob("libs/*/pyproject.toml"),
    ]
    for manifest in sorted(manifests):
        if manifest.parent == target:
            continue
        with manifest.open("rb") as file:
            data = tomllib.load(file)
        project = data.get("project")
        dependencies = project.get("dependencies", []) if isinstance(project, dict) else []
        if isinstance(dependencies, list) and any(
            isinstance(dependency, str) and requirement_name(dependency) == expected_name
            for dependency in dependencies
        ):
            result.append(manifest.parent.relative_to(repo_root))
    return result


def remove_from_root_project(repo_root: Path, library_path: str, name: str) -> None:
    """Remove a library from root dependencies, uv workspace members, and sources."""
    manifest = repo_root / "pyproject.toml"
    document = tomlkit.parse(manifest.read_text())
    project = document.get("project")
    dependencies = project.get("dependencies") if isinstance(project, Table) else None
    expected_name = _utils.normalise_name(name)
    changed = False
    if isinstance(dependencies, Array):
        for dependency in list(dependencies):
            if requirement_name(str(dependency)) == expected_name:
                dependencies.remove(dependency)
                changed = True
    workspace = document.get("tool", {}).get("uv", {}).get("workspace", {})
    members = workspace.get("members") if isinstance(workspace, Table) else None
    if isinstance(members, Array) and library_path in {str(member) for member in members}:
        members.remove(library_path)
        changed = True
    sources = document.get("tool", {}).get("uv", {}).get("sources", {})
    if isinstance(sources, Table):
        for source_name in list(sources):
            if _utils.normalise_name(str(source_name)) == expected_name:
                del sources[source_name]
                changed = True
    if changed:
        manifest.write_text(tomlkit.dumps(document))
