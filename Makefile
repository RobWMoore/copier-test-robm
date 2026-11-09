.DEFAULT_GOAL := setup

# Repository scaffolding and maintenance tasks.
.PHONY: require-uv init create-application remove-application copier-update-repo copier-update-apps copier-update-all copier-regenerate
.PHONY: test
.PHONY: remove-library copier-update-libs

# Dependency and validation tasks.
.PHONY: setup install update-deps lock-check format fix check lint type

# Library scaffolding tasks.
.PHONY: create-library

# Docker project and runtime tasks.
.PHONY: docker-compose-up docker-compose-down copier-update-docker-compose-scripts
.PHONY: docker-compose-example docker-build docker-run


export UV_CACHE_DIR := $(CURDIR)/.uv-cache

# Supply Docker build inputs shared by application Dockerfiles.
include build.env

# Confirm uv is available before launching scripts with the tooling Python.
require-uv:
	@command -v uv >/dev/null 2>&1 || { \
		printf '%s\n' \
			'Error: uv is required but was not found on PATH.' \
			'' \
			'Install uv on macOS or Linux with:' \
			'' \
			'    curl -LsSf https://astral.sh/uv/install.sh | sh' \
			'' \
			'After installation, restart your shell or ensure uv is on PATH.' >&2; \
		exit 127; \
	}

# Create dependency lockfiles for a newly generated repository.
init:
	@if [ ! -f uv.lock ]; then uv sync; fi
	@if [ ! -f Cargo.lock ]; then cargo generate-lockfile; fi
	@echo "Remember to commit uv.lock and Cargo.lock to the repository."

# Install dependencies, then run checks and tests.
setup:
	@if [ ! -f uv.lock ]; then echo "uv.lock is missing. Run 'make init' first." >&2; exit 1; fi
	@if [ ! -f Cargo.lock ]; then echo "Cargo.lock is missing. Run 'make init' first." >&2; exit 1; fi
	@$(MAKE) install check test

# Install project dependencies and local tooling.
install:
	@ ./scripts/install.sh

# Create a new local app or service app in the repository.
create-application:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_create_application

# Remove an application from the repository.
remove-application:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_remove_application

# Remove a library from all configured workspaces.
remove-library:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_remove_library


# Update the repository template.
# Set VCS_REF_REPO_TEMPLATE to update from a specific revision.
copier-update-repo:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_copier_update_repo $(if $(VCS_REF_REPO_TEMPLATE),--vcs-ref "$(VCS_REF_REPO_TEMPLATE)")

# Update generated application templates.
copier-update-apps:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_copier_update_apps $(if $(VCS_REF_APP_TEMPLATE),--vcs-ref "$(VCS_REF_APP_TEMPLATE)")

# Update generated library templates.
copier-update-libs:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_copier_update_libs $(if $(VCS_REF_LIB_TEMPLATE),--vcs-ref "$(VCS_REF_LIB_TEMPLATE)")

# Update generated Docker Compose templates.
copier-update-docker-compose-scripts:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_copier_update_docker_compose $(if $(VCS_REF_COMPOSE_TEMPLATE),--vcs-ref "$(VCS_REF_COMPOSE_TEMPLATE)")

# Update the repository, then every generated app, library, and Compose project.
copier-update-all:
	@ $(MAKE) copier-update-repo
	@ $(MAKE) copier-update-apps
	@ $(MAKE) copier-update-libs
	@ $(MAKE) copier-update-docker-compose-scripts

# Regenerate every template layer from its current recorded template revision.
copier-regenerate:
	@ $(MAKE) copier-update-all \
		VCS_REF_REPO_TEMPLATE=:current: VCS_REF_LIB_TEMPLATE=:current: \
		VCS_REF_APP_TEMPLATE=:current: VCS_REF_COMPOSE_TEMPLATE=:current:


# Create a single-service Docker Compose example project.
docker-compose-example:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_docker_compose example

# Start the selected Docker Compose project.
docker-compose-up:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_docker_compose up

# Stop the selected Docker Compose project.
docker-compose-down:
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_docker_compose down

# Build an application's Dockerfile using the repository root as the build context.
docker-build:
	@PYTHON_IMAGE="$(PYTHON_IMAGE)" UV_VERSION="$(UV_VERSION)" RUST_IMAGE="$(RUST_IMAGE)" RUST_RUNTIME_IMAGE="$(RUST_RUNTIME_IMAGE)" uv run --package repo-tooling python -m repo_tooling.make_scripts.make_docker_app build

# Build the image, then start the selected app and remove the container when it exits.
docker-run:
	@PYTHON_IMAGE="$(PYTHON_IMAGE)" UV_VERSION="$(UV_VERSION)" RUST_IMAGE="$(RUST_IMAGE)" RUST_RUNTIME_IMAGE="$(RUST_RUNTIME_IMAGE)" uv run --package repo-tooling python -m repo_tooling.make_scripts.make_docker_app run

# Interactively create a library.
create-library: require-uv
	@ uv run --package repo-tooling python -m repo_tooling.make_scripts.make_create_library $(if $(VCS_REF_LIB_TEMPLATE),--vcs-ref "$(VCS_REF_LIB_TEMPLATE)")

# Update dependency lockfiles.
update-deps:
	@ uv run --package checks python -m checks.python_checks.uv_lock --apply
	@ uv run --package checks python -m checks.rust_checks.cargo_lock --apply

# Verify dependency lockfiles are current.
lock-check:
	@ uv run --package checks python -m checks.python_checks.uv_lock
	@ uv run --package checks python -m checks.rust_checks.cargo_lock

# Run format checks.
format:
	@ uv run --package checks python -m checks.python_checks.format_; true
	@ uv run --package checks python -m checks.rust_checks.format_; true

# Apply automatic formatting and dependency fixes.
fix:
	@ uv run --package checks python -m checks.python_checks.format_ --fix; true
	@ uv run --package checks python -m checks.python_checks.requirements --apply; true
	@ uv run --package checks python -m checks.rust_checks.format_ --fix; true

# Run all local checks that are expected to be fixable or advisory.
check:
	 uv run --package checks python -m checks.python_checks.lint_ --fix; true
	 uv run --package checks python -m checks.python_checks.mypy_; true
	 uv run --package checks python -m checks.python_checks.python_environment; true
	 uv run --package checks python -m checks.rust_checks.lint_; true
	 uv run --package checks python -m checks.rust_checks.rust_environment; true
	 uv run --package checks python -m checks.rust_checks.cargocheck_; true
	@ $(MAKE) lock-check

# Run lint and environment checks.
lint:
	@ uv run --package checks python -m checks.python_checks.lint_
	@ uv run --package checks python -m checks.python_checks.python_environment
	@ uv run --package checks python -m checks.rust_checks.lint_
	@ uv run --package checks python -m checks.rust_checks.rust_environment

# Run static type checks.
type:
	@ uv run --package checks python -m checks.python_checks.mypy_
	@ uv run --package checks python -m checks.rust_checks.cargocheck_

# Run test suites.
test:
	@ uv run --all-packages python -m checks.python_checks.coverage_ .
	@ uv run --package checks python -m checks.rust_checks.cargotest_ .
