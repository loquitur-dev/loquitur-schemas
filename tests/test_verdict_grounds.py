"""LCP-0008: the verdict is a function of the grounds it cites.

Two families of test. The first binds the ``reason_codes`` enum in
``verification_summary.schema.json`` to the reason-code catalog, because the enum is a
hand-maintained second copy of the catalog's key set, and two copies of one vocabulary
drift apart unless something binds them.

The second exercises the rules JSON Schema cannot express: that the status equals the
mapped maximum severity of the cited codes, and that a ``pass`` cites an affirmative
ground. Each is written as a pair: a conforming document that must be accepted and a
malformed one that must be rejected. A tightening whose violation is never exercised is a
tightening that has not been tested.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from loquitur.schemas import load_reason_codes_catalog
from loquitur.schemas.validator import _validate_value, json_value_key
from loquitur.schemas.verdict_grounds import (
    SEVERITY_ORDER,
    SEVERITY_TO_STATUS,
    max_severity,
    status_for_codes,
    verdict_grounds_errors,
)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "loquitur" / "schemas" / "data" / "verification_summary.schema.json"
)


def _schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _base(**overrides) -> dict:
    doc = {
        "object_type": "verification_summary",
        "schema_version": "v2",
        "bundle_id": "bundle-001",
        "status": "pass",
        "reason_codes": ["INTEGRITY_OK"],
        "reason_code_vocabulary_version": "loquitur.reason_codes.v1",
    }
    doc.update(overrides)
    return doc


# --------------------------------------------------------------- the binding gate


def test_schema_enum_equals_catalog_key_set() -> None:
    """The enum and the catalog must name exactly the same codes.

    Not a subset in either direction: a code in the catalog but not the enum can never be
    emitted, and a code in the enum but not the catalog can be emitted and then fails to
    render, which is worse: it produces a verdict nobody can explain.
    """
    enum = set(_schema()["properties"]["reason_codes"]["items"]["enum"])
    catalog = set(load_reason_codes_catalog().entries)
    assert enum == catalog, f"only in schema enum: {sorted(enum - catalog)}; only in catalog: {sorted(catalog - enum)}"


def test_reason_context_does_not_carry_a_second_copy_of_the_vocabulary() -> None:
    """``reason_context[].code`` must not repeat the enum.

    The restricted dialect forbids ``$ref``, so the choice is between a second
    hand-maintained copy of the whole code list and typing the field as a plain string whose
    catalog membership is checked by :func:`verdict_grounds_errors`. A second copy drifts,
    so it is the string.
    """
    code = _schema()["properties"]["reason_context"]["items"]["properties"]["code"]
    assert "enum" not in code
    assert code["type"] == "string"
    # The context deliberately covers INTEGRITY_OFFLINE_FAIL as well. Without that cover the
    # document also violates the missing-context rule, and a bare truthiness check on the
    # error list would pass on `reason_context_missing` while proving nothing about the
    # catalog check.
    errors = verdict_grounds_errors(
        _base(
            status="fail",
            reason_codes=["INTEGRITY_OFFLINE_FAIL"],
            reason_context=[{"code": "INTEGRITY_OFFLINE_FAIL"}, {"code": "NOT_IN_THE_VOCABULARY"}],
        )
    )
    assert any(e.startswith("reason_context_code_not_in_catalog") for e in errors), (
        "an unknown code in reason_context must be caught by the catalog rule, not by whichever "
        f"other rule happens to fire: {errors}"
    )


def test_schema_stays_inside_the_restricted_validator_dialect() -> None:
    """Every keyword used must be one the project's own validator supports.

    ``loquitur.schemas.validator`` accepts nineteen keywords and fails closed on anything
    else, because a third party must be able to write an independent validator. A schema
    edit that reaches for ``if``/``then``/``$ref``/``minProperties`` is caught here, before
    it ships rather than after.
    """
    from loquitur.schemas.validator import SUPPORTED_SCHEMA_KEYWORDS

    def walk(node: object) -> set[str]:
        used: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    for child in value.values():
                        used |= walk(child)
                    used.add(key)
                    continue
                used.add(key)
                if key in {"items", "oneOf", "additionalProperties"}:
                    if isinstance(value, list):
                        for child in value:
                            used |= walk(child)
                    else:
                        used |= walk(value)
        return used

    schema = _schema()
    # Property NAMES are not keywords; walk() already skips them by recursing into the
    # values of `properties` rather than treating its keys as keywords.
    unsupported = {k for k in walk(schema) if k not in SUPPORTED_SCHEMA_KEYWORDS}
    assert not unsupported, f"unsupported keywords in verification_summary: {sorted(unsupported)}"


def test_every_severity_in_the_catalog_maps_to_a_status() -> None:
    """No catalog entry may carry a severity the mapping cannot resolve."""
    severities = {e.severity for e in load_reason_codes_catalog().entries.values()}
    assert severities <= set(SEVERITY_ORDER)
    assert set(SEVERITY_ORDER) == set(SEVERITY_TO_STATUS)


def test_an_affirmative_ground_exists_for_the_pass_path() -> None:
    """Requiring a pass to cite an info code is only satisfiable if info codes exist."""
    info = [c for c, e in load_reason_codes_catalog().entries.items() if e.severity == "info"]
    assert info, "no info-severity code exists, so no conforming pass could be emitted"


# --------------------------------------------------------------- the severity rules


def test_maximum_severity_decides_the_verdict() -> None:
    """One fail among many info codes still fails."""
    codes = ["INTEGRITY_OK", "AUTHORIZATION_VERIFIED", "INTEGRITY_OFFLINE_FAIL"]
    assert max_severity(codes) == "fail"
    assert status_for_codes(codes) == "fail"


def test_conforming_pass_is_accepted() -> None:
    assert verdict_grounds_errors(_base(key_checks=[{"check_id": "integrity"}])) == []


@pytest.mark.parametrize(
    ("doc", "expected_error"),
    [
        (_base(reason_codes=[]), "reason_codes_absent"),
        (_base(reason_codes=["NOT_A_REAL_CODE"]), "reason_code_not_in_catalog"),
        # A pass citing a revoked key: the central case the verdict-grounds rules refuse.
        (
            _base(
                reason_codes=["AUTHORIZATION_ISSUER_KEY_REVOKED"],
                reason_context=[{"code": "AUTHORIZATION_ISSUER_KEY_REVOKED"}],
            ),
            "status_contradicts_grounds",
        ),
        (_base(status="fail", reason_codes=["INTEGRITY_OK"]), "status_contradicts_grounds"),
        # Severity warn implies `warning`; declaring `pass` contradicts it before the
        # missing-affirmative-ground rule is ever reached.
        (_base(reason_codes=["FRESHNESS_WARNING"]), "status_contradicts_grounds"),
        (
            _base(status="fail", reason_codes=["INTEGRITY_OFFLINE_FAIL"]),
            "reason_context_missing",
        ),
        (
            _base(status="review", reason_codes=["NEEDS_REVIEW"]),
            "reason_context_missing",
        ),
        # The conditional rule the restricted dialect cannot express, so it must be
        # exercised here or it is enforced nowhere.
        (_base(), "pass_without_key_checks"),
        (_base(key_checks=[]), "pass_without_key_checks"),
        (_base(key_checks=None), "pass_without_key_checks"),
    ],
)
def test_malformed_grounds_are_rejected(doc: dict, expected_error: str) -> None:
    errors = verdict_grounds_errors(doc)
    assert errors, f"expected {expected_error}, got no error"
    assert any(e.startswith(expected_error) for e in errors), errors


def test_actionable_severities_accept_context() -> None:
    doc = _base(
        status="fail",
        reason_codes=["AUTHORIZATION_ISSUER_KEY_REVOKED"],
        reason_context=[
            {
                "code": "AUTHORIZATION_ISSUER_KEY_REVOKED",
                "subject": "issuer_key_id=key-7",
                "observed": "revoked_at 2026-01-01T00:00:00Z",
                "expected": "not revoked at the evaluation time",
                "window": "2025-01-01T00:00:00Z/2026-01-01T00:00:00Z",
            }
        ],
    )
    assert verdict_grounds_errors(doc) == []


# VG-1: "Entries MUST be unique", applied independently of schema validation, and a VG-1
# violation terminates the check, so the duplicate is the only error reported, whatever
# else the document gets wrong.
@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        (
            _base(key_checks=[{"check_id": "integrity"}], reason_codes=["INTEGRITY_OK", "INTEGRITY_OK"]),
            ["reason_codes_duplicated: INTEGRITY_OK (VG-1 requires unique entries)"],
        ),
        (
            _base(status="fail", key_checks=[{"check_id": "integrity"}], reason_codes=["INTEGRITY_OK", "INTEGRITY_OK"]),
            ["reason_codes_duplicated: INTEGRITY_OK (VG-1 requires unique entries)"],
        ),
        (
            _base(reason_codes=["INTEGRITY_OK", "NOT_A_CODE", "NOT_A_CODE"]),
            ["reason_codes_duplicated: NOT_A_CODE (VG-1 requires unique entries)"],
        ),
        (
            _base(reason_codes=["INTEGRITY_OK", "INTEGRITY_OK", "FRESHNESS_OK", "INTEGRITY_OK", "FRESHNESS_OK"]),
            ["reason_codes_duplicated: FRESHNESS_OK, INTEGRITY_OK (VG-1 requires unique entries)"],
        ),
    ],
    ids=[
        "duplicate",
        "duplicate-and-status-contradiction",
        "duplicate-unknown-code",
        "triple-and-second-code-listed-once",
    ],
)
def test_duplicate_reason_codes_are_a_terminating_vg1_violation(doc: dict, expected: list[str]) -> None:
    assert verdict_grounds_errors(doc) == expected


def test_codes_differing_only_in_case_are_not_duplicates_and_exact_repeats_are() -> None:
    """Uniqueness is exact: a case variant is an unknown code (VG-2), not a VG-1 duplicate,
    while the same code written twice beside it is one."""
    errors = verdict_grounds_errors(_base(reason_codes=["INTEGRITY_OK", "integrity_ok"]))
    assert [e.split(":", 1)[0] for e in errors] == ["reason_code_not_in_catalog"]
    errors = verdict_grounds_errors(_base(reason_codes=["INTEGRITY_OK", "integrity_ok", "INTEGRITY_OK"]))
    assert errors == ["reason_codes_duplicated: INTEGRITY_OK (VG-1 requires unique entries)"]


@pytest.mark.parametrize(
    "codes",
    [[1, 1.0], [{"a": 1}, {"a": 1.0}], [0, -0.0], [0.1, 1e-1]],
    ids=["one-and-one-point-zero", "nested-number", "zero-and-minus-zero", "same-binary64"],
)
def test_entries_that_are_one_json_value_are_a_vg1_duplicate(codes: list[object]) -> None:
    """Numbers compare by the binary64 value they are read as, so these are one entry cited
    twice, as both reference verifiers find."""
    errors = verdict_grounds_errors(_base(reason_codes=codes))
    assert [e.split(":", 1)[0] for e in errors] == ["reason_codes_duplicated"]


# Values RFC 8785 canonicalization refuses (a noncharacter, an integer beyond 2^53 - 1, a lone
# surrogate), each written twice as one JSON value: in another member order, or with a number
# in another spelling of the same binary64 value.
_UNCANONICAL_DUPLICATES = [
    [{"a": "\uffff", "b": 1}, {"b": 1, "a": "\uffff"}],
    [2**60, float(2**60)],
    [2**60 + 1, float(2**60)],
    [[1, "\ufdd0"], [1.0, "\ufdd0"]],
    [["\ud800", 1], ["\ud800", 1.0]],
]
_UNCANONICAL_IDS = [
    "noncharacter-member-order",
    "big-integer",
    "big-integer-rounded",
    "noncharacter-array",
    "lone-surrogate",
]


@pytest.mark.parametrize("codes", _UNCANONICAL_DUPLICATES, ids=_UNCANONICAL_IDS)
def test_one_json_value_canonicalization_refuses_is_still_a_vg1_duplicate(codes: list[object]) -> None:
    """Equality is by JSON value even where canonicalization refuses the value, as
    loquitur-verify-ts finds: a refusal does not make two equal entries distinct."""
    errors = verdict_grounds_errors(_base(reason_codes=codes))
    assert [e.split(":", 1)[0] for e in errors] == ["reason_codes_duplicated"]


@pytest.mark.parametrize("codes", _UNCANONICAL_DUPLICATES, ids=_UNCANONICAL_IDS)
def test_unique_items_agrees_with_vg1(codes: list[object]) -> None:
    """The schema's ``uniqueItems`` and VG-1 use one key, so they find the same duplicates."""
    unique_errors = _validate_value({"type": "array", "uniqueItems": True}, codes, "$")
    assert [e.code for e in unique_errors] == ["unique_items"]


