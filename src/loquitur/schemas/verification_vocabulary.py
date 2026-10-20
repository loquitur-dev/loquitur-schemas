"""Closed verification vocabularies for Loquitur protocol release 0.1."""

from __future__ import annotations

VERIFICATION_VOCABULARY_PROFILE = "loquitur.verification_vocabularies.v0.1"

# Four statuses, one per catalog severity (loquitur-protocol verification-vocabularies.md,
# LCP-0008). A verdict cites at least one reason code and its status is the status of the
# most severe code it cites, so every status has grounds. The cases in which verification
# cannot run carry reason codes of severity `review`; there is no status that names no
# reason.
VERIFICATION_STATUSES: tuple[str, ...] = ("pass", "warning", "review", "fail")
REGISTRY_VERDICTS: tuple[str, ...] = ("PASS", "WARN", "REVIEW", "FAIL")

# Total: every verification status has exactly one registry verdict, hence `str` rather
# than `str | None`.
STATUS_TO_REGISTRY_VERDICT: dict[str, str] = {
    "pass": "PASS",
    "warning": "WARN",
    "review": "REVIEW",
    "fail": "FAIL",
}


def verification_status_supported(value: object) -> bool:
    """Return whether ``value`` is a status of the closed verification vocabulary."""
    return isinstance(value, str) and value in VERIFICATION_STATUSES


def registry_verdict_supported(value: object) -> bool:
    """Return whether ``value`` is a verdict of the closed registry vocabulary."""
    return isinstance(value, str) and value in REGISTRY_VERDICTS
