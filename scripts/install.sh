#!/usr/bin/env bash
set -euo pipefail

# Install repository tooling and packages from the committed lockfile.
uv sync --locked --all-packages --all-extras
uv cache prune --ci
