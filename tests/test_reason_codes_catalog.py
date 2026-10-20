"""Tests for the reason codes description catalog.

Invariants this test suite enforces:

- All three audience narratives are present for every entry.
- JSON schema validation passes against the public catalog schema.
- The loader is idempotent (cached) and returns frozen dataclasses.
- Narrative content respects minimum quality bars (length, voice markers).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loquitur.schemas import (
    CATALOG_AUDIENCES,
    CATALOG_VERSION,
    CATALOG_VOCABULARY,
    ComplianceNarrative,
    ExecutiveNarrative,
    ReasonCodesCatalog,
    ReasonCodesCatalogError,
    TechnicalNarrative,
    catalog_data_path,
    load_reason_codes_catalog,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CATALOG_SCHEMA = PACKAGE_ROOT / "src" / "loquitur" / "schemas" / "data" / "reason_codes_catalog" / "schema.json"


# ---------------------------------------------------------------------------
# Catalog metadata invariants
# ---------------------------------------------------------------------------


def test_catalog_version_is_semver() -> None:
    """Catalog version is exposed as a semver-shaped string."""
    parts = CATALOG_VERSION.split(".")
    assert len(parts) == 3, f"CATALOG_VERSION must be major.minor.patch, got {CATALOG_VERSION}"
    for part in parts:
        assert part.isdigit(), f"CATALOG_VERSION component must be numeric: {part}"


def test_catalog_targets_canonical_vocabulary() -> None:
    """Catalog is paired with the canonical reason code vocabulary."""
    assert CATALOG_VOCABULARY == "loquitur.reason_codes.v1"


def test_catalog_audiences_are_fixed_set() -> None:
    """The three supported audiences are technical, compliance, executive."""
    assert CATALOG_AUDIENCES == ("technical", "compliance", "executive")


# ---------------------------------------------------------------------------
# Loader invariants
# ---------------------------------------------------------------------------


def test_load_returns_reason_codes_catalog_instance() -> None:
    catalog = load_reason_codes_catalog()
    assert isinstance(catalog, ReasonCodesCatalog)


def test_load_is_cached() -> None:
    """The loader caches the catalog: two calls return the same object."""
    first = load_reason_codes_catalog()
    second = load_reason_codes_catalog()
    assert first is second


def test_the_cached_catalog_cannot_be_changed() -> None:
    """Every caller shares the one cached catalog, so its mappings refuse assignment at every level."""
    catalog = load_reason_codes_catalog()
    entry = catalog.get("INTEGRITY_OK")
    with pytest.raises(TypeError):
        catalog.entries["INTEGRITY_OK"] = entry  # type: ignore[index]
    with pytest.raises(TypeError):
        del catalog.entries["INTEGRITY_OK"]  # type: ignore[attr-defined]
    templates = catalog.composition_templates
    with pytest.raises(TypeError):
        templates["technical"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        templates["technical"]["common"]["closing"]["PASS"] = "changed"  # type: ignore[index]
    assert catalog.get("INTEGRITY_OK") is entry
    assert dict(catalog.entries) == {code: catalog.get(code) for code in catalog}


def test_load_returns_metadata_aligned_with_module_constants() -> None:
    catalog = load_reason_codes_catalog()
    assert catalog.catalog_version == CATALOG_VERSION
    assert catalog.reason_code_vocabulary == CATALOG_VOCABULARY
    assert catalog.audiences == CATALOG_AUDIENCES


def test_load_returns_frozen_entries() -> None:
    """Catalog entries are frozen dataclasses; mutation must fail."""
    catalog = load_reason_codes_catalog()
    entry = catalog.get("INTEGRITY_OK")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        entry.code = "MUTATED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Per-entry structural invariants
# ---------------------------------------------------------------------------


def test_every_entry_has_all_three_audience_narratives() -> None:
    catalog = load_reason_codes_catalog()
    for code, entry in catalog.entries.items():
        assert isinstance(entry.technical, TechnicalNarrative), code
        assert isinstance(entry.compliance, ComplianceNarrative), code
        assert isinstance(entry.executive, ExecutiveNarrative), code


def test_every_entry_code_matches_map_key() -> None:
    """Catalog entry's ``code`` field equals its dict key."""
    catalog = load_reason_codes_catalog()
    for code, entry in catalog.entries.items():
        assert entry.code == code, f"key {code!r} but entry.code is {entry.code!r}"


# ---------------------------------------------------------------------------
# Narrative quality bars
# ---------------------------------------------------------------------------


def test_technical_headline_is_a_complete_sentence() -> None:
    """Technical headlines end with a period (sentence-shape sanity check)."""
    catalog = load_reason_codes_catalog()
    for code, entry in catalog.entries.items():
        h = entry.technical.headline
        assert h.endswith("."), f"{code} technical headline must end with period: {h!r}"


