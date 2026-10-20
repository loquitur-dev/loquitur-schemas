import json
import os
from pathlib import Path

import pytest

from loquitur.schemas.cryptographic_capabilities import (
    CRYPTOGRAPHIC_CAPABILITY_PROFILE,
    RESERVED_UNSUPPORTED_ALGORITHMS,
    SUPPORTED_SIGNATURE_ALGORITHMS,
    SUPPORTED_SIGNATURE_PAIRS,
    SUPPORTED_TRUST_KEY_TYPES,
    signature_algorithm_supported,
    signature_pair_supported,
    trust_key_type_supported,
)

PROTOCOL_CAPABILITIES = Path(__file__).resolve().parents[2] / "loquitur-protocol" / "CRYPTOGRAPHIC_CAPABILITIES.json"


def test_release_0_1_capability_matrix_is_closed() -> None:
    assert CRYPTOGRAPHIC_CAPABILITY_PROFILE == "loquitur.crypto_capabilities.v0.1"
    assert SUPPORTED_SIGNATURE_ALGORITHMS == ("secp256k1_ecdsa_sha256",)
    assert SUPPORTED_TRUST_KEY_TYPES == ("secp256k1",)
    assert RESERVED_UNSUPPORTED_ALGORITHMS == ("ed25519",)
    assert signature_algorithm_supported("secp256k1_ecdsa_sha256")
    assert trust_key_type_supported("secp256k1")
    assert not signature_algorithm_supported("ed25519")
    assert not trust_key_type_supported("ed25519")


def test_the_allowlist_is_a_set_of_algorithm_and_key_type_pairs() -> None:
    assert SUPPORTED_SIGNATURE_PAIRS == (("secp256k1_ecdsa_sha256", "secp256k1"),)
    got = {
        pair: signature_pair_supported(*pair)
        for pair in [
            ("secp256k1_ecdsa_sha256", "secp256k1"),
            ("secp256k1_ecdsa_sha256", "ed25519"),
            ("ed25519", "secp256k1"),
            ("ed25519", "ed25519"),
            ("unknown_alg", "secp256k1"),
            ("SECP256K1_ECDSA_SHA256", "secp256k1"),
            ("secp256k1_ecdsa_sha256", None),
            (None, "secp256k1"),
        ]
    }
    assert got == {pair: pair == ("secp256k1_ecdsa_sha256", "secp256k1") for pair in got}


def test_the_allowlist_is_the_protocol_capability_set() -> None:
    if not PROTOCOL_CAPABILITIES.is_file():
        # Skipped for a contributor working here alone; a failure where CI requires siblings.
        message = f"loquitur-protocol is not checked out beside this repository ({PROTOCOL_CAPABILITIES})"
        if os.environ.get("LOQUITUR_REQUIRE_SIBLINGS", "").strip().lower() in {"1", "true", "yes", "on"}:
            pytest.fail(message)
        pytest.skip(message)
    capabilities = json.loads(PROTOCOL_CAPABILITIES.read_text(encoding="utf-8"))
    pairs = tuple((row["id"], row["key_type"]) for row in capabilities["signature_algorithms"] if row["verification"])
    assert pairs == SUPPORTED_SIGNATURE_PAIRS
    assert tuple(row["id"] for row in capabilities["reserved_not_supported"]) == RESERVED_UNSUPPORTED_ALGORITHMS
    assert all(row["schema_acceptance"] and not row["verification"] for row in capabilities["reserved_not_supported"])
