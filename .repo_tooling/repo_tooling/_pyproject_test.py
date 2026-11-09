"""Tests for pyproject.toml management helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_tooling import _pyproject


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        ("demo-library>=1.0", "demo-library"),
        ("  demo_library[cli]", "demo-library"),
        ("", None),
    ],
)
def test_requirement_name_extracts_and_normalises_distribution_names(
    requirement: str, expected: str | None
) -> None:
    """Extract the distribution name from supported requirement strings."""
    assert _pyproject.requirement_name(requirement) == expected


def test_project_name_reads_the_project_name(tmp_path: Path) -> None:
    """Read a project name from a valid pyproject.toml file."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname = "demo-library"\nversion = "0.1.0"\n')

    assert _pyproject.project_name(manifest) == "demo-library"


def test_project_name_rejects_a_file_without_a_project_name(tmp_path: Path) -> None:
    """Reject a pyproject.toml file that does not define project.name."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nversion = "0.1.0"\n')

    with pytest.raises(TypeError, match=r"no \[project\]\.name"):
        _pyproject.project_name(manifest)


def test_read_toml_loads_a_document(tmp_path: Path) -> None:
    """Load TOML data with the shared manifest reader."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname = "demo"\n')

    assert _pyproject.read_toml(manifest) == {"project": {"name": "demo"}}


def test_mapping_rejects_non_mappings() -> None:
    """Reject invalid nested TOML configuration values."""
    with pytest.raises(ValueError, match=r"Missing or invalid \[tool\] configuration"):
        _pyproject.mapping([], "[tool]")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"project": {"dependencies": ["demo>=1.0"]}}, ("demo>=1.0",)),
        ({"project": {}}, ()),
    ],
)
def test_dependencies_validates_project_dependency_declarations(
    data: dict[str, object], expected: tuple[str, ...]
) -> None:
    """Return valid project dependencies and accept their absence."""
    assert _pyproject.dependencies(data) == expected


def test_dependencies_rejects_non_string_declarations() -> None:
    """Reject project dependencies that are not strings."""
    with pytest.raises(ValueError, match="project.dependencies must be a list of strings"):
        _pyproject.dependencies({"project": {"dependencies": ["demo", 1]}})


