"""Tests for shared application-management behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_tooling import _apps, _config, _utils


def test_choose_application_reprompts_until_selection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reprompt until an application number identifies an available app."""
    selections = iter(["invalid", "3", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(selections))

    assert (
        _apps.choose_application(
            ["alpha", "bravo"], "Select an application:", lambda application: application
        )
        == "bravo"
    )
    assert capsys.readouterr().err == "Invalid selection: invalid\nInvalid selection: 3\n"


def test_choose_application_handles_eof(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Return no selection and report an error when input reaches EOF."""
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError))

    assert _apps.choose_application(["alpha"], "Select an application:", str) is None
    assert capsys.readouterr().err == "Error: no application was selected.\n"


def test_choose_application_returns_none_when_user_quits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treat the explicit quit choice as no application selection."""
    monkeypatch.setattr("builtins.input", lambda _: "q")

    assert _apps.choose_application(["alpha"], "Choose:", str) is None


def test_docker_applications_discovers_supported_and_unrecognised_apps(tmp_path: Path) -> None:
    """Discover Docker apps and identify their language when possible."""
    python_application = tmp_path / "apps" / "alpha"
    python_application.mkdir(parents=True)
    (python_application / "Dockerfile").write_text("")
    (python_application / "pyproject.toml").write_text("")
    rust_application = tmp_path / "apps" / "bravo"
    rust_application.mkdir()
    (rust_application / "Dockerfile").write_text("")
    (rust_application / "Cargo.toml").write_text("")
    unrecognised_application = tmp_path / "apps" / "container"
    unrecognised_application.mkdir()
    (unrecognised_application / "Dockerfile").write_text("")
    (tmp_path / "apps" / "not-an-app").mkdir()
    (tmp_path / "apps" / "linked").symlink_to(python_application)

    assert [
        (application.name, application.dockerfile, application.language)
        for application in _apps.docker_applications(tmp_path / "apps")
    ] == [
        ("alpha", python_application / "Dockerfile", "python"),
        ("bravo", rust_application / "Dockerfile", "rust"),
        ("container", unrecognised_application / "Dockerfile", None),
    ]


def test_docker_applications_returns_empty_when_root_is_missing(tmp_path: Path) -> None:
    """Return no Docker apps when the applications directory is absent."""
    assert _apps.docker_applications(tmp_path / "missing") == []


def test_docker_available_checks_docker_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirm Docker availability by running its version command."""
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(_apps.subprocess, "run", run)

    assert _apps.docker_available()
    assert calls == [["docker", "version"]]


def test_docker_available_reports_a_missing_executable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report that Docker is unavailable when it is absent from PATH."""
    monkeypatch.setattr(_apps.shutil, "which", lambda _: None)

    assert not _apps.docker_available()
    assert "docker is required but was not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error", [OSError("not executable"), subprocess.CalledProcessError(1, ["docker"])]
)
def test_docker_available_reports_an_unusable_daemon(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    """Report daemon failures when the Docker version command cannot run."""
    monkeypatch.setattr(_apps.shutil, "which", lambda _: "/usr/bin/docker")

    def fail_run(*_: object, **__: object) -> None:
        raise error

    monkeypatch.setattr(_apps.subprocess, "run", fail_run)

    assert not _apps.docker_available()
    assert "Docker is unavailable" in capsys.readouterr().err


def test_applications_returns_sorted_real_directories(tmp_path: Path) -> None:
    """List direct app directories in order while skipping files and symlinks."""
    apps_root = tmp_path / "apps"
    (apps_root / "zebra").mkdir(parents=True)
    (apps_root / "alpha").mkdir()
    (apps_root / "not-a-directory").write_text("")
    (apps_root / "linked").symlink_to(apps_root / "alpha")

    assert _apps.applications(apps_root) == [apps_root / "alpha", apps_root / "zebra"]
    assert _apps.applications(tmp_path / "missing") == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [(" demo_app>=1.0 ", "demo-app"), ("", None), ("[extra]", None)],
)
def test_requirement_name_extracts_normalised_names(value: str, expected: str | None) -> None:
    """Extract and normalize a dependency name or return None if invalid."""
    assert _apps.requirement_name(value) == expected


def test_normalise_name() -> None:
    """Normalize application names through the shared utility."""
    assert _utils.normalise_name("Demo_App.Name") == "demo-app-name"


def test_remove_application_updates_workspace_and_deletes_directory(tmp_path: Path) -> None:
    """Remove workspace references before deleting the application directory."""
    root_manifest = tmp_path / "pyproject.toml"
    root_manifest.write_text(
        '[project]\ndependencies = ["demo-app"]\n'
        '[tool.uv.workspace]\nmembers = ["apps/demo"]\n'
        "[tool.uv.sources]\ndemo-app = { workspace = true }\n"
    )
    application = tmp_path / "apps" / "demo"
    application.mkdir(parents=True)
    (application / "pyproject.toml").write_text('[project]\nname = "demo-app"\n')
    (tmp_path / "release.env").write_text('RELEASE_CLI_APPS="apps/demo"\n')

    assert _apps.remove_application(tmp_path, application) == 0
    assert not application.exists()
    assert "apps/demo" not in root_manifest.read_text()


def test_remove_from_workspaces_removes_python_entries(tmp_path: Path) -> None:
    """Remove the app's dependency, workspace membership, and source entry."""
    root_manifest = tmp_path / "pyproject.toml"
    root_manifest.write_text(
        '[project]\ndependencies = ["demo_app>=1.0", "other"]\n'
        '[tool.uv.workspace]\nmembers = ["apps/demo", "apps/other"]\n'
        "[tool.uv.sources]\ndemo-app = { workspace = true }\n"
        "other = { workspace = true }\n"
    )
    app = tmp_path / "apps" / "demo"
    app.mkdir(parents=True)
    (app / "pyproject.toml").write_text('[project]\nname = "demo-app"\n')

    _apps.remove_from_workspaces(tmp_path, app, "apps/demo")

    remaining = root_manifest.read_text()
    assert "demo_app" not in remaining
    assert '"apps/demo"' not in remaining
    assert "other" in remaining


def test_remove_from_workspaces_removes_rust_member(tmp_path: Path) -> None:
    """Remove an application from the Cargo workspace members."""
    workspace_manifest = tmp_path / "Cargo.toml"
    workspace_manifest.write_text('[workspace]\nmembers = ["apps/demo", "apps/other"]\n')

    _apps.remove_from_workspaces(tmp_path, tmp_path / "apps/demo", "apps/demo")

    assert '"apps/demo"' not in workspace_manifest.read_text()
    assert '"apps/other"' in workspace_manifest.read_text()


def test_remove_from_workspaces_does_not_rewrite_unchanged_manifests(tmp_path: Path) -> None:
    """Leave the Python workspace manifest unchanged when no entries match."""
    root_manifest = tmp_path / "pyproject.toml"
    root_manifest.write_text('[project]\ndependencies = ["other"]\n')
    app = tmp_path / "apps" / "demo"
    app.mkdir(parents=True)
    (app / "pyproject.toml").write_text('[project]\nname = "demo-app"\n')
    original = root_manifest.read_text()

    _apps.remove_from_workspaces(tmp_path, app, "apps/demo")

    assert root_manifest.read_text() == original


def test_remove_from_workspaces_skips_missing_python_dependency_array(tmp_path: Path) -> None:
    """Leave a root manifest unchanged when it has no project dependencies."""
    root_manifest = tmp_path / "pyproject.toml"
    root_manifest.write_text("[tool.uv]\n")
    app = tmp_path / "apps" / "demo"
    app.mkdir(parents=True)
    (app / "pyproject.toml").write_text('[project]\nname = "demo-app"\n')
    original = root_manifest.read_text()

    _apps.remove_from_workspaces(tmp_path, app, "apps/demo")

    assert root_manifest.read_text() == original


def test_remove_from_workspaces_leaves_nonmember_cargo_workspace_unchanged(
    tmp_path: Path,
) -> None:
    """Leave a Cargo workspace unchanged when the app is not one of its members."""
    workspace_manifest = tmp_path / "Cargo.toml"
    workspace_manifest.write_text('[workspace]\nmembers = ["apps/other"]\n')

    _apps.remove_from_workspaces(tmp_path, tmp_path / "apps/demo", "apps/demo")

    assert workspace_manifest.read_text() == '[workspace]\nmembers = ["apps/other"]\n'


def test_libraries_discovers_python_and_rust_projects(tmp_path: Path) -> None:
    """List supported Python and Rust libraries while skipping invalid entries."""
    libs_root = tmp_path / "libs"
    python_library = libs_root / "alpha"
    python_library.mkdir(parents=True)
    (python_library / "pyproject.toml").write_text("")
    rust_library = libs_root / "bravo"
    rust_library.mkdir()
    (rust_library / "Cargo.toml").write_text("")
    (libs_root / "empty").mkdir()
    (libs_root / "not-a-directory").write_text("")

    assert _apps.libraries(libs_root) == [
        _apps.Library("alpha", "python"),
        _apps.Library("bravo", "rust"),
    ]
    assert _apps.libraries(tmp_path / "missing") == []


def test_print_no_libraries_error_only_suggests_creation_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Script presence is unconditional; command availability comes from configuration."""
    monkeypatch.setattr(_config, "DEVELOPMENT_APPROACH", "application_only_development")
    _apps.print_no_libraries_error(tmp_path)
    assert "make create-library" not in capsys.readouterr().err

    monkeypatch.setattr(_config, "DEVELOPMENT_APPROACH", "application_and_library_development")
    _apps.print_no_libraries_error(tmp_path)
    assert "make create-library" in capsys.readouterr().err


@pytest.mark.parametrize(("selection", "expected"), [("2", "service-app"), ("q", None)])
def test_choose_app_kind(
    selection: str, expected: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return the selected app kind or None when the user quits."""
    monkeypatch.setattr("builtins.input", lambda _: selection)

    assert _apps.choose_app_kind() == expected


def test_choose_app_kind_retries_invalid_selection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reprompt after an invalid app-kind selection."""
    selections = iter(["invalid", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(selections))

    assert _apps.choose_app_kind() == "local-app"
    assert "Invalid selection: invalid" in capsys.readouterr().err


def test_choose_app_kind_retries_out_of_range_number(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reprompt after an app-kind selection outside the available choices."""
    selections = iter(["3", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(selections))

    assert _apps.choose_app_kind() == "local-app"
    assert "Invalid selection: 3" in capsys.readouterr().err


def test_choose_library_retries_and_quits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reprompt for a valid library choice and support quitting."""
    libraries = [_apps.Library("demo", "python")]
    selections = iter(["0", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(selections))
    assert _apps.choose_library(libraries) == libraries[0]

    monkeypatch.setattr("builtins.input", lambda _: "q")
    assert _apps.choose_library(libraries) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("--My Library__", "my_library"), ("!!!", "")],
)
def test_to_snake_case(value: str, expected: str) -> None:
    """Convert labels to snake case and handle names without alphanumeric chars."""
    assert _apps.to_snake_case(value) == expected


def test_prompt_snake_case_name_uses_default_and_rejects_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the default name for empty input and reject unusable names."""
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert _apps.prompt_snake_case_name("Name", "default_name") == "default_name"
    monkeypatch.setattr("builtins.input", lambda _: "!!!")
    with pytest.raises(ValueError, match="application name"):
        _apps.prompt_snake_case_name("Name", "default_name")


def test_local_application_name_rejects_unusable_library_name() -> None:
    """Reject a library name that cannot produce an app-name default."""
    with pytest.raises(ValueError, match="wrapped library name"):
        _apps.local_application_name("!!!")


def test_local_application_name_uses_normalised_library_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build the default app name from a normalized library name."""
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert _apps.local_application_name("Demo-Library") == "demo_library_app"


def test_service_application_name_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the default service-app name when the prompt is left blank."""
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert _apps.service_application_name() == "service_app"


def test_ensure_available_app_directory_rejects_existing_paths(tmp_path: Path) -> None:
    """Accept a new app path and reject existing directories or symlinks."""
    apps = tmp_path / "apps"
    apps.mkdir()
    assert _apps.ensure_available_app_directory(tmp_path, "demo") == apps / "demo"
    (apps / "existing").mkdir()
    with pytest.raises(ValueError, match="already exists"):
        _apps.ensure_available_app_directory(tmp_path, "existing")
    (apps / "linked").symlink_to(apps / "existing")
    with pytest.raises(ValueError, match="already exists"):
        _apps.ensure_available_app_directory(tmp_path, "linked")


def test_run_copier_runs_the_command_with_failure_checking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run Copier through subprocess with check enabled."""
    calls: list[tuple[list[str], bool]] = []

    def run(command: list[str], *, check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr(_apps.subprocess, "run", run)

    _apps.run_copier(["copier", "copy"])

    assert calls == [(["copier", "copy"], True)]


@pytest.mark.parametrize("newline", ["\n", "\r\n", ""])
def test_add_release_target_is_idempotent_and_preserves_line_ending(
    tmp_path: Path, newline: str
) -> None:
    """Add a release target once while preserving the file's line ending."""
    release_environment = tmp_path / "release.env"
    release_environment.write_bytes(f'RELEASE_CLI_APPS="apps/demo"{newline}'.encode())

    _apps.add_release_target(release_environment, "RELEASE_CLI_APPS", "apps/demo")
    _apps.add_release_target(release_environment, "RELEASE_CLI_APPS", "apps/other")

    assert release_environment.read_bytes() == (
        f'RELEASE_CLI_APPS="apps/demo apps/other"{newline}'.encode()
    )


def test_release_target_helpers_reject_missing_configuration(tmp_path: Path) -> None:
    """Report missing release files and a missing required variable."""
    release_environment = tmp_path / "release.env"
    with pytest.raises(ValueError, match="Missing release configuration"):
        _apps.add_release_target(release_environment, "RELEASE_CLI_APPS", "apps/demo")
    with pytest.raises(ValueError, match="Missing release configuration"):
        _apps.remove_release_target(release_environment, "RELEASE_CLI_APPS", "apps/demo")

    release_environment.write_text("OTHER=value\n")
    with pytest.raises(ValueError, match="Missing RELEASE_CLI_APPS"):
        _apps.add_release_target(release_environment, "RELEASE_CLI_APPS", "apps/demo")


def test_remove_release_target_preserves_unrelated_entries(tmp_path: Path) -> None:
    """Remove only the selected app path from the release target list."""
    release_environment = tmp_path / "release.env"
    release_environment.write_text('RELEASE_CLI_APPS="apps/demo apps/other"\n')

    _apps.remove_release_target(release_environment, "RELEASE_CLI_APPS", "apps/demo")

    assert release_environment.read_text() == 'RELEASE_CLI_APPS="apps/other"\n'


def test_remove_release_target_skips_other_lines_and_ignores_missing_target(
    tmp_path: Path,
) -> None:
    """Skip unrelated settings and leave an unmatched release target unchanged."""
    release_environment = tmp_path / "release.env"
    release_environment.write_text('OTHER=value\nRELEASE_CLI_APPS="apps/other"\n')

    _apps.remove_release_target(release_environment, "RELEASE_CLI_APPS", "apps/missing")

    assert release_environment.read_text() == 'OTHER=value\nRELEASE_CLI_APPS="apps/other"\n'


def test_remove_release_target_ignores_a_missing_variable(tmp_path: Path) -> None:
    """Leave release settings unchanged when the target variable is absent."""
    release_environment = tmp_path / "release.env"
    release_environment.write_text("OTHER=value\n")

    _apps.remove_release_target(release_environment, "RELEASE_CLI_APPS", "apps/demo")

    assert release_environment.read_text() == "OTHER=value\n"


def test_create_local_app_returns_success_when_user_quits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Treat a user's choice to quit local-app creation as successful."""
    monkeypatch.setattr(_apps, "libraries", lambda _: [_apps.Library("demo", "python")])
    monkeypatch.setattr(_apps, "choose_library", lambda _: None)

    assert _apps.create_local_app(tmp_path) == 0


def test_create_local_app_reports_no_matching_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report when no discovered library matches the requested language."""
    monkeypatch.setattr(_apps, "libraries", lambda _: [_apps.Library("demo", "python")])

    assert _apps.create_local_app(tmp_path, "rust") == 1
    assert "No Python or Rust libraries found" in capsys.readouterr().err


@pytest.mark.parametrize("vcs_ref", [None, "", "app-branch"])
def test_python_application_creation_adds_workspace_member(
    vcs_ref: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create a Python local app and register it with the uv workspace."""
    monkeypatch.setenv("VCS_REF", "legacy-ref")
    monkeypatch.setenv("VCS_REF_REPO_TEMPLATE", "repo-ref")
    monkeypatch.setenv("VCS_REF_LIB_TEMPLATE", "lib-ref")
    monkeypatch.setenv("VCS_REF_COMPOSE_TEMPLATE", "compose-ref")
    if vcs_ref is not None:
        monkeypatch.setenv("VCS_REF_APP_TEMPLATE", vcs_ref)
    library = _apps.Library("demo_library", "python")
    monkeypatch.setattr(_apps, "libraries", lambda _: [library])
    monkeypatch.setattr(_apps, "choose_library", lambda _: library)
    monkeypatch.setattr(_apps, "local_application_name", lambda _: "demo_app")
    commands: list[list[str]] = []
    monkeypatch.setattr(_apps, "run_copier", lambda command: commands.append(command))
    (tmp_path / "release.env").write_text('RELEASE_CLI_APPS=""\n')
    calls: list[tuple[list[str], Path, bool]] = []

    def run(command: list[str], *, cwd: Path, check: bool) -> None:
        calls.append((command, cwd, check))

    monkeypatch.setattr(_apps.subprocess, "run", run)

    assert _apps.create_local_app(tmp_path, "python") == 0
    assert commands[0][5 : commands[0].index("--data")] == (
        ["--vcs-ref", vcs_ref] if vcs_ref else []
    )
    assert calls == [(["uv", "add", "--workspace", "apps/demo_app"], tmp_path, True)]


def test_python_application_creation_reports_workspace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Return the uv error code and report a workspace-registration failure."""
    library = _apps.Library("demo_library", "python")
    monkeypatch.setattr(_apps, "libraries", lambda _: [library])
    monkeypatch.setattr(_apps, "choose_library", lambda _: library)
    monkeypatch.setattr(_apps, "local_application_name", lambda _: "demo_app")
    monkeypatch.setattr(_apps, "run_copier", lambda _: None)
    monkeypatch.setattr(
        _apps.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(7, args[0])),
    )

    assert _apps.create_local_app(tmp_path, "python") == 7
    assert "Application creation failed" in capsys.readouterr().err


def test_local_application_creation_reports_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report invalid app-name input before creating an application."""
    library = _apps.Library("demo_library", "python")
    monkeypatch.setattr(_apps, "libraries", lambda _: [library])
    monkeypatch.setattr(_apps, "choose_library", lambda _: library)
    monkeypatch.setattr(
        _apps, "local_application_name", lambda _: (_ for _ in ()).throw(ValueError("bad name"))
    )

    assert _apps.create_local_app(tmp_path) == 2
    assert "Error: bad name" in capsys.readouterr().err


@pytest.mark.parametrize("vcs_ref", [None, "", "app-branch"])
def test_service_application_creation_uses_copier(
    vcs_ref: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass the service app kind, name, and path to Copier."""
    monkeypatch.setenv("VCS_REF", "legacy-ref")
    monkeypatch.setenv("VCS_REF_REPO_TEMPLATE", "repo-ref")
    monkeypatch.setenv("VCS_REF_LIB_TEMPLATE", "lib-ref")
    monkeypatch.setenv("VCS_REF_COMPOSE_TEMPLATE", "compose-ref")
    if vcs_ref is not None:
        monkeypatch.setenv("VCS_REF_APP_TEMPLATE", vcs_ref)
    monkeypatch.setattr(_apps, "service_application_name", lambda: "service_app")
    commands: list[list[str]] = []
    monkeypatch.setattr(_apps, "run_copier", lambda command: commands.append(command))

    assert _apps.create_service_app(tmp_path) == 0
    assert commands[0][5 : commands[0].index("--data")] == (
        ["--vcs-ref", vcs_ref] if vcs_ref else []
    )
    assert commands[0][commands[0].index("--data") :] == [
        "--data",
        "app_kind=service-app",
        "--data",
        "app_name=service_app",
        "--data",
        "programming_language=python",
        _config.COPIER_APP_TEMPLATE_URL,
        str(tmp_path / "apps" / "service_app"),
    ]
    assert (tmp_path / "apps" / "service_app").parent.is_dir()


def test_service_application_creation_reports_validation_and_copier_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report service-app validation errors and Copier failures."""
    monkeypatch.setattr(
        _apps,
        "service_application_name",
        lambda: (_ for _ in ()).throw(ValueError("bad service name")),
    )
    assert _apps.create_service_app(tmp_path) == 2
    assert "Error: bad service name" in capsys.readouterr().err

    monkeypatch.setattr(_apps, "service_application_name", lambda: "service_app")
    monkeypatch.setattr(
        _apps,
        "run_copier",
        lambda _: (_ for _ in ()).throw(subprocess.CalledProcessError(9, ["copier"])),
    )
    assert _apps.create_service_app(tmp_path) == 9
    assert "Service app creation failed" in capsys.readouterr().err


def test_remove_application_rejects_paths_outside_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse to remove an application directory outside the repository."""
    outside_application = tmp_path.parent / "outside-app"
    outside_application.mkdir()

    assert _apps.remove_application(tmp_path, outside_application) == 1
    assert outside_application.is_dir()
    assert "Application removal failed" in capsys.readouterr().err


def test_rust_application_creation_registers_with_cargo_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create a Rust local app and register it with the Cargo workspace."""
    library = _apps.Library("demo_library", "rust")
    monkeypatch.setattr(_apps, "libraries", lambda _: [library])
    monkeypatch.setattr(_apps, "choose_library", lambda _: library)
    monkeypatch.setattr(_apps, "local_application_name", lambda _: "demo_app")
    monkeypatch.setattr(_apps, "run_copier", lambda _: None)
    (tmp_path / "release.env").write_text('RELEASE_CLI_APPS=""\n')
    calls: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        _apps._cargo,
        "add_workspace_member",
        lambda root, path: calls.append((root, path)),
    )

    assert _apps.create_local_app(tmp_path, "rust") == 0
    assert calls == [(tmp_path, "apps/demo_app")]
