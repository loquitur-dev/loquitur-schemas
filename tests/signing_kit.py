"""Test-only secp256k1 signing, for tests that need a signature over a message this package builds.

The package takes no private key and produces no signature. Its tests still need signatures
to show that the messages it builds are the ones a signature binds, so this helper signs with
``cryptography`` directly. Keys are made when a test asks for one, from the operating system's
randomness or from a test's seeded generator, and are never written or printed.

Signatures are deterministic (RFC 6979) and low-S, the form the protocol accepts.
"""

from __future__ import annotations

import random
import secrets

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import utils as asym_utils

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def private_scalar(rng: random.Random | None = None) -> int:
    """A private scalar in [1, n - 1]: from ``rng`` when a test needs reproducible keys."""
    if rng is None:
        return secrets.randbelow(SECP256K1_N - 1) + 1
    return rng.randrange(1, SECP256K1_N)


def public_key_hex(scalar: int) -> str:
    """The uncompressed SEC1 public key of ``scalar``, as lowercase hex."""
    key = ec.derive_private_key(scalar, ec.SECP256K1())
    return (
        key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint).hex()
    )


def sign_digest(digest: bytes, scalar: int) -> tuple[int, int]:
    """Sign a 32-byte digest; returns ``(r, s)`` with ``s`` in the low half."""
    assert len(digest) == 32
    key = ec.derive_private_key(scalar, ec.SECP256K1())
    der = key.sign(digest, ec.ECDSA(asym_utils.Prehashed(hashes.SHA256()), deterministic_signing=True))
    r, s = asym_utils.decode_dss_signature(der)
    return r, min(s, SECP256K1_N - s)


def sign_digest_hex(digest: bytes, scalar: int) -> str:
    """:func:`sign_digest` in the protocol's compact form: r || s, 128 lowercase hex characters."""
    r, s = sign_digest(digest, scalar)
    return f"{r:064x}{s:064x}"