def test_json_value_key_never_raises() -> None:
    """Values no JSON text carries are still keyed, and keyed apart from every finite number."""
    deep: list[object] = []
    for _ in range(5000):
        deep = [deep]
    values = [math.nan, math.inf, -math.inf, 10**400, -(10**5000), deep, {1: "a"}, object.__class__]
    keys = [json_value_key(value) for value in values]
    assert json_value_key(10**400) == json_value_key(math.inf)
    assert json_value_key(-(10**5000)) == json_value_key(-math.inf)
    assert json_value_key(math.nan) != json_value_key(None)
    assert all(json_value_key(n) not in keys for n in (0, 1, -1, 1.5, 2**1023, -(2.0**1023)))


def test_unknown_status_is_gone_from_every_layer() -> None:
    """``unknown`` is not a status (LCP-0008), by any door.

    Three independent facts keep it out and each is asserted here, so that anyone
    considering adding it meets the reasoning rather than rediscovers it. It would resolve
    to no registry verdict; no severity maps to it, so a summary citing at least one code,
    as rule one requires, could never imply it; and the cases it might cover, the ones
    where verification could not run, have codes of severity ``review`` that say why
    rather than only that something is off.

    The normative owner is ``loquitur-protocol/VERIFICATION_VOCABULARIES.json``, whose own
    ``extension_rule`` declares a vocabulary change to be a breaking protocol change
    requiring schema, types and conformance updates together.
    """
    from loquitur.schemas.verification_vocabulary import (
        STATUS_TO_REGISTRY_VERDICT,
        VERIFICATION_STATUSES,
    )

    assert "unknown" not in VERIFICATION_STATUSES
    assert "unknown" not in STATUS_TO_REGISTRY_VERDICT
    assert "unknown" not in SEVERITY_TO_STATUS.values()
    assert "unknown" not in _schema()["properties"]["status"]["enum"]

    # The mapping is total: no caller has to handle a null.
    assert set(STATUS_TO_REGISTRY_VERDICT) == set(VERIFICATION_STATUSES)
    assert all(v is not None for v in STATUS_TO_REGISTRY_VERDICT.values())

    # Rejected at both layers, since each covers what the other cannot.
    import jsonschema

    assert list(jsonschema.Draft202012Validator(_schema()).iter_errors(_base(status="unknown")))
    assert verdict_grounds_errors(_base(status="unknown"))


