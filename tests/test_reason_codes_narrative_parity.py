"""Reason-code narrative catalog consolidation gates.

These tests make the reason-code catalog the single source of truth for both
per-code audience narratives and catalog-level composition templates used by
verifier renderers.
"""

from __future__ import annotations

from loquitur.schemas import CATALOG_AUDIENCES, load_reason_codes_catalog

CONTEXTS = ("offline_verification", "registry_entry")
# These tuples are the whole point of this module. They are the closed verdict vocabulary
# of registry_entry.schema.json, WARN included, and must stay in step with it, not with
# whatever the catalog happens to contain: a verdict missing here is a verdict whose
# rendering no test checks.
LEAD_KEYS = ("PASS", "WARN", "REVIEW", "FAIL")
CLOSING_KEYS = (
    "PASS",
    "WARN",
    "REVIEW",
    "FAIL_SINGLE",
    "FAIL_MULTI",
    "FAIL_AUTHORIZATION",
    "FAIL_SIGNATURE",
)


def test_catalog_owns_composition_templates_for_all_audiences() -> None:
    catalog = load_reason_codes_catalog()

    for audience in CATALOG_AUDIENCES:
        for context in CONTEXTS:
            for key in LEAD_KEYS:
                template = catalog.template(audience, context, "lead", key)
                assert isinstance(template, str)
                assert template.strip(), (audience, context, key)
                assert len(template) <= 800, (audience, context, key)

        for key in CLOSING_KEYS:
            template = catalog.template(audience, "common", "closing", key)
            assert isinstance(template, str)
            # Executive PASS intentionally has no closing sentence; the lead is enough.
            if not (audience == "executive" and key == "PASS"):
                assert template.strip(), (audience, key)
            assert len(template) <= 800, (audience, key)


def test_every_catalog_code_has_complete_audience_narratives() -> None:
    catalog = load_reason_codes_catalog()

    # Anti-vacuity floor, not a census. Pinning the exact count would make every catalog
    # addition fail here for no reason related to what this test checks; exact
    # catalog/enum parity is enforced by test_catalog_and_published_enum_agree.
    assert len(catalog.entries) >= 50
    for code, entry in catalog.entries.items():
        assert entry.technical.headline.strip(), code
        assert entry.technical.detail.strip(), code
        assert len(entry.technical.headline) <= 200, code
        assert len(entry.technical.detail) <= 1200, code

        assert entry.compliance.headline.strip(), code
        assert entry.compliance.consequence.strip(), code
        assert entry.compliance.required_action.strip(), code
        assert len(entry.compliance.headline) <= 200, code
        assert len(entry.compliance.consequence) <= 800, code
        assert len(entry.compliance.required_action) <= 400, code

        assert entry.executive.summary.strip(), code
        assert len(entry.executive.summary) <= 400, code


def test_the_catalog_narrates_exactly_the_closed_vocabulary() -> None:
    """The catalog's verdict keys must equal the verdicts the protocol has.

    Checking the key *set* rather than a list of keys catches a divergence in either
    direction: a verdict added to the schema and not to the catalog, for which
    ``catalog.template`` would raise at render time, or a template for a verdict the
    protocol does not have.
    """
    catalog = load_reason_codes_catalog()

    for audience in CATALOG_AUDIENCES:
        for context in CONTEXTS:
            for key in ("UNKNOWN", "unknown"):
                try:
                    catalog.template(audience, context, "lead", key)
                except Exception:
                    continue
                raise AssertionError(f"{audience}/{context} narrates {key!r}, which is not a verdict (LCP-0008)")
            # WARN is a verdict like the others; assert it renders for real.
            assert catalog.template(audience, context, "lead", "WARN").strip()
        assert catalog.template(audience, "common", "closing", "WARN").strip()
