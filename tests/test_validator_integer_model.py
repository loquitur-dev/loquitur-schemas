"""JSON Schema 2020-12 integers are values, not spellings.

Draft 2020-12 section 6.1.1 defines an integer as any number with a zero fractional part,
and the protocol says the same thing twice: ``bundle-objects.md`` requires ``1.0`` and
``1`` to be accepted identically, and ``canonicalization-and-hashing.md`` decides the
safe-integer range "by value ... regardless of spelling". RFC 8785 serializes ``2.0`` and
``2`` to the same bytes, so a validator that tells them apart gives the same committed
bytes two different verdicts.

A validator that tested ``isinstance(value, int)`` would reject every integer-valued float,
so a registry entry whose ``signature.payload_version`` is written ``2.0`` would be
schema-invalid and its signature, over bytes identical to the ``2`` spelling, would not
verify, while ``jsonschema``, ``loquitur-verify`` and ``loquitur-verify-ts`` all accept it.
``uniqueItems`` has the mirror-image trap: comparing ``json.dumps`` spellings counts
``[2, 2.0]`` as two distinct items.

The differential test at the end holds the validator to ``jsonschema``'s
``Draft202012Validator`` over every bundled example and fixture, with every integer leaf
re-spelled as a float, so the next spelling-sensitive keyword cannot hide.

Each test runs its whole table, the plain rows (``2``, ``2.5``, ``true``, distinct items,
documents without an integer leaf) beside the re-spelled ones, and compares the table at once,
so a test fails both if a re-spelled value is judged differently and if a plain one is.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from signing_kit import private_scalar, public_key_hex, sign_digest_hex

from loquitur.schemas.canonical import canonical_json_bytes
from loquitur.schemas.inventory import PUBLIC_SCHEMA_NAMES, load_schema_json
from loquitur.schemas.registry_signing import (
    _secp256k1_verify_digest,
    canonicalize_registry_entry_signing_payload,
)
from loquitur.schemas.validator import OBJECT_TYPE_TO_SCHEMA_NAME, _validate_value, validate_instance

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(object_type: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{object_type}.valid.json").read_text(encoding="utf-8"))


def _set(doc: dict[str, Any], path: tuple[str, ...], value: Any) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


# Every property the bundled schemas type as "integer", outside the registry-entry
# signature (covered by its own rows below). test_integer_fields_accept_by_value holds this
# list equal to the schemas before it runs a row, so a new integer field cannot be left out.
INTEGER_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("change_summary", ("snapshot_seq_current",)),
    ("change_summary", ("snapshot_seq_previous",)),
    ("change_summary", ("evidence_count_delta",)),
    ("coverage_summary", ("coverage", "required_present")),
    ("coverage_summary", ("coverage", "required_total")),
    ("coverage_summary", ("coverage", "recommended_present")),
    ("coverage_summary", ("coverage", "recommended_total")),
    ("lineage_summary", ("history_count",)),
    ("lineage_summary", ("latest_snapshot_seq",)),
    ("lineage_summary", ("current_snapshot_seq",)),
    ("lineage_summary", ("previous_snapshot_seq",)),
    ("verification_receipt", ("policy_version",)),
    ("verification_summary", ("policy_version",)),
)


def _integer_paths(schema: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    found: list[tuple[str, ...]] = []
    if not isinstance(schema, dict):
        return found
    declared = schema.get("type")
    if declared == "integer" or (isinstance(declared, list) and "integer" in declared):
        found.append(path)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, child in properties.items():
            found.extend(_integer_paths(child, (*path, name)))
    for child in schema.get("oneOf") or ():
        found.extend(_integer_paths(child, path))
    return found


def _declared_integer_fields() -> set[tuple[str, tuple[str, ...]]]:
    return {
        (object_type, path)
        for object_type, schema_name in OBJECT_TYPE_TO_SCHEMA_NAME.items()
        for path in _integer_paths(load_schema_json(schema_name))
    }


@pytest.mark.parametrize(
    ("object_type", "path"), INTEGER_FIELDS, ids=lambda v: ".".join(v) if isinstance(v, tuple) else v
)
def test_integer_fields_accept_by_value(object_type: str, path: tuple[str, ...]) -> None:
    # The table is every integer field of the bundled schemas, so a new one cannot be left out.
    assert _declared_integer_fields() == set(INTEGER_FIELDS) | {("registry_entry", ("signature", "payload_version"))}
    field = "$." + ".".join(path)
    got = {}
    for label, value in (("int", 2), ("integer-valued-float", 2.0), ("fractional", 2.5), ("bool", True)):
        result = validate_instance(object_type, _set(_fixture(object_type), path, value))
        got[label] = [(e.path, e.code) for e in result.errors]
    assert got == {
        "int": [],
        "integer-valued-float": [],
        "fractional": [(field, "type_mismatch")],
        "bool": [(field, "type_mismatch")],
    }


def test_a_receipt_policy_version_of_one_point_zero_validates_and_two_point_five_does_not() -> None:
    receipt = _fixture("verification_receipt")
    assert validate_instance("verification_receipt", receipt | {"policy_version": 1.0}).ok
    assert not validate_instance("verification_receipt", receipt | {"policy_version": 2.5}).ok


def _signed_with_ephemeral_key() -> tuple[dict[str, Any], str]:
    entry = json.loads((FIXTURES / "registry_entry.signed_catalog_demo.json").read_text(encoding="utf-8"))
    scalar = private_scalar()
    digest = hashlib.sha256(canonicalize_registry_entry_signing_payload(entry)).digest()
    entry["signature"] = dict(entry["signature"], signature=sign_digest_hex(digest, scalar))
    return entry, public_key_hex(scalar)


def test_registry_entry_payload_version_is_compared_by_value() -> None:
    entry, public_key_hex = _signed_with_ephemeral_key()
    got = {}
    for spelling in ("2", "2.0", "2e0", "2.5", "true"):
        text = json.dumps(entry).replace('"payload_version": 2', f'"payload_version": {spelling}')
        respelt = json.loads(text)
        valid = validate_instance("registry_entry", respelt).ok
        if valid:
            digest = hashlib.sha256(canonicalize_registry_entry_signing_payload(respelt)).digest()
            same_bytes = canonical_json_bytes(respelt) == canonical_json_bytes(entry)
            got[spelling] = (
                valid,
                same_bytes,
                _secp256k1_verify_digest(digest, respelt["signature"]["signature"], public_key_hex),
            )
        else:
            got[spelling] = (valid,)
    verified = (True, True, True)
    assert got == {"2": verified, "2.0": verified, "2e0": verified, "2.5": (False,), "true": (False,)}


def test_unique_items_compares_numbers_by_value() -> None:
    schema = {"type": "array", "uniqueItems": True}
    rows = [
        ([2, 2.0], False),
        ([2.0, 2], False),
        ([[1], [1.0]], False),
        ([{"a": 1}, {"a": 1.0}], False),
        ([0, -0.0], False),
        ([1, True], True),
        ([0, False], True),
        ([2, 2.5], True),
        (["2", 2], True),
    ]
    got = [(repr(items), not _validate_value(schema, items, "$")) for items, _ in rows]
    oracle = [(repr(items), jsonschema.Draft202012Validator(schema).is_valid(items)) for items, _ in rows]
    expected = [(repr(items), unique) for items, unique in rows]
    assert (got, oracle) == (expected, expected)


def _floated(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, list):
        return [_floated(item) for item in value]
    if isinstance(value, dict):
        return {key: _floated(item) for key, item in value.items()}
    return value


def _documents() -> list[tuple[str, str, Any]]:
    docs: list[tuple[str, str, Any]] = []
    for schema_name in PUBLIC_SCHEMA_NAMES:
        schema = load_schema_json(schema_name)
        if "example" in schema:
            docs.append((f"{schema_name}:example", schema_name, schema["example"]))
    for object_type, schema_name in OBJECT_TYPE_TO_SCHEMA_NAME.items():
        path = FIXTURES / f"{object_type}.valid.json"
        if path.exists():
            docs.append((f"{schema_name}:fixture", schema_name, json.loads(path.read_text(encoding="utf-8"))))
    return docs


def _has_integer_leaf(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, list):
        return any(_has_integer_leaf(item) for item in value)
    if isinstance(value, dict):
        return any(_has_integer_leaf(item) for item in value.values())
    return False


DOCUMENTS = _documents()


def test_validator_agrees_with_draft_2020_12() -> None:
    # The differential is not vacuous: enough documents carry an integer leaf to re-spell.
    assert sum(1 for _, _, doc in DOCUMENTS if _has_integer_leaf(doc)) >= 7
    disagreements = []
    for label, schema_name, doc in DOCUMENTS:
        for respell in (False, True):
            instance = _floated(doc) if respell else doc
            oracle = jsonschema.Draft202012Validator(load_schema_json(schema_name)).is_valid(instance)
            ours = validate_instance(schema_name, instance)
            if ours.ok is not oracle:
                spelling = "integers-as-floats" if respell else "as-written"
                disagreements.append((label, spelling, oracle, [(e.path, e.code) for e in ours.errors]))
    assert disagreements == []
