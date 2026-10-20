"""Adversarial and randomized coverage for the registry-entry signing surface.

``loquitur-schemas`` builds the message an issuer signs over a registry entry, so its
assurance cannot rest on fixtures alone: a single demo key and a handful of named fields
would leave the message with far shallower adversarial coverage than ``loquitur-verify``,
which checks signatures over it. The package signs nothing; the signatures below are made
by the test-only ``signing_kit`` with keys generated for the run.

Three properties are pinned here:

  1. **Exact signature coverage.** Mutating *any* field of a signed entry must
     invalidate the signature, except exactly the declared excluded set
     {signature, anchor, anchored_at}. Enumerated over every field, not sampled:
     a field silently dropped from the signed payload is a forgery primitive, and
     a field wrongly included breaks anchoring after signing.
  2. **Key binding.** A signature is valid only under the key that produced it,
     over randomly generated key pairs rather than one fixed key.
  3. **Fail-closed.** A hostile public key makes the ECDSA reference return false
     rather than raise.

Verification of a registry entry as a document (its contract, its signature step, the
issuer's authorization) is the verifiers' and is not exercised here; the signatures this
module checks are checked with the ``cryptography``-backed ECDSA reference over the
signing payload's digest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

import pytest
from signing_kit import private_scalar, public_key_hex, sign_digest_hex

from loquitur.schemas.registry_signing import (
    SIGNATURE_ALGORITHM,
    SIGNING_PAYLOAD_ID,
    SIGNING_PAYLOAD_VERSION,
    RegistrySigningError,
    _secp256k1_verify_digest,
    canonicalize_registry_entry_signing_payload,
    registry_entry_signing_payload,
)
from loquitur.schemas.signing_envelope import SIGNING_PAYLOAD_EXCLUDED_FIELDS
from loquitur.schemas.validator import calendar_instant_errors, is_calendar_instant, validate_instance

FIXTURES = Path(__file__).parent / "fixtures"
SEED = 20260722
ITERATIONS = int(os.environ.get("LOQUITUR_SIGNING_ITERATIONS", "16"))


def _base_entry() -> dict[str, Any]:
    entry = json.loads((FIXTURES / "registry_entry.valid.json").read_text(encoding="utf-8"))
    entry.pop("signature", None)
    return entry


def _keypair(rng: random.Random) -> tuple[int, str]:
    scalar = private_scalar(rng)
    return scalar, public_key_hex(scalar)


def _sign(entry: dict[str, Any], scalar: int, key_id: str | None = None) -> dict[str, Any]:
    """Sign the message this package builds, with an arbitrary key made for the run.

    The message is built first, so an entry the package refuses raises before any signing.
    """
    unsigned = dict(entry)
    unsigned.pop("signature", None)
    digest = hashlib.sha256(canonicalize_registry_entry_signing_payload(unsigned)).digest()
    signed = dict(unsigned)
    signed["signature"] = {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id or unsigned["issuer_key_id"],
        "payload_id": SIGNING_PAYLOAD_ID,
        "payload_version": SIGNING_PAYLOAD_VERSION,
        "signature": sign_digest_hex(digest, scalar),
    }
    return signed


def _mutate(value: Any, rng: random.Random) -> Any:
    if isinstance(value, str):
        return value + "x"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, list):
        return value + ["extra"] if value else ["extra"]
    if isinstance(value, dict):
        return {**value, "injected": "x"}
    if value is None:
        return "not-null"
    return "mutated"


def _verifies(entry: dict[str, Any], public_key_hex: str) -> bool:
    """The ECDSA reference over the signing payload's digest: the bytes a signer commits to."""
    signature = entry.get("signature")
    if not isinstance(signature, dict) or not isinstance(signature.get("signature"), str):
        return False
    digest = hashlib.sha256(canonicalize_registry_entry_signing_payload(entry)).digest()
    return _secp256k1_verify_digest(digest, signature["signature"], public_key_hex)


# --------------------------------------------------------------------------
# 1. exact signature coverage
# --------------------------------------------------------------------------


