from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loquitur.schemas.inventory import PUBLIC_REGISTRY_SCHEMA_NAMES, load_schema_json
from loquitur.schemas.validator import validate_by_object_type, validate_instance

FIXTURES = Path(__file__).resolve().parent / "fixtures"

FORBIDDEN_TRUST_REGISTRY_FIELDS = {
    "private_key",
    "private_key_hex",
    "seed",
    "mnemonic",
    "kyc_data",
    "aml_data",
    "tenant_data",
    "investor_data",
    "evidence_documents",
    "document_text",
    "asset_address",
    "property_address",
    "valuation_amount",
    "nav_amount",
}


def _fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "trust_registry.valid.json").read_text(encoding="utf-8"))


def test_trust_registry_schema_is_bundled_as_public_registry_schema() -> None:
    assert "trust_registry.schema.json" in PUBLIC_REGISTRY_SCHEMA_NAMES

    schema = load_schema_json("trust_registry.schema.json")
    assert schema["title"] == "Loquitur Trust Registry"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["object_type"]["const"] == "trust_registry"
    assert schema["properties"]["schema_version"]["enum"] == ["v1"]
    assert "expires_at" in schema["required"]
    assert schema["properties"]["expires_at"]["type"] == "string"


def test_trust_registry_fixture_validates_by_schema_and_object_type() -> None:
    fixture = _fixture()

    by_schema = validate_instance("trust_registry.schema.json", fixture)
    assert by_schema.ok is True, by_schema.to_dict()
    assert by_schema.schema_name == "trust_registry.schema.json"

    by_object_type = validate_by_object_type(fixture)
    assert by_object_type.ok is True, by_object_type.to_dict()
    assert by_object_type.schema_name == "trust_registry.schema.json"


def test_trust_registry_entries_have_strict_authorization_shape() -> None:
    schema = load_schema_json("trust_registry.schema.json")
    entry_schema = schema["properties"]["entries"]["items"]

    assert entry_schema["additionalProperties"] is False
    assert entry_schema["properties"]["status"]["enum"] == ["active", "suspended", "revoked"]
    assert entry_schema["properties"]["key_type"]["pattern"] == "^[a-z0-9][a-z0-9_]{0,63}$"
    assert entry_schema["properties"]["public_key_hex"]["pattern"] == "^([a-f0-9]{2}){1,512}$"
    assert entry_schema["properties"]["allowed_asset_types"]["items"]["pattern"] == "^[a-z0-9][a-z0-9_]{0,63}$"
    assert "expires_at" in entry_schema["required"]
    assert entry_schema["properties"]["expires_at"]["type"] == "string"


def test_trust_registry_schema_rejects_sensitive_fields_at_root_and_entry_level() -> None:
    schema = load_schema_json("trust_registry.schema.json")
    root_properties = set(schema["properties"])
    entry_properties = set(schema["properties"]["entries"]["items"]["properties"])

    assert root_properties.isdisjoint(FORBIDDEN_TRUST_REGISTRY_FIELDS)
    assert entry_properties.isdisjoint(FORBIDDEN_TRUST_REGISTRY_FIELDS)

    for forbidden_name in sorted(FORBIDDEN_TRUST_REGISTRY_FIELDS):
        invalid_root = _fixture() | {forbidden_name: "must-not-be-public"}
        root_result = validate_instance("trust_registry", invalid_root)
        assert root_result.ok is False
        assert any(
            error.code == "additional_property" and error.path == f"$.{forbidden_name}" for error in root_result.errors
        )

        invalid_entry = _fixture()
        invalid_entry["entries"] = [invalid_entry["entries"][0] | {forbidden_name: "must-not-be-public"}]
        entry_result = validate_instance("trust_registry", invalid_entry)
        assert entry_result.ok is False
        assert any(
            error.code == "additional_property" and error.path == f"$.entries[0].{forbidden_name}"
            for error in entry_result.errors
        )