# ------------------------------------------------- generated scenarios


def _build(codes: set[str]) -> dict:
    """Construct the summary a conforming producer would emit for ``codes``."""
    from loquitur.schemas.verdict_grounds import STATUSES_REQUIRING_CONTEXT

    catalog = load_reason_codes_catalog()
    status = status_for_codes(codes)
    doc = _base(status=status, reason_codes=sorted(codes))
    if status == "pass":
        doc["key_checks"] = [{"check_id": "integrity", "status": "pass"}]
    context = [{"code": c} for c in sorted(codes) if catalog.get(c).severity in STATUSES_REQUIRING_CONTEXT]
    if context:
        doc["reason_context"] = context
    return doc


def test_every_category_can_produce_a_conforming_summary() -> None:
    """No category may be unreportable.

    A category whose codes cannot appear in any valid summary is vocabulary that can never
    be used: the rules would have deleted part of the catalog without a trace.
    """
    catalog = load_reason_codes_catalog()
    categories: dict[str, set[str]] = {}
    for code, entry in catalog.entries.items():
        categories.setdefault(entry.category, set()).add(code)

    for category, codes in sorted(categories.items()):
        doc = _build(codes | {"INTEGRITY_OK"})
        assert verdict_grounds_errors(doc) == [], f"{category}: {verdict_grounds_errors(doc)}"