def test_signed_payload_contains_exactly_the_non_excluded_fields() -> None:
    """Structural ground truth: which fields enter the signed bytes.

    Deliberately NOT measured by mutating a signed entry and re-verifying: an
    out-of-schema mutation makes verification fail for *schema* reasons, which
    would be misread as "the signature covers this field". Comparing the entry
    keys against the signing payload keys separates the two concerns exactly.
    """
    entry = _base_entry()
    payload = registry_entry_signing_payload(entry)
    omitted = set(entry) - set(payload)
    unexpected = set(payload) - set(entry)

    assert omitted == set(SIGNING_PAYLOAD_EXCLUDED_FIELDS) & set(entry), (
        "fields missing from the signed payload do not match the declared exclusions: "
        f"omitted={sorted(omitted)} declared={sorted(SIGNING_PAYLOAD_EXCLUDED_FIELDS)}"
    )
    assert not unexpected, f"signed payload invents fields absent from the entry: {sorted(unexpected)}"
    assert set(payload), "signing payload is empty - nothing would be bound by the signature"


def test_mutating_any_signed_field_invalidates_the_signature() -> None:
    """Cryptographic consequence, over schema-valid alternatives only.

    Each mutation keeps the entry schema-valid, so a rejected signature can only
    mean the field is genuinely bound by the signature.
    """
    rng = random.Random(SEED)
    scalar, public_hex = _keypair(rng)
    entry = _base_entry()
    signed = _sign(entry, scalar)
    assert _verifies(signed, public_hex), "baseline signature must verify"

    alternatives: dict[str, Any] = {
        "asset_type": "fund_nav" if entry.get("asset_type") != "fund_nav" else "property",
        "workflow": "property_review" if entry.get("workflow") != "property_review" else "fund_nav_update",
        "verdict": "FAIL" if entry.get("verdict") != "FAIL" else "PASS",
        "disclosure_profile": (
            "partner_authorized_bundle"
            if entry.get("disclosure_profile") != "partner_authorized_bundle"
            else "minimal_public"
        ),
        "issued_at": "2030-01-01T00:00:00Z",
        "policy_version": "9.9.9",
        "reason_codes": ["INTEGRITY_OK", "FRESHNESS_OK"],
        "manifest_hash": "sha256:" + "0" * 64,
        "receipt_hash": "sha256:" + "1" * 64,
        "subject_ref_hash": "sha256:" + "2" * 64,
        "issuer_id": "issuer_other_synthetic",
        "registry_entry_id": "reg_other_synthetic_0001",
        "receipt_id": "vr_other_synthetic_0001",
        "policy_id": "policy.other",
    }
    tested = 0
    for field, replacement in alternatives.items():
        if field not in entry or entry[field] == replacement:
            continue
        mutated = copy.deepcopy(signed)
        mutated[field] = replacement
        assert not _verifies(mutated, public_hex), (
            f"field {field!r} is not bound by the signature: mutating it left the signature valid"
        )
        tested += 1
    assert tested >= 8, f"too few fields exercised ({tested}); the assertion would be vacuous"


def test_excluded_fields_can_be_attached_after_signing() -> None:
    """Anchoring happens after signing: it must not invalidate the issuer signature."""
    rng = random.Random(SEED + 1)
    scalar, public_hex = _keypair(rng)
    signed = _sign(_base_entry(), scalar)
    anchored = copy.deepcopy(signed)
    anchored["anchor"] = {
        "method": "blockchain_transaction",
        "system": "example:testnet",
        "anchor_reference": "0.0.1@1",
    }
    anchored["anchored_at"] = "2026-07-22T00:00:00Z"
    assert _verifies(anchored, public_hex), "attaching anchor metadata must not break the signature"


def test_removing_a_signed_field_invalidates_the_signature() -> None:
    rng = random.Random(SEED + 2)
    scalar, public_hex = _keypair(rng)
    signed = _sign(_base_entry(), scalar)
    for field in sorted(k for k in signed if k not in SIGNING_PAYLOAD_EXCLUDED_FIELDS):
        stripped = copy.deepcopy(signed)
        stripped.pop(field)
        try:
            assert not _verifies(stripped, public_hex), f"removing {field!r} left the signature valid"
        except RegistrySigningError:
            pass  # refusing to canonicalize an incomplete entry is also fail-closed


# --------------------------------------------------------------------------
# 2. key binding, over random keypairs
# --------------------------------------------------------------------------


