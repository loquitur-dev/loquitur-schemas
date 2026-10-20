"""Schema discovery helpers for the Loquitur public schemas package."""

from __future__ import annotations

import json
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

from .errors import LoquiturSchemasError


class SchemaNotFoundError(FileNotFoundError, LoquiturSchemasError):
    """Raised when a requested bundled schema is not present."""


PUBLIC_CANONICAL_SCHEMA_NAMES: tuple[str, ...] = (
    "change_summary.schema.json",
    "coverage_summary.schema.json",
    "lineage_summary.schema.json",
    "verification_receipt.schema.json",
    "verification_summary.schema.json",
)

PUBLIC_REGISTRY_SCHEMA_NAMES: tuple[str, ...] = (
    "registry_entry.schema.json",
    "trust_registry.schema.json",
)

PUBLIC_SCHEMA_NAMES: tuple[str, ...] = PUBLIC_CANONICAL_SCHEMA_NAMES + PUBLIC_REGISTRY_SCHEMA_NAMES

CANONICAL_SCHEMA_URI_BASE = "https://schemas.loquitur.dev/v1/"
PUBLIC_SCHEMA_IDS: dict[str, str] = {name: f"{CANONICAL_SCHEMA_URI_BASE}{name}" for name in PUBLIC_SCHEMA_NAMES}
PUBLIC_SCHEMA_NAMES_BY_ID: dict[str, str] = {schema_id: name for name, schema_id in PUBLIC_SCHEMA_IDS.items()}


def canonical_schema_uri(name: str) -> str:
    """Return the absolute canonical URI identity for a bundled public schema."""

    try:
        return PUBLIC_SCHEMA_IDS[name]
    except KeyError as exc:
        raise SchemaNotFoundError(f"schema not bundled: {name}") from exc


def schema_name_for_uri(uri: str) -> str:
    """Resolve an absolute canonical schema URI to its bundled filename."""

    try:
        return PUBLIC_SCHEMA_NAMES_BY_ID[uri]
    except KeyError as exc:
        raise SchemaNotFoundError(f"unsupported canonical schema URI: {uri}") from exc


def schema_data_root() -> Traversable:
    """Return the package-data root containing bundled schema files."""

    return resources.files("loquitur.schemas").joinpath("data")


def list_schema_names() -> list[str]:
    """List bundled JSON Schema filenames."""

    root = schema_data_root()
    return sorted(item.name for item in root.iterdir() if item.is_file() and item.name.endswith(".schema.json"))


def load_schema_text(name: str) -> str:
    """Load a bundled JSON Schema by filename or canonical URI."""

    if name in PUBLIC_SCHEMA_NAMES_BY_ID:
        name = PUBLIC_SCHEMA_NAMES_BY_ID[name]

    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise SchemaNotFoundError(f"unsafe schema name: {name!r}")

    candidate = schema_data_root().joinpath(name)
    if not candidate.is_file():
        raise SchemaNotFoundError(f"schema not bundled: {name}")
    return candidate.read_text(encoding="utf-8")


def load_schema_json(name: str) -> dict[str, Any]:
    """Load a bundled JSON Schema as a JSON object."""

    value = json.loads(load_schema_text(name))
    if not isinstance(value, dict):  # pragma: no cover - package corruption guard
        raise SchemaNotFoundError(f"schema is not a JSON object: {name}")
    return value