@pytest.mark.parametrize("seed", [20260809, 7, 31337])
def test_generated_code_sets_always_produce_a_conforming_summary(seed: int) -> None:
    """Over arbitrary subsets of the vocabulary, the rules stay satisfiable.

    Seeded rather than random: a property test that cannot be replayed is a flake
    generator, and determinism is the product here.
    """
    import random

    rng = random.Random(seed)
    codes_all = sorted(load_reason_codes_catalog().entries)
    for _ in range(300):
        codes = set(rng.sample(codes_all, rng.randint(1, 8)))
        doc = _build(codes)
        assert verdict_grounds_errors(doc) == [], f"{sorted(codes)}: {verdict_grounds_errors(doc)}"


@pytest.mark.parametrize("seed", [20260809, 7])
def test_no_code_set_admits_a_softer_verdict_than_it_implies(seed: int) -> None:
    """The central property: a verdict cannot be milder than its own grounds.

    This is what makes the summary checkable by a third party rather than trusted. Every
    substitution of a different status must be caught, in both directions: overstating a
    failure is as much a contradiction as understating one.
    """
    import random

    rng = random.Random(seed)
    codes_all = sorted(load_reason_codes_catalog().entries)
    for _ in range(200):
        codes = set(rng.sample(codes_all, rng.randint(1, 5)))
        implied = status_for_codes(codes)
        for claimed in ("pass", "warning", "review", "fail"):
            if claimed == implied:
                continue
            doc = _build(codes)
            doc["status"] = claimed
            doc.setdefault("key_checks", [{"check_id": "integrity", "status": "pass"}])
            assert verdict_grounds_errors(doc), (
                f"claiming {claimed} for codes implying {implied} was not caught: {sorted(codes)}"
            )


