"""The validator holds every instant to the calendar, as the verifiers and the signing gate do.

canonicalization-and-hashing.md, input strictness rule 8: every string a published schema holds
to the instant form ``YYYY-MM-DDTHH:MM:SSZ`` names a real UTC second, in the registry entry, the
trust registry and the verification receipt, used or not. The instant pattern admits February 30,
April 31, February 29 of a common year, second 60 and year 0000, so the rule is applied on top of
the pattern: ``validate_instance``, ``validate_file``, ``validate_by_object_type`` and the
``loquitur-schema-validate`` command refuse a document that carries such a string, as the
verifiers refuse it at load and the signing gate refuses to sign it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from loquitur.schemas.canonical import RegistryCanonicalizationError, registry_entry_hash
from loquitur.schemas.cli import main
from loquitur.schemas.inventory import load_schema_json
from loquitur.schemas.validator import (
    INSTANT_PATTERN,
    calendar_instant_errors,
    validate_by_object_type,
    validate_file,
    validate_instance,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The table of input strictness rule 8, in full.
CALENDAR_TABLE = {
    "2026-05-10T00:00:00Z": True,
    "2024-02-29T12:00:00Z": True,
    "2026-12-31T23:59:59Z": True,
    "2026-02-29T12:00:00Z": False,
    "2026-02-30T00:00:00Z": False,
    "2026-04-31T00:00:00Z": False,
    "2026-04-29T12:00:60Z": False,
    "0000-01-01T00:00:00Z": False,
    "2000-02-29T00:00:00Z": True,
    "1900-02-29T00:00:00Z": False,
    "2100-02-29T00:00:00Z": False,
}

# Every member each schema holds to the instant pattern, as a path into the valid fixture.
INSTANT_MEMBERS: dict[str, tuple[tuple[str | int, ...], ...]] = {
    "registry_entry": (("issued_at",), ("effective_at",), ("anchored_at",)),
    "trust_registry": (
        ("issued_at",),
        ("effective_at",),
        ("expires_at",),
        ("entries", 0, "effective_from"),
        ("entries", 0, "expires_at"),
        ("entries", 0, "revoked_at"),
    ),
    "verification_receipt": (("verified_at",),),
}


def _fixture(object_type: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FIXTURES / f"{object_type}.valid.json").read_text(encoding="utf-8"))
    return document


def _with(document: dict[str, Any], member: tuple[str | int, ...], value: str) -> dict[str, Any]:
    changed = copy.deepcopy(document)
    target: Any = changed
    for step in member[:-1]:
        target = target[step]
    target[member[-1]] = value
    return changed


def _json_path(member: tuple[str | int, ...]) -> str:
    return "$" + "".join(f"[{step}]" if isinstance(step, int) else f".{step}" for step in member)


def _schema_instant_paths(node: Any, path: str = "$") -> list[str]:
    """Where a schema holds a string to the instant pattern, as validator paths with ``[0]``."""

    if not isinstance(node, dict):
        return []
    found = [path] if node.get("pattern") == INSTANT_PATTERN else []
    for name, child in (node.get("properties") or {}).items():
        found += _schema_instant_paths(child, f"{path}.{name}")
    if isinstance(node.get("items"), dict):
        found += _schema_instant_paths(node["items"], f"{path}[0]")
    return found


def test_the_table_covers_every_instant_the_schemas_declare() -> None:
    # A schema that gains an instant member gains a row here, or this fails.
    for object_type, members in INSTANT_MEMBERS.items():
        declared = sorted(_schema_instant_paths(load_schema_json(f"{object_type}.schema.json")))
        assert declared == sorted(_json_path(member) for member in members), object_type
    for object_type in ("verification_summary", "change_summary", "coverage_summary", "lineage_summary"):
        assert _schema_instant_paths(load_schema_json(f"{object_type}.schema.json")) == [], object_type


@pytest.mark.parametrize(
    ("object_type", "member"),
    [(object_type, member) for object_type, members in INSTANT_MEMBERS.items() for member in members],
    ids=lambda value: value if isinstance(value, str) else _json_path(value),
)
def test_validate_instance_refuses_an_instant_that_names_no_calendar_second(
    object_type: str, member: tuple[str | int, ...]
) -> None:
    base = _fixture(object_type)
    assert validate_instance(object_type, base).ok
    for instant, is_instant in CALENDAR_TABLE.items():
        result = validate_instance(object_type, _with(base, member, instant))
        assert result.ok is is_instant, instant
        if not is_instant:
            assert [error.to_dict() for error in result.errors] == [
                {
                    "path": _json_path(member),
                    "code": "calendar_instant",
                    "message": f"string at {_json_path(member)} names no calendar instant",
                    "expected": "a real UTC second, YYYY-MM-DDTHH:MM:SSZ",
                    "actual": instant,
                }
            ]


def test_a_string_outside_the_instant_form_is_a_pattern_error_only() -> None:
    entry = _fixture("registry_entry")
    for not_the_form in (
        "2026-13-01T00:00:00Z",
        "2026-02-30T00:00:00z",
        "2026-02-30 00:00:00Z",
        "2026-02-30T24:00:00Z",
    ):
        changed = _with(entry, ("issued_at",), not_the_form)
        result = validate_instance("registry_entry", changed)
        assert [error.code for error in result.errors] == ["pattern_mismatch"], not_the_form
        # The standalone helper reports the string whether or not it is in the form.
        helper = calendar_instant_errors("registry_entry", changed)
        assert [error.code for error in helper] == ["calendar_instant"], not_the_form


def test_the_calendar_errors_sit_beside_the_other_errors() -> None:
    entry = _with(_fixture("registry_entry"), ("issued_at",), "2026-02-30T00:00:00Z") | {"extra": 1}
    assert sorted((error.path, error.code) for error in validate_instance("registry_entry", entry).errors) == [
        ("$.extra", "additional_property"),
        ("$.issued_at", "calendar_instant"),
    ]


def test_every_entry_point_refuses_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = _with(_fixture("registry_entry"), ("issued_at",), "2026-02-30T00:00:00Z")
    good = _with(_fixture("registry_entry"), ("issued_at",), "2028-02-29T12:00:00Z")
    bad_path, good_path = tmp_path / "bad.json", tmp_path / "good.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    good_path.write_text(json.dumps(good), encoding="utf-8")

    assert validate_by_object_type(bad).ok is False
    assert validate_by_object_type(good).ok is True
    assert validate_file("registry_entry", bad_path).ok is False
    assert validate_file("registry_entry", good_path).ok is True

    assert main(["validate", "registry_entry", str(bad_path)]) == 1
    out = capsys.readouterr().out
    assert "schema validation failed: registry_entry.schema.json" in out
    assert "- $.issued_at: calendar_instant: string at $.issued_at names no calendar instant" in out
    assert main(["validate", "registry_entry", str(bad_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert [(error["path"], error["code"]) for error in report["errors"]] == [("$.issued_at", "calendar_instant")]
    assert main(["validate", "registry_entry", str(good_path)]) == 0
    assert "schema validation ok" in capsys.readouterr().out

    # The digest of an entry the verifiers refuse at load is not computed either.
    with pytest.raises(RegistryCanonicalizationError, match=r"\$\.issued_at:calendar_instant"):
        registry_entry_hash(bad)
    assert registry_entry_hash(good).startswith("sha256:")


def test_the_summary_evaluation_clock_is_outside_the_rule() -> None:
    # Rule 8 names the registry entry, the trust registry and the receipt; the summary's
    # evaluation clock has its own form (fractional seconds, offsets) and its own pattern.
    summary = _fixture("verification_summary")
    clock = load_schema_json("verification_summary.schema.json")["properties"]["policy_checks"]["properties"][
        "evaluation_clock_iso"
    ]
    assert clock["pattern"] != INSTANT_PATTERN
    summary["policy_checks"]["evaluation_clock_iso"] = "2026-02-30T00:00:00Z"
    assert validate_instance("verification_summary", summary).ok
