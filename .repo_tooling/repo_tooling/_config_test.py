"""Tests for runtime feature and application-language restrictions."""

from __future__ import annotations

import pytest

from repo_tooling import _config


@pytest.mark.parametrize(
    ("feature", "setting", "disabled", "enabled"),
    [
        (
            "libraries",
            "DEVELOPMENT_APPROACH",
            "application_only_development",
            "application_and_library_development",
        ),
        ("docker", "DOCKER_ENABLED", False, True),
        ("gitlab_ci", "GITLAB_CI_ENABLED", False, True),
    ],
)
def test_feature_validation_reads_current_configuration(
    feature: str,
    setting: str,
    disabled: object,
    enabled: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_config, setting, disabled)
    with pytest.raises(_config.ConfigurationError, match=f"feature not enabled: {feature}"):
        _config.require_feature(feature)
    monkeypatch.setattr(_config, setting, enabled)
    _config.require_feature(feature)


@pytest.mark.parametrize("language", ["python", "rust"])
def test_language_validation_distinguishes_tooling_python_from_application_languages(
    language: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ())
    with pytest.raises(_config.ConfigurationError, match=f"language not enabled: {language}"):
        _config.require_language(language)
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", (language,))
    _config.require_language(language)