# ------------------------------------------------- content never makes the checker raise


@pytest.mark.parametrize(
    ("member", "label"),
    [(7, "7"), (None, "None"), (True, "True"), (["a"], "['a']"), ({}, "{}"), (1.5, "1.5")],
    ids=["number", "null", "boolean", "array", "object", "float"],
)
def test_a_non_string_reason_code_is_a_code_outside_the_catalog(member: object, label: str) -> None:
    errors = verdict_grounds_errors(_base(reason_codes=["INTEGRITY_OK", member]))
    assert errors == [f"reason_code_not_in_catalog: {label} (vocabulary loquitur.reason_codes.v1)"]


def test_mixed_unknown_entries_are_all_named_in_one_sorted_message() -> None:
    errors = verdict_grounds_errors(_base(reason_codes=["NOT_A_CODE", 7, {"a": 1}, None]))
    assert errors == ["reason_code_not_in_catalog: 7, NOT_A_CODE, None, {'a': 1} (vocabulary loquitur.reason_codes.v1)"]


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        ([7, 7], "reason_codes_duplicated: 7 (VG-1 requires unique entries)"),
        (
            [{"a": 1, "b": 2}, {"b": 2, "a": 1}],
            "reason_codes_duplicated: {'a': 1, 'b': 2} (VG-1 requires unique entries)",
        ),
        ([["a"], ["a"], "INTEGRITY_OK"], "reason_codes_duplicated: ['a'] (VG-1 requires unique entries)"),
    ],
    ids=["number", "object-in-any-key-order", "array"],
)
def test_equal_non_string_entries_are_a_vg1_duplicate(codes: list, expected: str) -> None:
    assert verdict_grounds_errors(_base(reason_codes=codes)) == [expected]


