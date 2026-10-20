from __future__ import annotations

import json
from pathlib import Path

from loquitur.schemas.cli import main
from loquitur.schemas.validator import (
    OBJECT_TYPE_TO_SCHEMA_NAME,
    SchemaValidationUsageError,
    schema_name_for_object_type,
    validate_by_object_type,
    validate_file,
    validate_instance,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(object_type: str) -> dict:
    fixture_name = (
        "registry_entry.catalog_valid.json" if object_type == "registry_entry" else f"{object_type}.valid.json"
    )
    return json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))


def test_validate_file_accepts_valid_fixture_by_schema_name() -> None:
    result = validate_file(
        "verification_summary.schema.json",
        FIXTURES / "verification_summary.valid.json",
    )
    assert result.ok is True
    assert result.schema_name == "verification_summary.schema.json"
    assert result.object_type == "verification_summary"
    assert result.errors == ()


def test_validate_instance_accepts_object_type_alias() -> None:
    for object_type, schema_name in OBJECT_TYPE_TO_SCHEMA_NAME.items():
        result = validate_instance(object_type, _fixture(object_type))
        assert result.ok is True
        assert result.schema_name == schema_name


def test_validate_by_object_type_resolves_schema_from_payload() -> None:
    instance = _fixture("coverage_summary")
    result = validate_by_object_type(instance)
    assert result.ok is True
    assert result.schema_name == "coverage_summary.schema.json"


def test_validate_by_object_type_rejects_missing_or_unknown_type() -> None:
    missing = validate_by_object_type({})
    assert missing.ok is False
    assert missing.errors[0].code == "missing_or_invalid_object_type"

    unknown = validate_by_object_type({"object_type": "unknown_object"})
    assert unknown.ok is False
    assert unknown.errors[0].code == "unsupported_object_type"


def test_validator_reports_required_additional_const_enum_and_pattern_errors() -> None:
    invalid = _fixture("verification_summary")
    invalid.pop("bundle_id")
    invalid["object_type"] = "wrong"
    invalid["schema_version"] = "v1"
    invalid["asset_type"] = "unsupported"
    invalid["policy_pack_sha256"] = "not-a-sha"
    invalid["unexpected"] = True

    result = validate_instance("verification_summary.schema.json", invalid)
    assert result.ok is False
    codes = {error.code for error in result.errors}
    assert "required" in codes
    assert "additional_property" in codes
    assert "const_mismatch" in codes
    assert "enum_mismatch" in codes
    assert "pattern_mismatch" in codes
    error_paths = {error.path for error in result.errors}
    assert "$.bundle_id" in error_paths
    assert "$.unexpected" in error_paths


def test_validator_reports_type_minimum_minlength_unique_items() -> None:
    invalid = _fixture("verification_summary")
    invalid["bundle_id"] = ""
    invalid["policy_version"] = 0
    invalid["reason_codes"] = ["INTEGRITY_OK", "INTEGRITY_OK"]
    invalid["warnings"] = [123]

    result = validate_instance("verification_summary", invalid)
    assert result.ok is False
    codes = {error.code for error in result.errors}
    assert "min_length" in codes
    assert "minimum" in codes
    assert "unique_items" in codes
    assert "type_mismatch" in codes


def test_validator_reports_minitems_for_schema_arrays() -> None:
    invalid = _fixture("verification_receipt")
    invalid["reason_codes"] = []

    result = validate_instance("verification_receipt", invalid)
    assert result.ok is False
    assert any(error.code == "min_items" and error.path == "$.reason_codes" for error in result.errors)


def test_validator_usage_errors_are_stable(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    try:
        validate_file("verification_summary", missing)
    except SchemaValidationUsageError as exc:
        assert "not found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected SchemaValidationUsageError")

    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    try:
        validate_file("verification_summary", bad)
    except SchemaValidationUsageError as exc:
        assert "invalid JSON" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected SchemaValidationUsageError")


def test_schema_name_for_object_type_resolves_registry_entry() -> None:
    assert schema_name_for_object_type("registry_entry") == "registry_entry.schema.json"


def test_cli_validate_valid_invalid_json_and_usage(capsys, tmp_path: Path) -> None:
    valid_path = FIXTURES / "verification_summary.valid.json"
    assert main(["validate", "verification_summary", str(valid_path)]) == 0
    assert "schema validation ok" in capsys.readouterr().out

    invalid = _fixture("verification_summary") | {"unexpected": True}
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    assert main(["validate", "verification_summary.schema.json", str(invalid_path)]) == 1
    out = capsys.readouterr().out
    assert "schema validation failed" in out
    assert "additional_property" in out

    registry_path = FIXTURES / "registry_entry.catalog_valid.json"
    assert main(["validate", "registry_entry.schema.json", str(registry_path)]) == 0
    assert "schema validation ok" in capsys.readouterr().out


def test_cli_validate_json_output(capsys) -> None:
    valid_path = FIXTURES / "verification_summary.valid.json"
    assert main(["validate", "verification_summary", str(valid_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["schema_name"] == "verification_summary.schema.json"
    assert payload["error_count"] == 0
