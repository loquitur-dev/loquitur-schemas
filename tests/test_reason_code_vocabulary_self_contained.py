"""The reason-code vocabulary must be verifiable from what this package ships.

Catalog parity is the catalog's central invariant: every code a schema allows has exactly one
catalog entry, and the catalog describes no code a schema refuses. Everything asserted here
uses only files inside this package, so the invariant holds in any checkout, in CI and in an
integrator's environment.

The artifacts must agree because they are consumed by different parties for the same
purpose: ``registry_entry.schema.json``, ``verification_receipt.schema.json`` and
``verification_summary.schema.json`` each tell a verifier which reason codes the object may
legally carry, and the catalog tells a human what each one means. A code in
the schema but not the catalog renders as a runtime error in the narrative layer; a
code in the catalog but not the schema is a promise the contract will reject.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loquitur.schemas import CATALOG_AUDIENCES, load_reason_codes_catalog

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DATA = PACKAGE_ROOT / "src" / "loquitur" / "schemas" / "data"
REGISTRY_ENTRY_SCHEMA = DATA / "registry_entry.schema.json"


def _published_enum() -> set[str]:
    schema = json.loads(REGISTRY_ENTRY_SCHEMA.read_text(encoding="utf-8"))
    enum = schema["properties"]["reason_codes"]["items"]["enum"]
    assert enum, "the published enum is empty; every comparison below would be vacuous"
    return set(enum)


def _catalog_codes() -> set[str]:
    codes = set(load_reason_codes_catalog().entries)
    assert codes, "the catalog is empty; every comparison below would be vacuous"
    return codes


def test_catalog_and_published_enum_agree() -> None:
    """The catalog and the registry entry schema's enum list the same reason codes."""
    catalog, enum = _catalog_codes(), _published_enum()

    missing_from_catalog = sorted(enum - catalog)
    assert not missing_from_catalog, (
        f"{len(missing_from_catalog)} reason codes are legal in registry_entry.schema.json "
        f"but absent from the catalog: {missing_from_catalog}. An entry carrying one of "
        "these validates and then fails to render, because the narrative layer has no "
        "text for it."
    )

    missing_from_enum = sorted(catalog - enum)
    assert not missing_from_enum, (
        f"{len(missing_from_enum)} reason codes are described in the catalog but are not "
        f"legal in registry_entry.schema.json: {missing_from_enum}. The catalog is "
        "promising an explanation for a code the closed contract will reject."
    )


# Every published object that carries a copy of the closed reason-code vocabulary. Three
# hand-maintained copies of one key set drift apart unless something binds each of them.
VOCABULARY_CARRIERS = (
    "registry_entry.schema.json",
    "verification_receipt.schema.json",
    "verification_summary.schema.json",
)


def _carried_enum(schema: dict) -> list[str]:
    return list(schema["properties"]["reason_codes"]["items"]["enum"])


def _drift(enum: list[str], catalog: set[str]) -> dict[str, list[str]]:
    return {
        "missing_from_catalog": sorted(set(enum) - catalog),
        "missing_from_enum": sorted(catalog - set(enum)),
        "repeated_in_enum": sorted({code for code in enum if enum.count(code) > 1}),
    }


@pytest.mark.parametrize("schema_name", VOCABULARY_CARRIERS)
def test_every_copy_of_the_vocabulary_is_the_catalog_key_set(schema_name: str) -> None:
    schema = json.loads((DATA / schema_name).read_text(encoding="utf-8"))
    enum = _carried_enum(schema)
    assert enum, f"{schema_name} carries an empty enum; the comparison would be vacuous"
    catalog = _catalog_codes()
    assert _drift(enum, catalog) == {"missing_from_catalog": [], "missing_from_enum": [], "repeated_in_enum": []}
    # The comparison sees drift in each direction: one code dropped, one invented.
    assert _drift(enum[1:], catalog)["missing_from_enum"] == [enum[0]]
    assert _drift(enum + ["NOT_A_CATALOG_CODE"], catalog)["missing_from_catalog"] == ["NOT_A_CATALOG_CODE"]


def test_every_published_code_renders_for_every_audience() -> None:
    """A code a verifier may emit must have text for every audience that reads a report.

    Presence in the catalog is not enough: an entry with a missing audience block
    surfaces as an empty section in a compliance report, which reads as "nothing to say"
    rather than "we failed to say it".
    """
    catalog = load_reason_codes_catalog()
    incomplete: list[str] = []
    for code in sorted(_published_enum()):
        entry = catalog.entries[code]
        for audience in CATALOG_AUDIENCES:
            block = getattr(entry, audience, None)
            if not block:
                incomplete.append(f"{code}:{audience}")
    assert not incomplete, f"catalog entries missing audience narrative: {incomplete}"


def _catalog_schema_enum(field: str) -> set[str]:
    """Read a closed vocabulary from the catalog's own schema.

    Derived, never transcribed: a test that encodes its author's assumption rather than
    the artifact's contract fails for the wrong reason, or worse, passes for the wrong
    reason.
    """
    schema = json.loads((DATA / "reason_codes_catalog" / "schema.json").read_text(encoding="utf-8"))
    values = set(schema["$defs"]["CatalogEntry"]["properties"][field]["enum"])
    assert values, f"{field} enum is empty in the catalog schema"
    return values


def test_every_published_code_declares_a_category_the_schema_allows() -> None:
    """Categories drive report ordering, and the allowed set is closed.

    loquitur-verify orders active reason codes by category
    (narrative._CANONICAL_CATEGORY_ORDER). A code whose category is outside that list
    sorts to the end of the report regardless of severity, so introducing a category
    must be a deliberate change to the catalog schema, visible here, rather than a
    side effect of adding one code.
    """
    catalog = load_reason_codes_catalog()
    allowed = _catalog_schema_enum("category")
    unexpected = sorted(
        (code, catalog.entries[code].category)
        for code in _published_enum()
        if catalog.entries[code].category not in allowed
    )
    assert not unexpected, f"categories outside the closed set {sorted(allowed)}: {unexpected}"


def test_severity_is_drawn_from_the_closed_set_the_schema_declares() -> None:
    catalog = load_reason_codes_catalog()
    allowed = _catalog_schema_enum("severity")
    unexpected = sorted(
        (code, catalog.entries[code].severity)
        for code in _published_enum()
        if catalog.entries[code].severity not in allowed
    )
    assert not unexpected, f"severities outside the closed set {sorted(allowed)}: {unexpected}"
