from __future__ import annotations

from loquitur.schemas.inventory import load_schema_json
from loquitur.schemas.validator import validate_instance


def test_verification_summary_schema_allows_optional_policy_evaluation_clock_trace() -> None:
    schema = load_schema_json("verification_summary.schema.json")

    assert "policy_checks" not in schema["required"]
    policy_checks = schema["properties"]["policy_checks"]
    assert policy_checks["type"] == ["object", "null"]
    # A looser pattern such as r"^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$" is wrong twice: the
    # `.*` accepts "2026-13-45Tnot a time at allZ", and `\d` is Unicode-Nd in Python but `[0-9]`
    # in the ECMA-262 dialect JSON Schema 2020-12 specifies, so this validator and any
    # JavaScript one would disagree on Arabic-Indic digits.
    assert policy_checks["properties"]["evaluation_clock_iso"]["pattern"] == (
        r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])"
        r"T([01][0-9]|2[0-3]):[0-5][0-9]:([0-5][0-9]|60)"
        r"(\.[0-9]+)?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$"
    )

    result = validate_instance(
        "verification_summary.schema.json",
        {
            "object_type": "verification_summary",
            "schema_version": "v2",
            "bundle_id": "bundle-policy-clock",
            "status": "pass",
            # LCP-0008: a verdict cites its grounds, and a pass says what it checked.
            # Present here so this test exercises the clock trace rather than re-failing
            # on the grounds rules, which have their own suite in test_verdict_grounds.
            "reason_codes": ["INTEGRITY_OK"],
            "key_checks": [{"check_id": "integrity", "status": "pass"}],
            "reason_code_vocabulary_version": "loquitur.reason_codes.v1",
            "policy_checks": {"evaluation_clock_iso": "2026-05-01T12:30:00+00:00"},
        },
    )

    assert result.ok is True
