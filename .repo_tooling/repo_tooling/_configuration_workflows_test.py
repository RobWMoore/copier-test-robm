"""Tests for configuration checks at workflow boundaries."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from repo_tooling import (
    _apps,
    _config,
    _copier,
    _docker,
    _libs,
    _utils,
)
from repo_tooling.make_scripts import (
    make_build_release_cli,
    make_build_release_docker_compose,
    make_bump_version,
    make_copier_update_apps,
    make_copier_update_docker_compose,
    make_copier_update_libs,
    make_copier_update_repo,
    make_create_library,
    make_docker_app,
    make_docker_compose,
    make_remove_application,
    make_remove_library,
)


@pytest.mark.parametrize(
    ("module", "arguments", "setting", "value", "feature"),
    [
        (
            make_create_library,
            ["demo"],
            "DEVELOPMENT_APPROACH",
            "application_only_development",
            "libraries",
        ),
        (
            make_remove_library,
            [],
            "DEVELOPMENT_APPROACH",
            "application_only_development",
            "libraries",
        ),
        (
            make_copier_update_libs,
            [],
            "DEVELOPMENT_APPROACH",
            "application_only_development",
            "libraries",
        ),
        (make_docker_app, ["build"], "DOCKER_ENABLED", False, "docker"),
        (make_docker_compose, ["up"], "DOCKER_ENABLED", False, "docker"),
        (make_docker_compose, ["down"], "DOCKER_ENABLED", False, "docker"),
        (make_docker_compose, ["example"], "DOCKER_ENABLED", False, "docker"),
        (make_copier_update_docker_compose, [], "DOCKER_ENABLED", False, "docker"),
        (make_build_release_cli, ["v1.0.0"], "GITLAB_CI_ENABLED", False, "gitlab_ci"),
        (make_bump_version, ["patch"], "GITLAB_CI_ENABLED", False, "gitlab_ci"),
        (make_build_release_docker_compose, ["v1.0.0"], "GITLAB_CI_ENABLED", False, "gitlab_ci"),
        (make_build_release_docker_compose, ["v1.0.0"], "DOCKER_ENABLED", False, "docker"),
    ],
)
def test_disabled_feature_exits_before_prompts_tools_or_writes(
    module: ModuleType,
    arguments: list[str],
    setting: str,
    value: object,
    feature: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_config, setting, value)
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("sys.argv", [module.__name__, *arguments])
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("unexpected prompt")))
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError("unexpected command")))

    assert module.main() == 2
    assert capsys.readouterr().err == f"Error: feature not enabled: {feature}.\n"
    assert not list(tmp_path.iterdir())


def test_explicit_disabled_creation_language_does_not_run_copier(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python",))
    monkeypatch.setattr(make_create_library.shutil, "which", lambda _: "/uv")
    run = Mock()
    monkeypatch.setattr("subprocess.run", run)

    assert make_create_library.main(["demo", "--language", "rust"]) == 2
    assert capsys.readouterr().err == "Error: language not enabled: rust.\n"
    run.assert_not_called()


def test_single_enabled_creation_language_does_not_prompt_for_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python",))
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(make_create_library.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("unexpected prompt")))
    run = Mock()
    monkeypatch.setattr("subprocess.run", run)

    assert make_create_library.main(["demo"]) == 0
    assert "programming_language=python" in run.call_args_list[0].args[0]


def test_disabled_creation_language_is_reported_even_when_uv_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python",))
    monkeypatch.setattr(make_create_library.shutil, "which", lambda _: None)

    assert make_create_library.main(["demo", "--language=rust"]) == 2
    assert capsys.readouterr().err == "Error: language not enabled: rust.\n"


@pytest.mark.parametrize("kind", ["application", "library"])
def test_removal_keeps_disabled_language_component_visible_and_preserves_files(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = tmp_path / ("apps" if kind == "application" else "libs") / "rust_demo"
    directory.mkdir(parents=True)
    (directory / "Cargo.toml").write_text('[package]\nname="rust-demo"\nversion="0.1.0"\n')
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python",))
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("sys.argv", ["remove"])
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError("unexpected command")))
    if kind == "application":
        status = make_remove_application.main()
    else:
        status = make_remove_library.main()

    assert status == 2
    output = capsys.readouterr()
    assert "rust_demo" in output.out
    assert "language not enabled: rust" in output.err
    assert (directory / "Cargo.toml").is_file()


@pytest.mark.parametrize(
    ("module", "directory"),
    [(make_copier_update_apps, "apps"), (make_copier_update_libs, "libs")],
)
def test_copier_batch_reports_all_disabled_components_before_any_update(
    module: ModuleType,
    directory: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An enabled component sorted first must not be updated before a later rejection."""
    (tmp_path / ".copier-answers.yml").write_text("project_name: demo\n")
    for name, language in [("alpha", "python"), ("beta", "rust"), ("gamma", "rust")]:
        component = tmp_path / directory / name
        component.mkdir(parents=True)
        (component / ".copier-answers.yml").write_text(f"programming_language: {language}\n")
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python",))
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("sys.argv", ["update"])
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError("unexpected command")))

    assert module.main() == 2
    error = capsys.readouterr().err
    assert "language not enabled: rust" in error
    assert f"{directory}/beta" in error
    assert f"{directory}/gamma" in error


