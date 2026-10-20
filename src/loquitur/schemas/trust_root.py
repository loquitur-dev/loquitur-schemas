"""The message of the trust-registry root signature.

A trust registry is authenticated by a signature from a root key distributed out of band,
never alongside the registry it authenticates (loquitur-protocol ``trust-root.md``). This
module defines the bytes that signature covers: a domain-separated, canonical envelope over
every member of the registry except ``signature``, which cannot cover itself. A signer
builds the message with :func:`trust_registry_signing_bytes`, hashes it with SHA-256 and
signs the digest with secp256k1 ECDSA; the signing itself is not part of this package.

Nothing here verifies. Reading a trust-root document, matching the signing key, judging
the root's status and its window at the operator's evaluation time, and checking the
signature, in the order ``trust-root.md`` gives, is the verifier's: ``loquitur-verify`` and
``loquitur-verify-ts``, each given a trust-root document (``--trust-root``). One rule has one
implementation, and this package carries none of the verifier's rules. The verifier holds its
copy of the constants below to this module byte for byte, so a signer and a verifier cannot
disagree about the message.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import canonical_json_bytes
from .errors import LoquiturSchemasError
from .registry_signing import SIGNATURE_ALGORITHM

TRUST_ROOT_DOMAIN = "org.loquitur.protocol.trust-registry-root-signature"
TRUST_ROOT_ENVELOPE_SCHEMA = "loquitur.trust_registry_root_signing_envelope.v1"
TRUST_REGISTRY_PAYLOAD_SCHEMA = "loquitur.trust_registry.v1"
TRUST_ROOT_SIGNING_DOMAIN_PREFIX = b"LOQUITUR\x00TRUST_REGISTRY\x00ROOT_SIGNATURE\x00V1\x00"

# The signature cannot cover itself.
TRUST_REGISTRY_SIGNING_EXCLUDED_FIELDS = frozenset({"signature"})


class TrustRootError(ValueError, LoquiturSchemasError):
    """The trust-registry material given to sign is malformed."""


def trust_registry_signing_payload(trust_registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the trust-registry fields the root signature commits to."""
    if not isinstance(trust_registry, Mapping):
        raise TrustRootError("trust registry must be a mapping/object")
    return {
        key: value for key, value in dict(trust_registry).items() if key not in TRUST_REGISTRY_SIGNING_EXCLUDED_FIELDS
    }


def trust_registry_signing_envelope(trust_registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the closed, domain-separated envelope a root signature binds."""
    return {
        "domain": TRUST_ROOT_DOMAIN,
        "envelope_schema": TRUST_ROOT_ENVELOPE_SCHEMA,
        "envelope_version": 1,
        "payload_schema": TRUST_REGISTRY_PAYLOAD_SCHEMA,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "payload": trust_registry_signing_payload(trust_registry),
    }


def trust_registry_signing_bytes(trust_registry: Mapping[str, Any]) -> bytes:
    """Return the exact bytes a root key signs to authenticate a trust registry."""
    return TRUST_ROOT_SIGNING_DOMAIN_PREFIX + canonical_json_bytes(trust_registry_signing_envelope(trust_registry))
