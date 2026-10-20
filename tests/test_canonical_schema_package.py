from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loquitur.schemas.inventory import (
    PUBLIC_CANONICAL_SCHEMA_NAMES,
    PUBLIC_REGISTRY_SCHEMA_NAMES,
    PUBLIC_SCHEMA_NAMES,
    canonical_schema_uri,
    list_schema_names,
    load_schema_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

EXPECTED_OBJECT_TYPES = {
    "verification_summary.schema.json": "verification_summary",
    "verification_receipt.schema.json": "verification_receipt",
    "change_summary.schema.json": "change_summary",
    "lineage_summary.schema.json": "lineage_summary",
    "coverage_summary.schema.json": "coverage_summary",
}

EXCLUDED_PUBLIC_DRAFT_OR_SUPPORT_SCHEMAS = {
    # ``trust_registry.schema.json`` is a public registry schema (asserted above)
    # and never belongs in this list.
    "manifest.schema.json",
    "envelope_env1.schema.json",
}


def _fixture_for(object_type: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{object_type}.valid.json").read_text(encoding="utf-8"))


def _lightweight_validate(schema: dict[str, Any], instance: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties", {})
    for required_name in schema.get("required", []):
        if required_name not in instance:
            errors.append(f"missing required field: {required_name}")
    if schema.get("additionalProperties") is False:
        for key in instance:
            if key not in properties:
                errors.append(f"unexpected field: {key}")
    for key, spec in properties.items():
        if key not in instance:
            continue
        value = instance[key]
        if "const" in spec and value != spec["const"]:
            errors.append(f"{key} const mismatch")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{key} enum mismatch")
    return errors


def test_five_stable_canonical_schemas_and_registry_entry_are_bundled() -> None:
    assert list_schema_names() == sorted(PUBLIC_SCHEMA_NAMES)
    assert set(PUBLIC_CANONICAL_SCHEMA_NAMES) == set(EXPECTED_OBJECT_TYPES)
    assert set(PUBLIC_REGISTRY_SCHEMA_NAMES) == {"registry_entry.schema.json", "trust_registry.schema.json"}
    assert set(list_schema_names()).isdisjoint(EXCLUDED_PUBLIC_DRAFT_OR_SUPPORT_SCHEMAS)


def test_canonical_schemas_preserve_public_contract_shape() -> None:
    for name, object_type in EXPECTED_OBJECT_TYPES.items():
        schema = load_schema_json(name)
        assert schema["$id"] == canonical_schema_uri(name)
        assert schema["$id"].startswith("https://schemas.loquitur.dev/v1/")
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert "object_type" in schema["required"]
        assert "schema_version" in schema["required"]
        assert schema["properties"]["object_type"]["const"] == object_type
        assert schema["properties"]["schema_version"]["enum"] == ["v2"]


def test_golden_fixtures_validate_against_bundled_schema_contract_subset() -> None:
    for name, object_type in EXPECTED_OBJECT_TYPES.items():
        schema = load_schema_json(name)
        fixture = _fixture_for(object_type)
        assert _lightweight_validate(schema, fixture) == []


def test_strict_additional_properties_is_enforced_by_contract_subset() -> None:
    schema = load_schema_json("verification_summary.schema.json")
    invalid = _fixture_for("verification_summary") | {"unexpected": True}
    assert "unexpected field: unexpected" in _lightweight_validate(schema, invalid)
