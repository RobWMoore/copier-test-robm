"""Tests for shared library-management behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_tooling import _config, _libs


def test_to_snake_case() -> None:
    """Convert a library display name to snake case."""
    assert _libs.to_snake_case("My Library") == "my_library"


def test_to_snake_case_strips_edges_and_returns_empty_for_punctuation() -> None:
    """Strip edge separators and return an empty name for punctuation only."""
    assert _libs.to_snake_case("__My Library__") == "my_library"
    assert _libs.to_snake_case("!!!") == ""


def test_library_config_factories_define_python_and_rust_values() -> None:
    """Build the expected manifest and version settings for each language."""
    python = _libs.LibraryConfig.python("3.14.0")
    rust = _libs.LibraryConfig.rust("1.85.0")

    assert (python.language, python.version_data, python.manifest_name) == (
        "python",
        "python_version=3.14.0",
        "pyproject.toml",
    )
    assert (rust.language, rust.version_data, rust.manifest_name) == (
        "rust",
        "rust_msrv=1.85.0",
        "Cargo.toml",
    )


def test_choose_config_rejects_empty_language_options_before_prompting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("unexpected prompt"))
    with pytest.raises(_config.ConfigurationError, match="language not enabled"):
        _libs.choose_config([])


def test_choose_config_does_not_prompt_for_one_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return the sole language configuration without reading user input."""
    config = _libs.LibraryConfig.python("3.14.0")
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("input should not be called"))

    assert _libs.choose_config([config]) is config


def test_choose_config_prompts_for_a_language(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Select the numbered language configuration entered by the user."""
    configs = [
        _libs.LibraryConfig.python("3.14.0"),
        _libs.LibraryConfig.rust("1.85.0"),
    ]
    selections = iter(["invalid", "3", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(selections))

    assert _libs.choose_config(configs) is configs[1]
    captured = capsys.readouterr()
    assert captured.out == "Select a library language to create:\n1) Python\n2) Rust\n"
    assert captured.err == "Invalid selection: invalid\nInvalid selection: 3\n"


def test_library_config_selects_each_supported_manifest(tmp_path: Path) -> None:
    """Match Python and Rust libraries to their corresponding configs."""
    python = _libs.LibraryConfig.python("3.14.0")
    rust = _libs.LibraryConfig.rust("1.85.0")
    python_library = tmp_path / "python"
    python_library.mkdir()
    (python_library / python.manifest_name).write_text("")
    rust_library = tmp_path / "rust"
    rust_library.mkdir()
    (rust_library / rust.manifest_name).write_text("")

    assert _libs.library_config(python_library, [python, rust]) is python
    assert _libs.library_config(rust_library, [python, rust]) is rust


@pytest.mark.parametrize("manifests", [(), ("pyproject.toml", "Cargo.toml")])
def test_library_config_rejects_missing_or_ambiguous_manifests(
    tmp_path: Path, manifests: tuple[str, ...]
) -> None:
    """Reject library directories with zero or multiple supported manifests."""
    library = tmp_path / "demo"
    library.mkdir()
    for manifest in manifests:
        (library / manifest).write_text("")
    configs = [
        _libs.LibraryConfig.python("3.14.0"),
        _libs.LibraryConfig.rust("1.85.0"),
    ]

    with pytest.raises(ValueError, match="exactly one supported manifest"):
        _libs.library_config(library, configs)


def test_libraries_discovers_sorted_valid_directories_and_skips_invalid_entries(
    tmp_path: Path,
) -> None:
    """Return sorted direct libraries and skip invalid entries and symlinks."""
    python = _libs.LibraryConfig.python("3.14.0")
    rust = _libs.LibraryConfig.rust("1.85.0")
    (tmp_path / "z-rust").mkdir()
    (tmp_path / "z-rust" / rust.manifest_name).write_text("")
    (tmp_path / "a-python").mkdir()
    (tmp_path / "a-python" / python.manifest_name).write_text("")
    (tmp_path / "empty").mkdir()
    (tmp_path / "not-a-directory").write_text("")
    linked_library = tmp_path / "linked"
    linked_library.symlink_to(tmp_path / "a-python")

    assert _libs.libraries(tmp_path, [python, rust]) == [
        tmp_path / "a-python",
        tmp_path / "z-rust",
    ]
    assert _libs.libraries(tmp_path / "missing", [python, rust]) == []


def test_library_directory_validates_language_and_direct_child(tmp_path: Path) -> None:
    """Require an existing direct library child with the selected manifest."""
    config = _libs.LibraryConfig.python("3.14.0")
    library = tmp_path / "libs" / "demo"
    library.mkdir(parents=True)
    (library / config.manifest_name).write_text("")

    assert _libs.library_directory(tmp_path, "libs/demo", config) == library.resolve()
    with pytest.raises(ValueError, match="direct child"):
        _libs.library_directory(tmp_path, "libs/demo/nested", config)
    with pytest.raises(ValueError, match="direct child"):
        _libs.library_directory(tmp_path, "outside", config)

    rust = _libs.LibraryConfig.rust("1.85.0")
    with pytest.raises(ValueError, match="no Cargo.toml"):
        _libs.library_directory(tmp_path, "libs/demo", rust)


def test_choose_library_retries_invalid_selection_and_quits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reprompt after invalid library choices and return None when quitting."""
    libraries = [Path("libs/demo"), Path("libs/other")]
    selections = iter(["invalid", "3", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(selections))

    assert _libs.choose_library(libraries) == libraries[1]
    assert capsys.readouterr().err == "Invalid selection: invalid\nInvalid selection: 3\n"

    monkeypatch.setattr("builtins.input", lambda _: "q")
    assert _libs.choose_library(libraries) is None