def test_service_component_does_not_require_python_application_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component = tmp_path / "apps" / "service"
    component.mkdir(parents=True)
    (component / ".copier-answers.yml").write_text(
        "app_kind: service-app\nprogramming_language: python\n"
    )
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())

    _copier.validate_components([component], tmp_path)


@pytest.mark.parametrize("language", ["python", "rust"])
def test_cli_release_rejects_disabled_language_before_creating_artifacts(
    language: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = tmp_path / "apps" / "demo"
    application.mkdir(parents=True)
    manifest = "pyproject.toml" if language == "python" else "Cargo.toml"
    (application / manifest).write_text("")
    (tmp_path / "release.env").write_text('RELEASE_CLI_APPS="apps/demo"\n')
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError("unexpected command")))

    assert make_build_release_cli.main(["v1.0.0"]) == 2
    assert f"language not enabled: {language}" in capsys.readouterr().err
    assert not (tmp_path / "dist").exists()


@pytest.mark.parametrize("action", ["build", "run", "example"])
def test_docker_workflow_rejects_selected_disabled_language(
    action: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = tmp_path / "apps" / "demo"
    application.mkdir(parents=True)
    (application / "Dockerfile").write_text("")
    (application / "Cargo.toml").write_text("")
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python",))
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(_apps, "docker_available", lambda: True)
    monkeypatch.setattr(make_docker_compose.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr("builtins.input", lambda _: "1")
    run = Mock()
    monkeypatch.setattr("subprocess.run", run)
    module = make_docker_compose if action == "example" else make_docker_app

    assert module.main([action]) == 2
    assert "language not enabled: rust" in capsys.readouterr().err
    run.assert_not_called()
    assert not (tmp_path / "docker-compose-scripts").exists()


def test_local_application_creation_only_offers_enabled_language_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, manifest in [("python_demo", "pyproject.toml"), ("rust_demo", "Cargo.toml")]:
        library = tmp_path / "libs" / name
        library.mkdir(parents=True)
        (library / manifest).write_text("")
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python",))
    choose = Mock(return_value=None)
    monkeypatch.setattr(_apps, "choose_library", choose)

    assert _apps.create_local_app(tmp_path) == 0
    choose.assert_called_once_with([_apps.Library("python_demo", "python")])


@pytest.mark.parametrize("language", [None, "rust"])
def test_local_application_creation_rejects_disabled_language_before_selection(
    language: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())
    choose = Mock()
    monkeypatch.setattr(_apps, "choose_library", choose)

    assert _apps.create_local_app(tmp_path, language) == 2
    assert "language not enabled:" in capsys.readouterr().err
    choose.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_service_application_removal_is_language_neutral_and_does_not_require_release_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = tmp_path / "apps" / "service"
    service.mkdir(parents=True)
    (service / ".copier-answers.yml").write_text(
        "app_kind: service-app\nprogramming_language: python\n"
    )
    (service / "pyproject.toml").write_text('[project]\nname="service"\n')
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())
    monkeypatch.setattr(_config, "GITLAB_CI_ENABLED", False)

    assert _apps.remove_application(tmp_path, service) == 0
    assert not service.exists()


def test_repository_copier_update_remains_available_with_all_features_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config, "DEVELOPMENT_APPROACH", "application_only_development")
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())
    monkeypatch.setattr(_config, "DOCKER_ENABLED", False)
    monkeypatch.setattr(_config, "GITLAB_CI_ENABLED", False)
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(_copier, "require_root_answers", Mock())
    monkeypatch.setattr(_copier, "abort_if_merge_conflicts", Mock())
    run = Mock()
    monkeypatch.setattr(_copier, "run_update", run)
    monkeypatch.setattr("sys.argv", ["update-repo"])

    assert make_copier_update_repo.main() == 0
    run.assert_called_once()


