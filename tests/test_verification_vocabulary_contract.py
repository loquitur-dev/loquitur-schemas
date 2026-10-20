from __future__ import annotations

import json
import re
from pathlib import Path

from loquitur.schemas.verification_vocabulary import (
    REGISTRY_VERDICTS,
    STATUS_TO_REGISTRY_VERDICT,
    VERIFICATION_STATUSES,
)

ROOT = Path(__file__).resolve().parents[1]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "src/loquitur/schemas/data" / name).read_text(encoding="utf-8"))


def test_receipt_and_summary_status_are_the_same_closed_enum() -> None:
    receipt = _schema("verification_receipt.schema.json")
    summary = _schema("verification_summary.schema.json")
    assert tuple(receipt["properties"]["status"]["enum"]) == VERIFICATION_STATUSES
    assert tuple(summary["properties"]["status"]["enum"]) == VERIFICATION_STATUSES


def test_registry_verdict_and_mapping_are_closed() -> None:
    registry = _schema("registry_entry.schema.json")
    assert tuple(registry["properties"]["verdict"]["enum"]) == REGISTRY_VERDICTS
    assert tuple(STATUS_TO_REGISTRY_VERDICT) == VERIFICATION_STATUSES
    # `unknown` is not a status (LCP-0008): it would map to no verdict. The mapping is
    # total: every status resolves, and no caller handles a null.
    assert "unknown" not in STATUS_TO_REGISTRY_VERDICT
    assert all(value is not None for value in STATUS_TO_REGISTRY_VERDICT.values())
    assert set(STATUS_TO_REGISTRY_VERDICT.values()) == set(REGISTRY_VERDICTS)


def test_readme_does_not_claim_receipt_status_is_free_string() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "receipt status is not a free string" in readme
    assert "intentionally not enum-constrained" not in readme
    assert "planned for `0.2.0`" not in readme


def test_readme_status_vocabulary_matches_the_closed_constant() -> None:
    """The README is the packaged long description, so a stale vocabulary ships with it.

    The README travels inside the distribution, so drift would become public the moment
    the package is uploaded, with no further chance to catch it: a vocabulary listing a
    fifth value would tell an integrator on the project page to build a producer emitting
    a value every validator rejects. This binds the prose to the constant.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quoted = re.findall(r"`((?:pass|warning|review|fail|unknown)(?:\s*\|\s*\w+)+)`", readme)
    assert quoted, "README states no status vocabulary, so this gate would check nothing"
    for listing in quoted:
        values = tuple(part.strip() for part in listing.split("|"))
        assert values == VERIFICATION_STATUSES, (
            f"README states {values} but the closed vocabulary is {VERIFICATION_STATUSES}"
        )
