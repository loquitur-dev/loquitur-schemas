"""Normative registry-entry signing envelope v2.

The signed message is not the bare registry entry. It is a fixed binary domain
prefix followed by the RFC 8785 canonical encoding of a closed envelope that
binds the protocol domain, envelope version, payload identity, payload schema,
signature algorithm and filtered registry-entry payload.

The protocol defines no earlier signing payload: a signature object without
``payload_id`` and ``payload_version`` breaks the registry entry's contract.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .canonical import canonical_json_bytes, sha256_uri

SIGNATURE_ALGORITHM = "secp256k1_ecdsa_sha256"
SIGNING_PAYLOAD_ID = "registry_entry_signing_payload_v2"
SIGNING_PAYLOAD_VERSION = 2
SIGNING_ENVELOPE_DOMAIN = "org.loquitur.protocol.registry-entry-signature"
SIGNING_ENVELOPE_SCHEMA = "loquitur.signing_envelope.v2"
SIGNING_PAYLOAD_SCHEMA = "loquitur.registry_entry.v1"
SIGNING_DOMAIN_PREFIX = b"LOQUITUR\x00REGISTRY_ENTRY\x00SIGNATURE\x00V2\x00"
SIGNING_PAYLOAD_EXCLUDED_FIELDS = frozenset({"signature", "anchor", "anchored_at"})


def registry_entry_signing_payload(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the registry-entry fields the issuer signature commits to."""

    return {key: value for key, value in dict(entry).items() if key not in SIGNING_PAYLOAD_EXCLUDED_FIELDS}


def registry_entry_signing_envelope(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the closed, domain-separated signing envelope object."""

    return {
        "domain": SIGNING_ENVELOPE_DOMAIN,
        "envelope_schema": SIGNING_ENVELOPE_SCHEMA,
        "envelope_version": SIGNING_PAYLOAD_VERSION,
        "payload": registry_entry_signing_payload(entry),
        "payload_id": SIGNING_PAYLOAD_ID,
        "payload_schema": SIGNING_PAYLOAD_SCHEMA,
        "signature_algorithm": SIGNATURE_ALGORITHM,
    }


def canonicalize_registry_entry_signing_envelope(entry: Mapping[str, Any]) -> bytes:
    """Return the exact v2 signing-message bytes: prefix || JCS(envelope)."""

    return SIGNING_DOMAIN_PREFIX + canonical_json_bytes(registry_entry_signing_envelope(entry))


def registry_entry_signing_payload_hash(entry: Mapping[str, Any]) -> str:
    """Return the SHA-256 URI of the exact v2 signing-message bytes."""

    return sha256_uri(canonicalize_registry_entry_signing_envelope(entry))


def signing_message_sha256(entry: Mapping[str, Any]) -> bytes:
    """Return the SHA-256 digest of the exact v2 signing-message bytes."""

    return hashlib.sha256(canonicalize_registry_entry_signing_envelope(entry)).digest()
