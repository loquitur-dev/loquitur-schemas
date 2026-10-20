from __future__ import annotations

import json
from pathlib import Path

import pytest

from loquitur.schemas.compatibility import (
    BREAKING,
    REVIEW_REQUIRED,
    check_schema_compatibility,
    load_bundled_compatibility_baseline,
    load_schema_map_from_root,
    main,
    snapshot_public_canonical_contracts,
)
from loquitur.schemas.inventory import PUBLIC_SCHEMA_NAMES, load_schema_json


def _schema_map() -> dict[str, dict]:
    return {name: load_schema_json(name) for name in PUBLIC_SCHEMA_NAMES}


def test_current_public_canonical_schemas_match_compatibility_baseline() -> None:
    report = check_schema_compatibility()

    assert report.ok is True
    assert report.breaking_findings == ()
    assert report.current_schema_count == 7
    assert report.baseline_id == "public_canonical_v0_1_0"


def test_contract_snapshot_is_deterministic_and_covers_every_public_schema() -> None:
    """Coverage is the point: a gate that skips a schema is green while that schema breaks."""
    snapshot = snapshot_public_canonical_contracts()

    assert snapshot["schema_names"] == list(PUBLIC_SCHEMA_NAMES)
    assert sorted(snapshot["schemas"]) == sorted(PUBLIC_SCHEMA_NAMES)
    for schema_name, contract in snapshot["schemas"].items():
        assert contract["$id"] == f"https://schemas.loquitur.dev/v1/{schema_name}"
    # These two carry the signed wire and the issuer authorization, where a breaking change
    # costs the most.
    assert "registry_entry.schema.json" in snapshot["schemas"]
    assert "trust_registry.schema.json" in snapshot["schemas"]
    assert snapshot == load_bundled_compatibility_baseline()


def test_required_field_removal_is_breaking() -> None:
    schemas = _schema_map()
    summary = json.loads(json.dumps(schemas["verification_summary.schema.json"]))
    summary["required"] = [field for field in summary["required"] if field != "bundle_id"]
    schemas["verification_summary.schema.json"] = summary

    report = check_schema_compatibility(current_schemas=schemas)

    assert report.ok is False
    assert any(
        finding.severity == BREAKING
        and finding.schema_name == "verification_summary.schema.json"
        and finding.code == "required_field_removed"
        and finding.baseline == "bundle_id"
        for finding in report.findings
    )


def test_property_contract_change_is_breaking() -> None:
    schemas = _schema_map()
    receipt = json.loads(json.dumps(schemas["verification_receipt.schema.json"]))
    receipt["properties"]["object_type"]["const"] = "verification_receipt_v3"
    schemas["verification_receipt.schema.json"] = receipt

    report = check_schema_compatibility(current_schemas=schemas)

    assert report.ok is False
    assert any(
        finding.severity == BREAKING
        and finding.schema_name == "verification_receipt.schema.json"
        and finding.code == "property_contract_changed"
        and finding.path == "$.properties.object_type"
        for finding in report.findings
    )


def test_optional_property_addition_requires_review_without_being_a_breaking_change() -> None:
    schemas = _schema_map()
    lineage = json.loads(json.dumps(schemas["lineage_summary.schema.json"]))
    lineage["properties"]["optional_future_field"] = {"type": "string"}
    schemas["lineage_summary.schema.json"] = lineage

    report = check_schema_compatibility(current_schemas=schemas)

    assert report.ok is True
    assert any(
        finding.severity == REVIEW_REQUIRED
        and finding.schema_name == "lineage_summary.schema.json"
        and finding.code == "property_added"
        for finding in report.findings
    )


def test_cli_fails_for_breaking_change_unless_explicitly_allowed_with_changelog(tmp_path: Path, capsys) -> None:
    schema_data_root = Path(__file__).resolve().parents[1] / "src" / "loquitur" / "schemas" / "data"
    current_root = tmp_path / "schemas"
    current_root.mkdir()
    for schema_name in PUBLIC_SCHEMA_NAMES:
        payload = json.loads((schema_data_root / schema_name).read_text(encoding="utf-8"))
        if schema_name == "verification_summary.schema.json":
            payload["required"] = [field for field in payload["required"] if field != "bundle_id"]
        (current_root / schema_name).write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_schema_map_from_root(current_root)
    assert "verification_summary.schema.json" in loaded

    assert main(["--current-schema-root", str(current_root)]) == 1
    assert "schema compatibility failed" in capsys.readouterr().out

    assert main(["--current-schema-root", str(current_root), "--allow-breaking"]) == 64
    assert "--allow-breaking requires --changelog" in capsys.readouterr().err

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# schema compatibility\n\n- intentional breaking change for test.\n", encoding="utf-8")
    assert main(["--current-schema-root", str(current_root), "--allow-breaking", "--changelog", str(changelog)]) == 0


# --------------------------------------------------------------- nested contract coverage


def _mutated(fn) -> dict[str, dict]:
    schemas = json.loads(json.dumps(_schema_map()))
    fn(schemas)
    return schemas


_REGISTRY_ENTRY = "registry_entry.schema.json"
_TRUST_REGISTRY = "trust_registry.schema.json"
_VERIFICATION_SUMMARY = "verification_summary.schema.json"


def _signature_branches(schemas: dict) -> list[dict]:
    return schemas[_REGISTRY_ENTRY]["properties"]["signature"]["oneOf"]


def _trust_entry(schemas: dict) -> dict:
    return schemas[_TRUST_REGISTRY]["properties"]["entries"]["items"]


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("delete the v2 signature branch", lambda s: _signature_branches(s).pop(1)),
        (
            "widen the signature algorithm identifier to anything",
            lambda s: _signature_branches(s)[1]["properties"]["algorithm"].update(pattern="^.+$"),
        ),
        (
            "change the signing payload version const",
            lambda s: _signature_branches(s)[1]["properties"]["payload_version"].update(const=3),
        ),
        (
            "widen the signature away from P1363 hex",
            lambda s: _signature_branches(s)[1]["properties"]["signature"].update(pattern="^.+$"),
        ),
        (
            "widen the trust-registry key_type identifier to anything",
            lambda s: _trust_entry(s)["properties"]["key_type"].update(pattern="^.+$"),
        ),
        (
            "widen public_key_hex to anything",
            lambda s: _trust_entry(s)["properties"]["public_key_hex"].update(pattern="^.*$"),
        ),
        ("empty the trust-entry required list", lambda s: _trust_entry(s).update(required=[])),
        (
            "narrow the trust-entry status enum",
            lambda s: _trust_entry(s)["properties"]["status"].update(enum=["active"]),
        ),
        (
            "cap a bundle id at one character",
            lambda s: s[_VERIFICATION_SUMMARY]["properties"]["bundle_id"].update(maxLength=1),
        ),
    ],
)
def test_nested_contract_changes_are_breaking(label: str, mutate) -> None:
    """Every one of these mutations is a breaking change the gate must report.

    Each changes a contract that lives in a nested object (``properties``, ``required``
    or ``oneOf`` below the top level, ``registry_entry.signature`` among them), which a
    gate that reduced such a property to ``{}`` would never register as a change.

    Two of these mutations widen an identifier grammar (algorithm, key_type): the schemas
    admit any well-formed identifier and leave support to the verifier's allowlist, so the
    grammar itself is the contract that must not move silently.
    """

    result = check_schema_compatibility(_mutated(mutate))

    assert result.ok is False, f"{label}: gate reported compatible"
    assert any(finding.severity == BREAKING for finding in result.findings), (
        f"{label}: no breaking finding; got {[f.severity for f in result.findings]}"
    )