@pytest.mark.parametrize("languages", [(), ("python",), ("rust",), ("python", "rust")])
def test_language_configuration_and_build_arguments_are_evaluated_at_call_time(
    languages: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", languages)
    monkeypatch.setattr(_config, "PYTHON_VERSION", "3.12.9")
    monkeypatch.setattr(_config, "RUST_MSRV", "1.86.0")

    assert [config.language for config in _libs.configs(enabled_only=True)] == list(languages)
    assert _libs.configs()[0].version_data == "python_version=3.12.9"
    assert _libs.configs()[1].version_data == "rust_msrv=1.86.0"
    arguments = dict(_docker.build_argument_environment_variables())
    assert ("PYTHON_IMAGE" in arguments) == ("python" in languages)
    assert ("UV_VERSION" in arguments) == ("python" in languages)
    assert ("RUST_IMAGE" in arguments) == ("rust" in languages)
    assert ("RUST_RUNTIME_IMAGE" in arguments) == ("rust" in languages)


@pytest.mark.parametrize(
    ("module", "directory"),
    [(make_copier_update_apps, "apps"), (make_copier_update_libs, "libs")],
)
def test_copier_batch_updates_every_enabled_component_after_preflight(
    module: ModuleType, directory: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".copier-answers.yml").write_text("project_name: demo\n")
    for name, language in [("alpha", "python"), ("beta", "rust")]:
        component = tmp_path / directory / name
        component.mkdir(parents=True)
        (component / ".copier-answers.yml").write_text(f"programming_language: {language}\n")
    monkeypatch.setattr(_utils, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(_copier, "abort_if_merge_conflicts", Mock())
    run = Mock()
    monkeypatch.setattr(_copier, "run_update", run)
    monkeypatch.setattr("sys.argv", ["update"])

    assert module.main() == 0
    assert [call.args[0][-1] for call in run.call_args_list] == [
        str(tmp_path / directory / name) for name in ("alpha", "beta")
    ]


def test_service_update_does_not_pass_an_application_python_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = tmp_path / "apps" / "service"
    service.mkdir(parents=True)
    (service / ".copier-answers.yml").write_text(
        "app_kind: service-app\nprogramming_language: python\n"
    )
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())
    run = Mock()
    monkeypatch.setattr(_copier, "run_update", run)

    _copier.update_application(service, tmp_path, None)
    command = run.call_args.args[0]
    assert not any(argument.startswith("python_version=") for argument in command)


def test_application_creation_passes_docker_settings_without_editing_disabled_release_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    (library / "pyproject.toml").write_text("")
    monkeypatch.setattr(_config, "GITLAB_CI_ENABLED", False)
    monkeypatch.setattr(_config, "DOCKER_ENABLED", False)
    monkeypatch.setattr(_apps, "choose_library", lambda _: _apps.Library("demo", "python"))
    monkeypatch.setattr(_apps, "local_application_name", lambda _: "demo_app")
    copy = Mock()
    monkeypatch.setattr(_apps, "run_copier", copy)
    release = Mock()
    monkeypatch.setattr(_apps, "add_release_target", release)
    monkeypatch.setattr("subprocess.run", Mock())

    assert _apps.create_local_app(tmp_path) == 0
    assert "allow_docker=false" in copy.call_args.args[0]
    release.assert_not_called()
    assert not (tmp_path / "release.env").exists()


def test_library_creation_without_enabled_languages_exits_before_prompting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())
    monkeypatch.setattr(make_create_library.shutil, "which", lambda _: "/uv")
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("unexpected prompt")))

    assert make_create_library.main(["demo"]) == 2
    assert "language not enabled:" in capsys.readouterr().err
