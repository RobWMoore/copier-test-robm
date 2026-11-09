"""Provide private helpers for repository-local tooling."""

import hashlib
import re
from pathlib import Path


def repo_root(module_path: Path) -> Path:
    """Return the generated repository root for a tooling module path."""
    for ancestor in module_path.resolve().parents:
        if ancestor.name == ".repo_tooling":
            return ancestor.parent
    raise ValueError(f"No .repo_tooling ancestor found for {module_path}.")


def to_kebab_case(value: str) -> str:
    """Return value as lowercase kebab case."""
    return re.sub(r"-+$", "", re.sub(r"^-+", "", re.sub(r"[^a-z0-9]+", "-", value.lower())))


def normalise_name(value: str) -> str:
    """Return a package or application name in kebab case."""
    return to_kebab_case(value)


def sha256_checksum(path: Path) -> str:
    """Return the SHA-256 checksum of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