def test_true_and_one_are_different_entries() -> None:
    errors = verdict_grounds_errors(_base(reason_codes=[True, 1]))
    assert [e.split(":", 1)[0] for e in errors] == ["reason_code_not_in_catalog"]


@pytest.mark.parametrize("code", [7, None, ["a"], {"k": "v"}], ids=["number", "null", "array", "object"])
def test_a_non_string_context_code_is_refused_under_vg7(code: object) -> None:
    doc = _base(
        status="fail",
        reason_codes=["INTEGRITY_OFFLINE_FAIL"],
        reason_context=[{"code": "INTEGRITY_OFFLINE_FAIL"}, {"code": code}],
    )
    assert verdict_grounds_errors(doc) == [
        f"reason_context_code_not_in_catalog: {code!r} (vocabulary loquitur.reason_codes.v1)"
    ]


# verdict-grounds.md section 1: the rules apply to any JSON value, schema-valid or not. A
# key_checks of another type is absent for VG-5, a context entry that names no code violates
# VG-7 and explains nothing for VG-6, and a reason_context that is not an array is absent.


@pytest.mark.parametrize(
    "checks", ["x", True, False, 1, 0, ""], ids=["string", "true", "false", "one", "zero", "empty-string"]
)
def test_a_key_checks_of_another_type_is_absent_for_a_pass(checks: object) -> None:
    assert [e.split(":", 1)[0] for e in verdict_grounds_errors(_base(key_checks=checks))] == ["pass_without_key_checks"]


@pytest.mark.parametrize("checks", [[{"check_id": "integrity"}], {"integrity": "pass"}], ids=["array", "object"])
def test_a_non_empty_array_or_object_of_key_checks_holds_for_a_pass(checks: object) -> None:
    assert verdict_grounds_errors(_base(key_checks=checks)) == []


@pytest.mark.parametrize(
    ("entry", "label"),
    [
        ("INTEGRITY_OFFLINE_FAIL", "'INTEGRITY_OFFLINE_FAIL' (not an object)"),
        (None, "None (not an object)"),
        ([{"code": "INTEGRITY_OFFLINE_FAIL"}], "[{'code': 'INTEGRITY_OFFLINE_FAIL'}] (not an object)"),
        ({"observed": "x"}, "an entry without a code"),
    ],
    ids=["string", "null", "array", "object-without-code"],
)
def test_a_context_entry_that_names_no_code_is_refused_under_vg7(entry: object, label: str) -> None:
    doc = _base(
        status="fail",
        reason_codes=["INTEGRITY_OFFLINE_FAIL"],
        reason_context=[{"code": "INTEGRITY_OFFLINE_FAIL"}, entry],
    )
    assert verdict_grounds_errors(doc) == [
        f"reason_context_code_not_in_catalog: {label} (vocabulary loquitur.reason_codes.v1)"
    ]


def test_a_context_entry_without_a_code_grounds_no_actionable_code() -> None:
    doc = _base(status="fail", reason_codes=["INTEGRITY_OFFLINE_FAIL"], reason_context=[{}])
    assert [e.split(":", 1)[0] for e in verdict_grounds_errors(doc)] == [
        "reason_context_code_not_in_catalog",
        "reason_context_missing",
    ]


@pytest.mark.parametrize(
    "context", [{"code": "INTEGRITY_OFFLINE_FAIL"}, "INTEGRITY_OFFLINE_FAIL", 7], ids=["object", "string", "number"]
)
def test_a_reason_context_that_is_not_an_array_is_absent(context: object) -> None:
    doc = _base(status="fail", reason_codes=["INTEGRITY_OFFLINE_FAIL"], reason_context=context)
    assert [e.split(":", 1)[0] for e in verdict_grounds_errors(doc)] == ["reason_context_missing"]


