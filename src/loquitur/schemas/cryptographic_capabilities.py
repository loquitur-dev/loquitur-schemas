"""Closed cryptographic capability set for Loquitur protocol release 0.1.

The documents name their algorithm and key type with open identifiers, and the published
schemas admit any well-formed one. Support is decided by the verifier, never by the input:
a verifier checks the pair (signature algorithm, key type) against its own allowlist at the
signature step and answers ``UNSUPPORTED_SIGNATURE_ALGORITHM`` for any other pair. In release
0.1 the allowlist is the one pair below (``CRYPTOGRAPHIC_CAPABILITIES.json`` in
``loquitur-protocol``).
"""

from __future__ import annotations

CRYPTOGRAPHIC_CAPABILITY_PROFILE = "loquitur.crypto_capabilities.v0.1"
SUPPORTED_SIGNATURE_ALGORITHMS: tuple[str, ...] = ("secp256k1_ecdsa_sha256",)
SUPPORTED_TRUST_KEY_TYPES: tuple[str, ...] = ("secp256k1",)
SUPPORTED_SIGNATURE_PAIRS: tuple[tuple[str, str], ...] = (("secp256k1_ecdsa_sha256", "secp256k1"),)
# Admitted by the schemas as identifiers, supported by no 0.1 verifier.
RESERVED_UNSUPPORTED_ALGORITHMS: tuple[str, ...] = ("ed25519",)


def signature_algorithm_supported(value: object) -> bool:
    """Return whether ``value`` is a signature algorithm of the release 0.1 allowlist."""

    return isinstance(value, str) and value in SUPPORTED_SIGNATURE_ALGORITHMS


def trust_key_type_supported(value: object) -> bool:
    """Return whether ``value`` is a key type of the release 0.1 allowlist."""

    return isinstance(value, str) and value in SUPPORTED_TRUST_KEY_TYPES


def signature_pair_supported(algorithm: object, key_type: object) -> bool:
    """Return whether (signature algorithm, key type) is in the release 0.1 allowlist."""

    return (
        isinstance(algorithm, str) and isinstance(key_type, str) and (algorithm, key_type) in SUPPORTED_SIGNATURE_PAIRS
    )
