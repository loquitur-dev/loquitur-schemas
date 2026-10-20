from __future__ import annotations

import json
from pathlib import Path

from loquitur.schemas.inventory import (
    CANONICAL_SCHEMA_URI_BASE,
    PUBLIC_SCHEMA_IDS,
    PUBLIC_SCHEMA_NAMES,
    canonical_schema_uri,
    load_schema_json,
    load_schema_text,
    schema_name_for_uri,
)
from loquitur.schemas.validator import resolve_schema_name, validate_instance


def test_public_schema_ids_are_absolute_canonical_uris() -> None:
    assert CANONICAL_SCHEMA_URI_BASE == "https://schemas.loquitur.dev/v1/"
    assert sorted(PUBLIC_SCHEMA_IDS) == sorted(PUBLIC_SCHEMA_NAMES)

    for schema_name in PUBLIC_SCHEMA_NAMES:
        schema_id = canonical_schema_uri(schema_name)
        assert schema_id == f"https://schemas.loquitur.dev/v1/{schema_name}"
        assert schema_name_for_uri(schema_id) == schema_name
        assert load_schema_json(schema_name)["$id"] == schema_id


def test_schema_loaders_and_validator_accept_canonical_uri_identity() -> None:
    schema_uri = canonical_schema_uri("verification_summary.schema.json")
    schema = load_schema_json(schema_uri)
    assert schema["$id"] == schema_uri
    assert "verification_summary" in load_schema_text(schema_uri)
    assert resolve_schema_name(schema_uri) == "verification_summary.schema.json"

    fixture_path = Path(__file__).resolve().parent / "fixtures" / "verification_summary.valid.json"
    valid_instance = json.loads(fixture_path.read_text(encoding="utf-8"))
    result = validate_instance(schema_uri, valid_instance)
    assert result.ok is True
    assert result.schema_name == "verification_summary.schema.json"
