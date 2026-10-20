"""The bytes a root key signs to authenticate a trust registry.

``trust_root.py`` is the signing side only: the domain-separated, canonical message over
every member of the registry except ``signature``. What a verifier does with a signature
over these bytes is ``trust-root.md``'s and is implemented once, in the verifiers; the
tests here pin the message, so that a signer and a verifier cannot disagree about it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loquitur.schemas.canonical import canonical_json_bytes
from loquitur.schemas.registry_signing import SIGNATURE_ALGORITHM
from loquitur.schemas.trust_root import (
    TRUST_REGISTRY_PAYLOAD_SCHEMA,
    TRUST_REGISTRY_SIGNING_EXCLUDED_FIELDS,
    TRUST_ROOT_DOMAIN,
    TRUST_ROOT_ENVELOPE_SCHEMA,
    TRUST_ROOT_SIGNING_DOMAIN_PREFIX,
    TrustRootError,
    trust_registry_signing_bytes,
    trust_registry_signing_envelope,
    trust_registry_signing_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _trust_registry() -> dict:
    return json.loads((FIXTURES / "trust_registry.valid.json").read_text(encoding="utf-8"))


def test_signing_bytes_are_domain_separated_and_canonical() -> None:
    registry = _trust_registry()
    message = trust_registry_signing_bytes(registry)
    assert message.startswith(b"LOQUITUR\x00TRUST_REGISTRY\x00ROOT_SIGNATURE\x00V1\x00")
    assert message == TRUST_ROOT_SIGNING_DOMAIN_PREFIX + canonical_json_bytes(trust_registry_signing_envelope(registry))
    reordered = dict(reversed(list(registry.items())))
    assert trust_registry_signing_bytes(reordered) == message
    # the signature field cannot cover itself
    with_signature = dict(registry)
    with_signature["signature"] = {"algorithm": SIGNATURE_ALGORITHM, "key_id": "x", "signature": "aa" * 64}
    assert trust_registry_signing_bytes(with_signature) == message


def test_the_envelope_is_closed_and_names_the_protocol_identifiers() -> None:
    registry = _trust_registry()
    envelope = trust_registry_signing_envelope(registry)
    assert set(envelope) == {
        "domain",
        "envelope_schema",
        "envelope_version",
        "payload_schema",
        "signature_algorithm",
        "payload",
    }
    assert envelope["domain"] == TRUST_ROOT_DOMAIN == "org.loquitur.protocol.trust-registry-root-signature"
    assert (
        envelope["envelope_schema"] == TRUST_ROOT_ENVELOPE_SCHEMA == "loquitur.trust_registry_root_signing_envelope.v1"
    )
    assert envelope["envelope_version"] == 1
    assert envelope["payload_schema"] == TRUST_REGISTRY_PAYLOAD_SCHEMA == "loquitur.trust_registry.v1"
    assert envelope["signature_algorithm"] == SIGNATURE_ALGORITHM == "secp256k1_ecdsa_sha256"
    assert TRUST_REGISTRY_SIGNING_EXCLUDED_FIELDS == frozenset({"signature"})


def test_the_payload_is_every_member_but_the_signature() -> None:
    registry = _trust_registry()
    registry["signature"] = {"algorithm": SIGNATURE_ALGORITHM, "key_id": "x", "signature": "aa" * 64}
    payload = trust_registry_signing_payload(registry)
    assert set(payload) == set(registry) - {"signature"}
    assert all(payload[key] == registry[key] for key in payload)


@pytest.mark.parametrize("material", [None, 42, "registry", ["entries"], b"bytes"])
def test_material_that_is_not_an_object_is_refused(material) -> None:
    with pytest.raises(TrustRootError):
        trust_registry_signing_bytes(material)  # type: ignore[arg-type]