def test_signatures_round_trip_under_randomised_keys() -> None:
    rng = random.Random(SEED + 3)
    for _ in range(ITERATIONS):
        scalar, public_hex = _keypair(rng)
        assert _verifies(_sign(_base_entry(), scalar), public_hex)


def test_signature_never_verifies_under_a_different_key() -> None:
    rng = random.Random(SEED + 4)
    for _ in range(ITERATIONS):
        scalar, _ = _keypair(rng)
        _, other_public_hex = _keypair(rng)
        assert not _verifies(_sign(_base_entry(), scalar), other_public_hex)


# --------------------------------------------------------------------------
# 3. fail-closed on hostile input
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "public_key_hex",
    ["", "04", "zz" * 65, "00" * 65, "04" + "11" * 64, "ff" * 32],
)
def test_the_ecdsa_reference_returns_false_on_hostile_public_keys_rather_than_raising(public_key_hex: str) -> None:
    rng = random.Random(SEED + 7)
    scalar, _ = _keypair(rng)
    signed = _sign(_base_entry(), scalar)
    try:
        verified = _verifies(signed, public_key_hex)
    except Exception as exc:  # noqa: BLE001 - the property under test
        raise AssertionError(f"the ECDSA reference raised on a hostile public key: {exc!r}") from exc
    assert verified is False


def test_randomised_signature_corruption_never_verifies() -> None:
    rng = random.Random(SEED + 8)
    scalar, public_hex = _keypair(rng)
    signed = _sign(_base_entry(), scalar)
    original = signed["signature"]["signature"]
    for _ in range(ITERATIONS):
        index = rng.randrange(len(original))
        replacement = rng.choice([c for c in "0123456789abcdef" if c != original[index].lower()])
        corrupted = copy.deepcopy(signed)
        corrupted["signature"]["signature"] = original[:index] + replacement + original[index + 1 :]
        assert not _verifies(corrupted, public_hex)


# --------------------------------------------------------------------------
# 4. no signing message for what the verifiers refuse at load
# --------------------------------------------------------------------------

# canonicalization-and-hashing.md, input strictness rule 8, the table in full.
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


def test_the_calendar_rule_reads_the_protocol_table() -> None:
    assert {instant: is_calendar_instant(instant) for instant in CALENDAR_TABLE} == CALENDAR_TABLE
    for not_an_instant in ("2026-05-10T00:00:00z", "2026-05-10 00:00:00Z", "2026-05-10T00:00:00Z\n", 20260510, None):
        assert is_calendar_instant(not_an_instant) is False


@pytest.mark.parametrize("field", ["issued_at", "effective_at", "anchored_at"])
def test_no_signing_message_for_an_instant_that_names_no_calendar_second(field: str) -> None:
    rng = random.Random(SEED + 7)
    scalar, _public_hex = _keypair(rng)
    got = {}
    for instant, is_instant in CALENDAR_TABLE.items():
        entry = _base_entry() | {field: instant}
        # The pattern admits every row; the validator adds the calendar rule, and it refuses
        # exactly the rows the signing message refuses.
        assert validate_instance("registry_entry", entry).ok is is_instant, instant
        assert bool(calendar_instant_errors("registry_entry", entry)) is (not is_instant)
        try:
            _sign(entry, scalar)
            got[instant] = True
        except RegistrySigningError as exc:
            assert f"$.{field}:calendar_instant" in str(exc)
            got[instant] = False
    assert got == CALENDAR_TABLE


@pytest.mark.parametrize(
    ("label", "change"),
    [
        ("noncharacter in a value", {"issuer_key_id": "key\ufdd0"}),
        ("noncharacter U+1FFFE in a value", {"policy_id": "policy\U0001fffe"}),
        ("lone surrogate in a value", {"policy_id": "policy\ud800"}),
    ],
)
def test_no_signing_message_for_a_value_that_breaks_input_strictness(label: str, change: dict[str, Any]) -> None:
    rng = random.Random(SEED + 8)
    scalar, _public_hex = _keypair(rng)
    entry = _base_entry() | change
    assert validate_instance("registry_entry", entry).ok, label
    with pytest.raises(RegistrySigningError, match="input strictness"):
        _sign(entry, scalar)