def test_packages_indexes_workspace_packages(tmp_path: Path) -> None:
    """Index package paths and dependencies from uv workspace members."""
    (tmp_path / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["libs/*"]\n')
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    (library / "pyproject.toml").write_text(
        '[project]\nname = "demo_library"\ndependencies = ["other>=1.0"]\n'
    )

    assert _pyproject.packages(tmp_path) == {"demo-library": (library.resolve(), ("other>=1.0",))}


def test_packages_rejects_duplicate_normalised_names(tmp_path: Path) -> None:
    """Reject workspace packages whose names normalise to the same value."""
    (tmp_path / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["libs/*"]\n')
    for directory_name, name in (("one", "demo_library"), ("two", "demo-library")):
        library = tmp_path / "libs" / directory_name
        library.mkdir(parents=True)
        (library / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n')

    with pytest.raises(ValueError, match="Workspace contains duplicate package name: demo-library"):
        _pyproject.packages(tmp_path)


@pytest.mark.parametrize("members", ["", 'members = "libs/*"', 'members = ["libs/*", 1]'])
def test_packages_rejects_invalid_workspace_members(tmp_path: Path, members: str) -> None:
    (tmp_path / "pyproject.toml").write_text(f"[tool.uv.workspace]\n{members}\n")

    with pytest.raises(
        ValueError, match=r"\[tool.uv.workspace\].members must be a list of strings"
    ):
        _pyproject.packages(tmp_path)


@pytest.mark.parametrize(
    "invalid_project",
    [None, "", "project = 42\n", '[project]\nversion = "0.1.0"\n', "[project]\nname = 42\n"],
)
def test_packages_skips_members_without_named_projects(
    tmp_path: Path, invalid_project: str | None
) -> None:
    """Ignore non-package directories without losing valid workspace packages."""
    (tmp_path / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["libs/*"]\n')
    invalid = tmp_path / "libs" / "invalid"
    invalid.mkdir(parents=True)
    if invalid_project is not None:
        (invalid / "pyproject.toml").write_text(invalid_project)
    valid = tmp_path / "libs" / "valid"
    valid.mkdir()
    (valid / "pyproject.toml").write_text('[project]\nname = "valid"\n')

    assert _pyproject.packages(tmp_path) == {"valid": (valid.resolve(), ())}


def test_local_dependencies_deduplicates_shared_transitive_dependencies(tmp_path: Path) -> None:
    """A diamond-shaped graph installs its shared dependency once, before either parent."""
    shared = tmp_path / "shared"
    left = tmp_path / "left"
    right = tmp_path / "right"
    workspace = {
        "shared": (shared, ()),
        "left": (left, ("shared>=1.0",)),
        "right": (right, ("shared>=1.0",)),
    }

    assert _pyproject.local_dependencies("app", ("left", "right", "shared"), workspace) == [
        ("shared", shared),
        ("left", left),
        ("right", right),
    ]


def test_local_dependencies_returns_transitive_dependencies_in_order(tmp_path: Path) -> None:
    """Return child packages before their dependants for installation."""
    dependency = tmp_path / "libs" / "dependency"
    intermediate = tmp_path / "libs" / "intermediate"
    workspace = {
        "intermediate": (intermediate, ("dependency>=1.0",)),
        "dependency": (dependency, ()),
    }

    assert _pyproject.local_dependencies("app", ("intermediate>=1.0",), workspace) == [
        ("dependency", dependency),
        ("intermediate", intermediate),
    ]


@pytest.mark.parametrize(
    ("dependencies", "workspace", "message"),
    [
        (("!invalid",), {}, "Invalid dependency declaration"),
        (
            ("first",),
            {
                "first": (Path("first"), ("second",)),
                "second": (Path("second"), ("first",)),
            },
            "Local workspace dependency cycle includes first",
        ),
    ],
)
def test_local_dependencies_rejects_invalid_graphs(
    dependencies: tuple[str, ...],
    workspace: dict[str, tuple[Path, tuple[str, ...]]],
    message: str,
) -> None:
    """Reject malformed requirements and cycles in local dependency graphs."""
    with pytest.raises(ValueError, match=message):
        _pyproject.local_dependencies("app", dependencies, workspace)


def test_dependants_finds_apps_and_libraries_that_use_a_project(tmp_path: Path) -> None:
    """Find dependants across repository application and library directories."""
    target = tmp_path / "libs" / "target"
    target.mkdir(parents=True)
    (target / "pyproject.toml").write_text('[project]\nname = "target-library"\n')
    application = tmp_path / "apps" / "client"
    application.mkdir(parents=True)
    (application / "pyproject.toml").write_text(
        '[project]\ndependencies = ["target_library>=1.0"]\n'
    )
    library = tmp_path / "libs" / "helper"
    library.mkdir(parents=True)
    (library / "pyproject.toml").write_text('[project]\ndependencies = ["other-library>=1.0"]\n')

    assert _pyproject.dependants(tmp_path, target, "target-library") == [Path("apps/client")]


def test_remove_from_root_project_removes_all_library_entries(tmp_path: Path) -> None:
    """Remove matching root dependencies, workspace membership, and source data."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\ndependencies = ["demo-library>=1.0", "other-library"]\n'
        '[tool.uv.workspace]\nmembers = ["libs/demo", "libs/other"]\n'
        "[tool.uv.sources]\n"
        "demo_library = { workspace = true }\n"
        "other-library = { workspace = true }\n"
    )

    _pyproject.remove_from_root_project(tmp_path, "libs/demo", "demo-library")
    after_removal = manifest.read_text()
    _pyproject.remove_from_root_project(tmp_path, "libs/demo", "demo-library")

    assert "demo-library" not in after_removal
    assert "demo_library" not in after_removal
    assert '"libs/demo"' not in after_removal
    assert "other-library" in after_removal
    assert manifest.read_text() == after_removal
