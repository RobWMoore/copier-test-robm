"""Generated repository settings and runtime workflow restrictions.

Update these values through Copier settings rather than editing this file.
Python remains the tooling language regardless of enabled application languages.
"""

from __future__ import annotations

DEVELOPMENT_APPROACH = "application_and_library_development"
ENABLED_PROGRAMMING_LANGUAGES: tuple[str, ...] = tuple(["python", "rust"])
DOCKER_ENABLED = True
GITLAB_CI_ENABLED = False
PYTHON_VERSION = "3.14.0"
RUST_MSRV = "1.85.0"
UV_VERSION = "0.11.28"
COPIER_LIB_TEMPLATE_URL = "".join(
    [
        "git@gitlab.com:coldquanta/uk/software/prototypes/copier-templates/copier-li",
        "b-template.git",
    ]
)
COPIER_APP_TEMPLATE_URL = "".join(
    [
        "git@gitlab.com:coldquanta/uk/software/prototypes/copier-templates/copier-ap",
        "p-template.git",
    ]
)
COPIER_DOCKER_COMPOSE_TEMPLATE_URL = "".join(
    [
        "git@gitlab.com:coldquanta/uk/software/prototypes/copier-templates/copier-do",
        "cker-compose-template.git",
    ]
)


class ConfigurationError(ValueError):
    """A requested workflow is disabled by the generated repository settings."""


def feature_enabled(feature: str) -> bool:
    """Return whether a supported workflow feature is currently enabled."""
    return {
        "libraries": DEVELOPMENT_APPROACH == "application_and_library_development",
        "docker": DOCKER_ENABLED,
        "gitlab_ci": GITLAB_CI_ENABLED,
    }[feature]


def require_feature(feature: str) -> None:
    """Reject a disabled workflow before it prompts or changes the repository."""
    if not feature_enabled(feature):
        raise ConfigurationError(f"feature not enabled: {feature}.")


def require_language(language: str, component: str | None = None) -> None:
    """Reject a disabled application language, optionally identifying its component."""
    if language not in ENABLED_PROGRAMMING_LANGUAGES:
        context = f" ({component})" if component is not None else ""
        raise ConfigurationError(f"language not enabled: {language}{context}.")