def test_trust_registry_rejects_unknown_status_key_type_and_scope() -> None:
    invalid = _fixture()
    invalid["entries"] = [
        invalid["entries"][0]
        | {
            "status": "trusted",
            "key_type": "RSA",
            "allowed_asset_types": ["private_credit"],
            "allowed_workflows": ["private_credit_review"],
        }
    ]

    result = validate_instance("trust_registry", invalid)
    assert result.ok is False
    codes = {error.code for error in result.errors}
    assert "enum_mismatch" in codes
    assert ("$.entries[0].key_type", "pattern_mismatch") in {(error.path, error.code) for error in result.errors}


def test_trust_registry_expiry_is_required_at_registry_and_entry_level() -> None:
    schema = load_schema_json("trust_registry.schema.json")
    entry_schema = schema["properties"]["entries"]["items"]

    assert "expires_at" in schema["required"]
    assert "expires_at" in entry_schema["required"]

    fixture = _fixture()
    assert fixture["expires_at"] == "2026-05-29T12:00:00Z"
    assert fixture["entries"][0]["expires_at"] == "2026-05-29T12:00:00Z"

    missing_root = _fixture()
    missing_root.pop("expires_at")
    missing_root_result = validate_instance("trust_registry", missing_root)
    assert missing_root_result.ok is False
    assert any(error.code == "required" and error.path == "$.expires_at" for error in missing_root_result.errors)

    missing_entry = _fixture()
    missing_entry["entries"] = [{k: v for k, v in missing_entry["entries"][0].items() if k != "expires_at"}]
    missing_entry_result = validate_instance("trust_registry", missing_entry)
    assert missing_entry_result.ok is False
    assert any(
        error.code == "required" and error.path == "$.entries[0].expires_at" for error in missing_entry_result.errors
    )

    null_root = _fixture()
    null_root["expires_at"] = None
    null_root_result = validate_instance("trust_registry", null_root)
    assert null_root_result.ok is False
    assert any(error.code == "type_mismatch" and error.path == "$.expires_at" for error in null_root_result.errors)


def test_trust_registry_signature_is_required_for_strict_schema_validation() -> None:
    schema = load_schema_json("trust_registry.schema.json")
    assert "signature" in schema["required"]
    assert schema["properties"]["signature"]["type"] == "object"

    fixture = _fixture()
    assert isinstance(fixture["signature"], dict)

    unsigned = _fixture()
    unsigned.pop("signature")

    unsigned_result = validate_instance("trust_registry", unsigned)
    assert unsigned_result.ok is False
    assert any(error.code == "required" and error.path == "$.signature" for error in unsigned_result.errors)

    null_signature = _fixture()
    null_signature["signature"] = None
    null_result = validate_instance("trust_registry", null_signature)
    assert null_result.ok is False
    assert any(error.code == "type_mismatch" and error.path == "$.signature" for error in null_result.errors)

    signed_result = validate_instance("trust_registry", fixture)
    assert signed_result.ok is True, signed_result.to_dict()


def test_trust_registry_admits_open_algorithm_and_key_type_identifiers() -> None:
    # The pair (algorithm, key_type) is judged by the verifier's allowlist at the signature
    # step and at root authentication; the schema holds only the identifier grammar.
    admitted = _fixture()
    admitted["entries"][0]["key_type"] = "ed25519"
    admitted["entries"][0]["public_key_hex"] = "ab" * 32
    admitted["signature"]["algorithm"] = "ed25519"
    assert validate_instance("trust_registry", admitted).ok is True

    refused = _fixture()
    refused["entries"][0]["key_type"] = "Ed25519"
    refused["entries"][0]["public_key_hex"] = "abc"
    refused["signature"]["algorithm"] = ""
    result = validate_instance("trust_registry", refused)
    assert result.ok is False
    assert {(error.path, error.code) for error in result.errors} == {
        ("$.entries[0].key_type", "pattern_mismatch"),
        ("$.entries[0].public_key_hex", "pattern_mismatch"),
        ("$.signature.algorithm", "pattern_mismatch"),
    }
