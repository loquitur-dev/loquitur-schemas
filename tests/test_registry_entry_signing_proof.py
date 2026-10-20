from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loquitur.schemas.registry_signing import (
    SIGNATURE_ALGORITHM,
    SIGNING_DOMAIN_PREFIX,
    SIGNING_ENVELOPE_DOMAIN,
    SIGNING_PAYLOAD_EXCLUDED_FIELDS,
    SIGNING_PAYLOAD_ID,
    SIGNING_PAYLOAD_VERSION,
    _secp256k1_verify_digest_for_tests,
    canonicalize_registry_entry_signing_payload,
    registry_entry_signing_envelope,
    registry_entry_signing_payload,
    registry_entry_signing_payload_hash,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "registry_entry.catalog_valid.json").read_text(encoding="utf-8"))


def _signed_fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "registry_entry.signed_catalog_demo.json").read_text(encoding="utf-8"))


def _committed_public_key_hex() -> str:
    return str(
        json.loads((FIXTURES / "registry_demo_secp256k1_public_key.json").read_text(encoding="utf-8"))["public_key_hex"]
    )


def test_signing_payload_excludes_signature_anchor_and_anchored_at() -> None:
    entry = _fixture()
    payload = registry_entry_signing_payload(entry)

    assert SIGNING_PAYLOAD_ID == "registry_entry_signing_payload_v2"
    assert SIGNING_PAYLOAD_VERSION == 2
    assert SIGNING_PAYLOAD_EXCLUDED_FIELDS == frozenset({"signature", "anchor", "anchored_at"})
    assert set(SIGNING_PAYLOAD_EXCLUDED_FIELDS).isdisjoint(payload)
    assert payload["registry_entry_id"] == entry["registry_entry_id"]
    assert payload["receipt_hash"] == entry["receipt_hash"]
    assert payload["verdict"] == entry["verdict"]
    envelope = registry_entry_signing_envelope(entry)
    assert envelope["domain"] == SIGNING_ENVELOPE_DOMAIN
    assert envelope["payload_id"] == SIGNING_PAYLOAD_ID
    assert envelope["envelope_version"] == SIGNING_PAYLOAD_VERSION
    assert canonicalize_registry_entry_signing_payload(entry).startswith(SIGNING_DOMAIN_PREFIX)


def test_signing_payload_hash_ignores_post_signature_and_anchor_fields() -> None:
    entry = _fixture()
    post_anchor = entry | {
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": "demo-key-2",
            "payload_id": SIGNING_PAYLOAD_ID,
            "payload_version": SIGNING_PAYLOAD_VERSION,
            "signature": "00" * 64,
        },
        "anchor": {
            "method": "blockchain_transaction",
            "system": "example:testnet",
            "anchor_reference": "tx-demo",
        },
        "anchored_at": "2026-04-29T13:00:00Z",
    }

    assert registry_entry_signing_payload_hash(entry) == registry_entry_signing_payload_hash(post_anchor)
    assert canonicalize_registry_entry_signing_payload(entry) == canonicalize_registry_entry_signing_payload(
        post_anchor
    )


def test_signing_payload_hash_changes_when_commitment_changes() -> None:
    entry = _fixture()

    assert registry_entry_signing_payload_hash(entry) != registry_entry_signing_payload_hash(
        entry | {"verdict": "FAIL"}
    )
    assert registry_entry_signing_payload_hash(entry) != registry_entry_signing_payload_hash(
        entry | {"receipt_hash": "sha256:" + "d" * 64}
    )
    assert registry_entry_signing_payload_hash(entry) != registry_entry_signing_payload_hash(
        entry | {"reason_codes": ["MARK_STALE"]}
    )


def test_demo_signature_self_check_uses_expected_public_key_without_exposing_verifier_contract() -> None:
    """The committed golden is proved by verifying it, not by re-signing it.

    The public key comes from the committed *public* fixture. A public key is not a
    secret and is all verification needs, so the assertion depends on no private key.
    """

    entry = _fixture()
    signed = _signed_fixture()
    digest = hashlib.sha256(canonicalize_registry_entry_signing_payload(entry)).digest()
    assert _secp256k1_verify_digest_for_tests(
        digest,
        signed["signature"]["signature"],
        _committed_public_key_hex(),
    )


def test_demo_signature_self_check_fails_for_tampered_commitment_digest() -> None:
    signed = _signed_fixture()
    tampered = _fixture() | {"verdict": "FAIL"}
    digest = hashlib.sha256(canonicalize_registry_entry_signing_payload(tampered)).digest()

    assert not _secp256k1_verify_digest_for_tests(
        digest,
        signed["signature"]["signature"],
        _committed_public_key_hex(),
    )


def test_the_package_exports_no_earlier_signing_payload() -> None:
    import loquitur.schemas as package
    import loquitur.schemas.registry_signing as signing
    import loquitur.schemas.signing_envelope as envelope

    for module in (package, signing, envelope):
        leftovers = sorted(name for name in dir(module) if "legacy" in name.lower() or name.endswith("_v1"))
        assert leftovers == [], f"{module.__name__} still names {leftovers}"
    assert "registry_entry_signing_payload_v1" not in repr(vars(envelope).values())