def test_technical_detail_has_minimum_substance() -> None:
    """Technical detail must be at least ~40 chars (matches schema minLength)."""
    catalog = load_reason_codes_catalog()
    for code, entry in catalog.entries.items():
        assert len(entry.technical.detail) >= 40, code


def test_compliance_consequence_uses_assertive_voice_markers() -> None:
    """Compliance consequence uses assertive voice consistently.

    Across all entries, the consequence text predominantly
    uses assertive language (must / cannot / do not / require / does not /
    is not). Soft-voice markers (should consider, may want to, perhaps,
    might be) should be rare and never alone.
    """
    catalog = load_reason_codes_catalog()
    soft_markers = ("should consider", "may want to", "perhaps", "might be")
    soft_hits = []
    for code, entry in catalog.entries.items():
        text = entry.compliance.consequence.lower()
        for marker in soft_markers:
            if marker in text:
                soft_hits.append((code, marker))

    # Soft markers are a smell, not always wrong (some codes are info-level
    # and warrant soft language). Cap the rate at 5% of entries to catch
    # systematic drift without forbidding legitimate softness.
    assert len(soft_hits) <= max(2, len(catalog.entries) // 20), (
        f"Too many compliance consequences using soft voice markers: "
        f"{soft_hits}. Compliance narratives should be assertive."
    )


def test_compliance_required_action_is_imperative() -> None:
    """required_action starts with an imperative verb (heuristic check)."""
    catalog = load_reason_codes_catalog()
    # Accept the most common imperative starts seen in the catalog.
    imperative_starts = (
        "Reject",
        "Require",
        "Investigate",
        "Determine",
        "Document",
        "Route",
        "Schedule",
        "Retry",
        "Either",
        "Continue",
        "Identify",
        "Surface",
        "Aggregate",
        "Ensure",
        "Review",
        "No action",
        "Treat",
        "If",
    )
    bad = []
    for code, entry in catalog.entries.items():
        first_word = entry.compliance.required_action.split(maxsplit=1)[0].rstrip(",.")
        if not entry.compliance.required_action.startswith(imperative_starts):
            bad.append((code, first_word))
    assert not bad, f"compliance.required_action must start with imperative voice: {bad}"


def test_executive_summary_avoids_technical_jargon() -> None:
    """Executive summaries should avoid SHA, RFC, hash-, schema-name jargon.

    Allowing some terms (for example 'verification', 'verification record') because
    they are not jargon. Disallowing terms that signal the audience is wrong.
    """
    catalog = load_reason_codes_catalog()
    forbidden_jargon = (
        "SHA-256",
        "RFC 8785",
        "RFC-8785",
        "JCS",
        "manifest.sha256",
        "p1.json",
        "canonical_input.json",
    )
    leaks = []
    for code, entry in catalog.entries.items():
        text = entry.executive.summary
        for token in forbidden_jargon:
            if token in text:
                leaks.append((code, token))
    assert not leaks, f"Executive narratives leak technical jargon: {leaks}"


def test_executive_summary_is_concise() -> None:
    """Executive summaries cap at the schema-declared upper bound."""
    catalog = load_reason_codes_catalog()
    for code, entry in catalog.entries.items():
        assert 30 <= len(entry.executive.summary) <= 400, (
            f"{code}: executive summary length {len(entry.executive.summary)} outside [30, 400]"
        )


# ---------------------------------------------------------------------------
# JSON schema validation
# ---------------------------------------------------------------------------


def test_bundled_catalog_validates_against_public_schema() -> None:
    """The bundled catalog passes its own JSON schema validation.

    This is a structural defense: schema and catalog are in the same package,
    a CI step that runs this test catches catalog drift early.
    """
    pytest.importorskip("jsonschema")
    import jsonschema  # type: ignore[import-not-found]

    schema = json.loads(CATALOG_SCHEMA.read_text(encoding="utf-8"))
    catalog_path = catalog_data_path()
    catalog_text = catalog_path.read_text(encoding="utf-8")
    catalog_data = json.loads(catalog_text)

    jsonschema.validate(catalog_data, schema)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_get_unknown_code_raises_clear_error() -> None:
    """A code the catalog does not hold raises ReasonCodesCatalogError."""
    catalog = load_reason_codes_catalog()
    with pytest.raises(ReasonCodesCatalogError, match="not present in catalog"):
        catalog.get("DEFINITELY_NOT_A_REAL_REASON_CODE")


def test_contains_works_for_string_lookup() -> None:
    catalog = load_reason_codes_catalog()
    assert "INTEGRITY_OK" in catalog
    assert "DEFINITELY_NOT_A_REAL_REASON_CODE" not in catalog
    assert 12345 not in catalog  # type: ignore[operator]


def test_iteration_yields_canonical_code_keys() -> None:
    catalog = load_reason_codes_catalog()
    codes_via_iter = set(catalog)
    codes_via_entries = set(catalog.entries)
    assert codes_via_iter == codes_via_entries