@pytest.mark.parametrize("summary", [None, [], "summary", 7], ids=["null", "array", "string", "number"])
def test_a_summary_that_is_not_an_object_cites_nothing(summary: object) -> None:
    assert verdict_grounds_errors(summary) == [  # type: ignore[arg-type]
        "reason_codes_absent: a verdict must cite the grounds for it"
    ]


@pytest.mark.parametrize(
    "status", ["PASS", "warn", None, 1, "unknown"], ids=["PASS", "warn", "null", "number", "unknown"]
)
def test_a_status_outside_the_vocabulary_is_named_before_the_contradiction(status: object) -> None:
    errors = verdict_grounds_errors(_base(status=status, key_checks=[{"check_id": "integrity"}]))
    assert [e.split(":", 1)[0] for e in errors] == ["verdict_outside_vocabulary", "status_contradicts_grounds"]
    assert (
        errors[0]
        == f"verdict_outside_vocabulary: status={status if isinstance(status, str) else repr(status)!r} is not one of pass, warning, review, fail"
    )


def test_a_status_inside_the_vocabulary_gets_no_vocabulary_diagnostic() -> None:
    errors = verdict_grounds_errors(_base(status="warning", key_checks=[{"check_id": "integrity"}]))
    assert [e.split(":", 1)[0] for e in errors] == ["status_contradicts_grounds"]


# ------------------------------------- a message about a value costs a bounded amount, never a recursion


def _nested(depth: int) -> list:
    value: list = []
    for _ in range(depth):
        value = [value]
    return value


def _cyclic() -> list:
    value: list = []
    value.append(value)
    return value


@pytest.mark.parametrize("where", ["reason_context", "reason_codes", "status", "context_code"])
@pytest.mark.parametrize("shape", ["deep", "wide", "cyclic", "long-string"])
def test_no_shape_of_value_makes_the_checker_raise_or_a_message_grow(where: str, shape: str) -> None:
    if where == "reason_codes" and shape == "cyclic":
        pytest.skip("reason_codes entries are compared by value (VG-1); a value that contains itself has none")
    value: object = {
        "deep": _nested(5000),
        "wide": list(range(100_000)),
        "cyclic": _cyclic(),
        "long-string": "x" * 1_000_000,
    }[shape]
    doc = _base(
        status="fail", reason_codes=["INTEGRITY_OFFLINE_FAIL"], reason_context=[{"code": "INTEGRITY_OFFLINE_FAIL"}]
    )
    if where == "reason_context":
        doc["reason_context"] = [{"code": "INTEGRITY_OFFLINE_FAIL"}, value]
    elif where == "reason_codes":
        doc["reason_codes"] = ["INTEGRITY_OFFLINE_FAIL", value]
    elif where == "status":
        doc["status"] = value
    else:
        doc["reason_context"] = [{"code": value}]
    errors = verdict_grounds_errors(doc)
    assert errors
    assert all(len(error) < 2_000 for error in errors)


def test_a_deeply_nested_context_entry_is_reported_under_vg7() -> None:
    doc = _base(
        status="fail",
        reason_codes=["INTEGRITY_OFFLINE_FAIL"],
        reason_context=[{"code": "INTEGRITY_OFFLINE_FAIL"}, _nested(5000)],
    )
    errors = verdict_grounds_errors(doc)
    assert [e.split(":", 1)[0] for e in errors] == ["reason_context_code_not_in_catalog"]
    assert "(not an object)" in errors[0]


def test_a_cyclic_context_entry_is_reported_under_vg7() -> None:
    doc = _base(
        status="fail",
        reason_codes=["INTEGRITY_OFFLINE_FAIL"],
        reason_context=[{"code": "INTEGRITY_OFFLINE_FAIL"}, _cyclic()],
    )
    assert [e.split(":", 1)[0] for e in verdict_grounds_errors(doc)] == ["reason_context_code_not_in_catalog"]
