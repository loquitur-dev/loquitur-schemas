from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loquitur.schemas.inventory import load_schema_json
from loquitur.schemas.validator import _validate_value, validate_by_object_type, validate_instance

FIXTURES = Path(__file__).resolve().parent / "fixtures"

FORBIDDEN_PUBLIC_FIELD_NAMES = {
    "raw_evidence",
    "evidence_documents",
    "document_text",
    "ocr_output",
    "canonical_input",
    "asset_address",
    "property_address",
    "parcel_id",
    "valuation_amount",
    "nav_amount",
    "price_per_share",
    "cap_rate",
    "noi",
    "irr",
    "ltv",
    "vacancy",
    "rent_roll",
    "tenant_data",
    "investor_data",
    "kyc_data",
    "aml_data",
    "coverage_summary",
    "change_summary",
    "lineage_summary",
}


def _fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "registry_entry.catalog_valid.json").read_text(encoding="utf-8"))


def test_registry_entry_schema_is_bundled_with_strict_public_shape() -> None:
    schema = load_schema_json("registry_entry.schema.json")

    assert schema["title"] == "Loquitur Registry Entry"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["object_type"]["const"] == "registry_entry"
    assert schema["properties"]["schema_version"]["enum"] == ["v1"]
    assert schema["properties"]["asset_type"]["pattern"] == "^[a-z0-9][a-z0-9_]{0,63}$"
    assert "enum" not in schema["properties"]["asset_type"]
    assert schema["properties"]["verdict"]["enum"] == ["PASS", "WARN", "REVIEW", "FAIL"]


def test_registry_entry_fixture_validates_by_schema_and_object_type() -> None:
    fixture = _fixture()

    by_schema = validate_instance("registry_entry.schema.json", fixture)
    assert by_schema.ok is True, by_schema.to_dict()
    assert by_schema.schema_name == "registry_entry.schema.json"

    by_object_type = validate_by_object_type(fixture)
    assert by_object_type.ok is True, by_object_type.to_dict()
    assert by_object_type.schema_name == "registry_entry.schema.json"


def test_registry_entry_schema_rejects_sensitive_public_fields() -> None:
    schema = load_schema_json("registry_entry.schema.json")
    public_properties = set(schema["properties"])

    assert public_properties.isdisjoint(FORBIDDEN_PUBLIC_FIELD_NAMES)

    for forbidden_name in sorted(FORBIDDEN_PUBLIC_FIELD_NAMES):
        invalid = _fixture() | {forbidden_name: "must-not-be-public"}
        result = validate_instance("registry_entry", invalid)
        assert result.ok is False
        assert any(
            error.code == "additional_property" and error.path == f"$.{forbidden_name}" for error in result.errors
        )


def test_registry_entry_schema_rejects_malformed_asset_types_and_invalid_verdicts() -> None:
    invalid = _fixture()
    invalid["asset_type"] = "Private-Credit"
    invalid["verdict"] = "VERIFIED"
    invalid["reason_codes"] = ["CONFLICTING_EVIDENCE_DETECTED", "CONFLICTING_EVIDENCE_DETECTED"]

    result = validate_instance("registry_entry", invalid)
    assert result.ok is False
    codes = {error.code for error in result.errors}
    assert "enum_mismatch" in codes
    assert "pattern_mismatch" in codes
    assert "unique_items" in codes


def test_registry_entry_signature_and_anchor_are_reserved_not_required() -> None:
    fixture = _fixture()
    fixture.pop("signature")
    fixture.pop("anchor")

    result = validate_instance("registry_entry", fixture)
    assert result.ok is True, result.to_dict()

    signed = fixture | {
        "signature": {
            "algorithm": "secp256k1_ecdsa_sha256",
            "key_id": "demo-key-2",
            "payload_id": "registry_entry_signing_payload_v2",
            "payload_version": 2,
            "signature": "a36e1f293f0c2207b3b1139fce4c3d50854e5af50000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        },
        "anchor": {
            "method": "blockchain_transaction",
            "system": "example:testnet",
            "anchor_reference": "tx-demo-placeholder",
        },
    }
    signed_result = validate_instance("registry_entry", signed)
    assert signed_result.ok is True, signed_result.to_dict()


def test_registry_entry_signature_and_anchor_subobjects_are_strict() -> None:
    invalid = _fixture() | {
        "signature": {
            "algorithm": "secp256k1_ecdsa_sha256",
            "key_id": "demo-key-2",
            "payload_id": "registry_entry_signing_payload_v2",
            "payload_version": 2,
            "signature": "a36e1f293f0c2207b3b1139fce4c3d50854e5af50000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
            "public_key_material": "must-not-leak-here",
        },
        "anchor": {
            "method": "blockchain_transaction",
            "system": "example:testnet",
            "anchor_reference": "tx-demo-placeholder",
            "raw_transaction": "must-not-leak-here",
        },
    }

    result = validate_instance("registry_entry", invalid)
    assert result.ok is False
    error_paths = {error.path for error in result.errors if error.code == "additional_property"}
    assert "$.signature.public_key_material" in error_paths
    assert "$.anchor.raw_transaction" in error_paths


def _with_algorithm(algorithm: str) -> dict[str, Any]:
    return _fixture() | {
        "signature": {
            "algorithm": algorithm,
            "key_id": "demo-key-2",
            "payload_id": "registry_entry_signing_payload_v2",
            "payload_version": 2,
            "signature": "00" * 64,
        }
    }


def test_registry_entry_schema_admits_any_well_formed_algorithm_identifier() -> None:
    # The document names its algorithm; whether a verifier supports it is decided at the
    # signature step from the verifier's own allowlist (UNSUPPORTED_SIGNATURE_ALGORITHM), not
    # by the schema.
    got = {
        algorithm: validate_instance("registry_entry", _with_algorithm(algorithm)).ok
        for algorithm in ("secp256k1_ecdsa_sha256", "ed25519", "unknown_alg", "a", "a" * 64)
    }
    assert got == dict.fromkeys(got, True)


def test_registry_entry_schema_refuses_an_algorithm_outside_the_identifier_grammar() -> None:
    got = {}
    for algorithm in ("ED25519", "", "_x", "a-b", "a" * 65, "ed25519\n"):
        result = validate_instance("registry_entry", _with_algorithm(algorithm))
        got[algorithm] = (result.ok, {error.code for error in result.errors if error.path == "$.signature.algorithm"})
    assert got == dict.fromkeys(got, (False, {"pattern_mismatch"}))


def test_a_signature_without_payload_id_and_payload_version_breaks_the_contract() -> None:
    # The protocol defines no signing payload before v2, so the schema has no branch for the
    # old three-member shape: it matches neither null nor the v2 object.
    entry = _fixture() | {
        "signature": {
            "algorithm": "secp256k1_ecdsa_sha256",
            "key_id": "demo-key-2",
            "signature": "00" * 64,
        }
    }
    result = validate_instance("registry_entry", entry)
    assert result.ok is False
    assert all(error.path.startswith("$.signature") for error in result.errors), result.to_dict()
    schema = load_schema_json("registry_entry.schema.json")
    branches = schema["properties"]["signature"]["oneOf"]
    assert [branch.get("title") for branch in branches] == [None, "RegistryEntrySignatureV2"]
    # Against the v2 branch alone, the two missing members are what refuses it.
    assert {(error.path, error.code) for error in _validate_value(branches[1], entry["signature"], "$.signature")} == {
        ("$.signature.payload_id", "required"),
        ("$.signature.payload_version", "required"),
    }
