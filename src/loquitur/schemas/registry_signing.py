"""The registry-entry signing message, validated, and the ECDSA reference check.

This module builds the exact bytes an issuer signs over a registry entry (signing envelope
v2, defined in ``signing_envelope``) after holding the entry to the schema and to input
strictness, so an entry the verifiers refuse never yields a signing message. It takes no
private key and produces no signature: signing tools are not part of this package.

It verifies nothing a protocol document specifies: the signature step of a registry entry,
issuer authorization against a trust registry and trust-registry root authentication are
the verifiers' (``loquitur-verify``, ``loquitur-verify-ts``), implemented once each. The one
verification primitive here, ``_secp256k1_verify_digest``, is the ``cryptography``-backed
ECDSA reference the verifier's differential test compares its own implementation against.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import utils as asym_utils

# The redundant `X as X` below is the PEP 484 explicit re-export marker, not a typo.
# `loquitur.schemas.__init__` and `trust_root` import these names from this module, and a
# type checker in strict mode accepts that only for a name the module marks as exported.
# None of them is used *here*: written plainly they read as dead imports and a lint
# autofix deletes them, which breaks the package's import.
from .errors import LoquiturSchemasError
from .signing_envelope import (
    SIGNATURE_ALGORITHM as SIGNATURE_ALGORITHM,
)
from .signing_envelope import (
    SIGNING_DOMAIN_PREFIX as SIGNING_DOMAIN_PREFIX,
)
from .signing_envelope import (
    SIGNING_ENVELOPE_DOMAIN as SIGNING_ENVELOPE_DOMAIN,
)
from .signing_envelope import (
    SIGNING_ENVELOPE_SCHEMA as SIGNING_ENVELOPE_SCHEMA,
)
from .signing_envelope import (
    SIGNING_PAYLOAD_EXCLUDED_FIELDS as SIGNING_PAYLOAD_EXCLUDED_FIELDS,
)
from .signing_envelope import (
    SIGNING_PAYLOAD_ID as SIGNING_PAYLOAD_ID,
)
from .signing_envelope import (
    SIGNING_PAYLOAD_SCHEMA as SIGNING_PAYLOAD_SCHEMA,
)
from .signing_envelope import (
    SIGNING_PAYLOAD_VERSION as SIGNING_PAYLOAD_VERSION,
)
from .signing_envelope import (
    canonicalize_registry_entry_signing_envelope,
)
from .signing_envelope import (
    registry_entry_signing_envelope as _registry_entry_signing_envelope,
)
from .signing_envelope import (
    registry_entry_signing_payload as _registry_entry_signing_payload,
)
from .signing_envelope import (
    registry_entry_signing_payload_hash as _registry_entry_signing_payload_hash,
)
from .validator import input_strictness_violation, validate_instance

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
# The protocol's encodings: a compact r||s signature is 128 lowercase hex characters and a
# public key is the uncompressed SEC1 point, 04 then 128 lowercase hex characters. Nothing
# is trimmed or case-folded before these are applied (use with fullmatch).
_SIGNATURE_HEX_RE = re.compile(r"[0-9a-f]{128}")
_PUBLIC_KEY_HEX_RE = re.compile(r"04[0-9a-f]{128}")


class RegistrySigningError(ValueError, LoquiturSchemasError):
    """Raised when a registry entry cannot yield a signing message: it fails its contract."""


def _validate_registry_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise RegistrySigningError("registry entry must be a mapping/object")
    normalized = dict(entry)
    # The schema with the calendar rule for its instants, and then what the verifiers refuse
    # at load beyond it: a value that breaks input strictness. An entry the verifiers refuse
    # never yields a signing message.
    result = validate_instance("registry_entry", normalized)
    if not result.ok:
        errors = "; ".join(f"{error.path}:{error.code}" for error in result.errors)
        raise RegistrySigningError(f"invalid registry_entry cannot be signed: {errors}")
    violation = input_strictness_violation(normalized)
    if violation is not None:
        raise RegistrySigningError(f"invalid registry_entry cannot be signed: input strictness: {violation}")
    return normalized


def registry_entry_signing_payload(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the validated payload object embedded in signing envelope v2."""

    return _registry_entry_signing_payload(_validate_registry_entry(entry))


def registry_entry_signing_envelope(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the validated closed signing envelope v2."""

    return _registry_entry_signing_envelope(_validate_registry_entry(entry))


def canonicalize_registry_entry_signing_payload(entry: Mapping[str, Any]) -> bytes:
    """Return the exact v2 signing-message bytes.

    The bytes are the domain prefix followed by the RFC 8785 encoding of the
    envelope (``signing_envelope``), not the bare payload.
    """

    return canonicalize_registry_entry_signing_envelope(_validate_registry_entry(entry))


def registry_entry_signing_payload_hash(entry: Mapping[str, Any]) -> str:
    """Return the SHA-256 URI of the exact v2 signing-message bytes."""

    return _registry_entry_signing_payload_hash(_validate_registry_entry(entry))


def _load_public_key(public_key_hex: str) -> ec.EllipticCurvePublicKey:
    # Lowercase only, checked before any parsing: `bytes.fromhex` also accepts uppercase and
    # embedded whitespace, so a key spelled differently from the one committed to would load.
    if not isinstance(public_key_hex, str) or not _PUBLIC_KEY_HEX_RE.fullmatch(public_key_hex):
        raise RegistrySigningError("public key must be uncompressed SEC1 hex: 04 and 128 lowercase hex characters")
    encoded = bytes.fromhex(public_key_hex)
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), encoded)
    except ValueError as exc:
        raise RegistrySigningError("public key point is not on secp256k1") from exc


def _raw_signature_hex_to_der(signature_hex: str) -> bytes:
    # Lowercase only, checked before `int(x, 16)`, which also accepts uppercase, surrounding
    # whitespace, underscores and a 0x prefix: each a second spelling of the same r and s.
    if not isinstance(signature_hex, str) or not _SIGNATURE_HEX_RE.fullmatch(signature_hex):
        raise RegistrySigningError("signature must be compact 64-byte r||s as 128 lowercase hex characters")
    r = int(signature_hex[:64], 16)
    s = int(signature_hex[64:], 16)
    if not (1 <= r < SECP256K1_N and 1 <= s < SECP256K1_N):
        raise RegistrySigningError("signature r/s values must be in [1, secp256k1_n - 1]")
    if s > SECP256K1_N // 2:
        raise RegistrySigningError("signature uses non-canonical high-S encoding")
    return asym_utils.encode_dss_signature(r, s)


def _secp256k1_verify_digest(digest: bytes, signature_hex: str, public_key_hex: str) -> bool:
    if len(digest) != 32:
        return False
    try:
        der_signature = _raw_signature_hex_to_der(signature_hex)
        public_key = _load_public_key(public_key_hex)
        public_key.verify(der_signature, digest, ec.ECDSA(asym_utils.Prehashed(hashes.SHA256())))
        return True
    except (InvalidSignature, RegistrySigningError, ValueError):
        return False


# The name the verifier's differential test imports: the cryptography-backed reference it
# compares its own ECDSA implementation against. A primitive, not a protocol rule.
def _secp256k1_verify_digest_for_tests(digest: bytes, signature_hex: str, public_key_hex: str) -> bool:
    return _secp256k1_verify_digest(digest, signature_hex, public_key_hex)
