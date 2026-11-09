"""Run the shared tooling suite against explicit settings in every render."""

from __future__ import annotations

import pytest

from repo_tooling import _config


@pytest.fixture(autouse=True)
def configured_tooling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give existing workflow tests enabled defaults; individual tests override them."""
    for variable in (
        "VCS_REF",
        "VCS_REF_REPO_TEMPLATE",
        "VCS_REF_LIB_TEMPLATE",
        "VCS_REF_APP_TEMPLATE",
        "VCS_REF_COMPOSE_TEMPLATE",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(_config, "DEVELOPMENT_APPROACH", "application_and_library_development")
    monkeypatch.setattr(_config, "ENABLED_PROGRAMMING_LANGUAGES", ("python", "rust"))
    monkeypatch.setattr(_config, "DOCKER_ENABLED", True)
    monkeypatch.setattr(_config, "GITLAB_CI_ENABLED", True)
