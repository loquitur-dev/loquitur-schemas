from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loquitur.schemas.canonical import (
    RegistryCanonicalizationError,
    canonicalize_registry_entry,
    registry_entry_hash,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "registry_entry.catalog_valid.json").read_text(encoding="utf-8"))


def _reverse_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _reverse_mapping(value[key]) for key in reversed(list(value.keys()))}
    if isinstance(value, list):
        return [_reverse_mapping(item) for item in value]
    return value


def test_registry_entry_canonicalization_is_minified_and_stable() -> None:
    entry = _fixture()

    canonical = canonicalize_registry_entry(entry)

    assert isinstance(canonical, bytes)
    assert canonical.startswith(b"{")
    assert b": " not in canonical
    assert b", " not in canonical
    assert json.loads(canonical.decode("utf-8")) == entry


def test_registry_entry_hash_is_field_order_invariant() -> None:
    entry = _fixture()
    reordered = _reverse_mapping(entry)

    assert list(reordered.keys()) != list(entry.keys())
    assert canonicalize_registry_entry(entry) == canonicalize_registry_entry(reordered)
    assert registry_entry_hash(entry) == registry_entry_hash(reordered)
    assert registry_entry_hash(entry).startswith("sha256:")
    assert len(registry_entry_hash(entry)) == len("sha256:") + 64


def test_registry_entry_hash_changes_when_commitment_content_is_tampered() -> None:
    entry = _fixture()
    tampered = entry | {"verdict": "FAIL"}

    assert registry_entry_hash(entry) != registry_entry_hash(tampered)


def test_registry_entry_hash_changes_when_reason_codes_change() -> None:
    entry = _fixture()
    tampered = entry | {"reason_codes": ["MARK_STALE"]}

    assert registry_entry_hash(entry) != registry_entry_hash(tampered)


def test_registry_entry_hash_includes_optional_signature_and_anchor_as_provided() -> None:
    entry = _fixture()
    signed_and_anchored = entry | {
        "signature": {
            "algorithm": "secp256k1_ecdsa_sha256",
            "key_id": "demo-key-2",
            "payload_id": "registry_entry_signing_payload_v2",
            "payload_version": 2,
            "signature": "a36e1f293f0c2207b3b1139fce4c3d50854e5af50000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        },
        "anchor": {
            "method": "blockchain_transaction",
            "system": "example:testnet",
            "anchor_reference": "tx-demo-placeholder",
        },
        "anchored_at": "2026-04-29T12:30:00Z",
    }

    assert registry_entry_hash(entry) != registry_entry_hash(signed_and_anchored)


def test_invalid_registry_entry_is_not_canonicalized() -> None:
    invalid = _fixture() | {"valuation_amount": 35000000}

    with pytest.raises(RegistryCanonicalizationError) as excinfo:
        canonicalize_registry_entry(invalid)

    message = str(excinfo.value)
    assert "invalid registry_entry" in message
    assert "valuation_amount" in message


def test_non_mapping_registry_entry_is_rejected() -> None:
    with pytest.raises(RegistryCanonicalizationError):
        canonicalize_registry_entry(["not", "an", "object"])  # type: ignore[arg-type]
