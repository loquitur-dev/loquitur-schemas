"""Signatures and keys are lowercase hex, checked before anything parses them.

The protocol fixes a compact signature as ``r || s`` in exactly 128 lowercase hex characters
and a public key as the uncompressed SEC1 point in lowercase hex. ``int(x, 16)`` and
``bytes.fromhex`` also accept uppercase, surrounding whitespace, underscores and a ``0x``
prefix, so a parser built on them alone would load a second spelling of the same value as
the value committed to. The two parsing helpers refuse any other form before parsing, and
the ECDSA helper built on them verifies only the lowercase form.

The mutations live in ``fixtures/trust_root_hex_cases.json`` with the trust-root case table
that ``loquitur-verify`` runs against its trust-root reader (``trust-root.md`` row 5 and the
public-key rule); this file runs the helpers under the same mutations. Every signature is
made at test time with a freshly generated key.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from signing_kit import private_scalar, public_key_hex, sign_digest_hex

from loquitur.schemas.registry_signing import (
    RegistrySigningError,
    _load_public_key,
    _raw_signature_hex_to_der,
    _secp256k1_verify_digest,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES = json.loads((FIXTURES / "trust_root_hex_cases.json").read_text(encoding="utf-8"))


def mutate_signature(sig: str, mutation: str) -> Any:
    assert len(sig) == 128 and sig[0] == "0" and sig[64] == "0"
    return {
        "none": sig,
        "z128": "z" * 128,
        "upper": sig.upper(),
        "space_padded": " " + sig[1:64] + " " + sig[65:],
        "zero_x_prefixed": "0x" + sig[2:64] + "0x" + sig[66:],
        "underscored": sig[1] + "_" + sig[2:64] + sig[65] + "_" + sig[66:],
        "truncated_127": sig[:127],
        "extended_129": sig + "0",
        "empty": "",
        "non_string": 12345,
    }[mutation]


def mutate_public_key(pub: str, mutation: str) -> str:
    return {
        "none": pub,
        "upper": "04" + pub[2:].upper(),
        "leading_space": " " + pub,
        "trailing_newline": pub + "\n",
    }[mutation]


def _sign_until_both_halves_start_with_zero(message: bytes) -> tuple[str, str]:
    """Sign with fresh keys until r and s both start with '0', so every mutation applies.

    The padded and underscored spellings replace a leading '0', which keeps the length at
    128 and the integer value unchanged: the spellings a length check misses.
    """
    digest = hashlib.sha256(message).digest()
    for _ in range(20000):
        scalar = private_scalar()
        sig = sign_digest_hex(digest, scalar)
        if sig[0] == "0" and sig[64] == "0":
            return sig, public_key_hex(scalar)
    raise AssertionError("no signature with leading zero nibbles in 20000 keys")


@pytest.fixture(scope="module")
def signed_digest() -> tuple[bytes, str, str]:
    message = b"loquitur lowercase hex"
    sig, pub = _sign_until_both_halves_start_with_zero(message)
    return hashlib.sha256(message).digest(), sig, pub


def _refused(parse, value: Any) -> str:
    try:
        parse(value)
    except RegistrySigningError:
        return "RegistrySigningError"
    return "parsed"


def test_the_shared_table_still_carries_the_signature_and_key_cases() -> None:
    """The verifier reads these two sections; the mutations below are the ones they name."""
    signature_mutations = {case["mutation"] for case in CASES["root_signature_cases"]}
    key_mutations = {case["mutation"] for case in CASES["root_public_key_cases"]}
    probe = "0" + "1" * 63 + "0" + "2" * 63
    assert len(CASES["root_signature_cases"]) >= 12 and len(CASES["root_public_key_cases"]) >= 4
    for mutation in signature_mutations:
        mutate_signature(probe, mutation)
    for mutation in key_mutations:
        mutate_public_key("04" + "ab" * 64, mutation)
    # The point of the uppercase, space-padded and underscored rows: int(x, 16) reads them as
    # the valid r and s, so only the form can refuse them.
    for mutation in ("upper", "space_padded", "underscored"):
        form = mutate_signature(probe, mutation)
        assert len(form) == 128
        assert (int(form[:64], 16), int(form[64:], 16)) == (int(probe[:64], 16), int(probe[64:], 16))


def test_signature_hex_is_refused_before_it_is_parsed(signed_digest) -> None:
    digest, sig, pub = signed_digest
    mutations = [
        "none",
        "upper",
        "space_padded",
        "zero_x_prefixed",
        "underscored",
        "z128",
        "truncated_127",
        "extended_129",
        "empty",
        "non_string",
    ]
    got = {
        mutation: (
            _refused(_raw_signature_hex_to_der, mutate_signature(sig, mutation)),
            _secp256k1_verify_digest(digest, mutate_signature(sig, mutation), pub),
        )
        for mutation in mutations
    }
    assert got == {m: ("parsed", True) if m == "none" else ("RegistrySigningError", False) for m in mutations}


def test_public_key_hex_is_refused_before_it_is_parsed(signed_digest) -> None:
    digest, sig, pub = signed_digest
    mutations = ["none", "upper", "leading_space", "trailing_newline"]
    got = {
        mutation: (
            _refused(_load_public_key, mutate_public_key(pub, mutation)),
            _secp256k1_verify_digest(digest, sig, mutate_public_key(pub, mutation)),
        )
        for mutation in mutations
    }
    assert got == {m: ("parsed", True) if m == "none" else ("RegistrySigningError", False) for m in mutations}
