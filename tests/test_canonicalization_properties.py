"""Randomized property coverage for JCS canonicalization.

Every commitment in the protocol is a hash over these bytes, so canonicalization
is the single function whose correctness everything else inherits. Other tests
pin specific known cases (astral key ordering, no Unicode normalization, duplicate
keys, non-finite numbers, safe-integer range). This module holds the properties that
must hold for arbitrary documents:

  * determinism: same value, same bytes, every time;
  * order invariance: key order in the input cannot change the output;
  * round trip: re-parsing canonical bytes and re-canonicalizing is a fixpoint;
  * injectivity: different content must not collide onto the same bytes.

Seeded, so any counterexample is reproducible.
"""

from __future__ import annotations

import json
import os
import random

import pytest

from loquitur.schemas.canonical import canonical_json_bytes

SEED = 20260722
ITERATIONS = int(os.environ.get("LOQUITUR_CANON_ITERATIONS", "200"))

# Values chosen to stay inside the protocol's declared value space: JSON-safe
# integers, finite floats, and strings that exercise unicode edges without
# relying on lone surrogates (which are rejected elsewhere by design).
_ATOMS = [
    None,
    True,
    False,
    0,
    1,
    -1,
    42,
    -42,
    2**53 - 1,
    -(2**53 - 1),
    0.0,
    1.5,
    -1.5,
    1e10,
    1e-10,
    "",
    "a",
    "Z",
    "0",
    "é",
    "É",
    "\ufffd",  # U+FFFF, the highest BMP code point, is a noncharacter and refused (rule 9)
    "\U0001f600",
    "line\nbreak",
    "tab\there",
    'quote"inside',
    "back\\slash",
    "e\u0301",
    "é",  # decomposed and precomposed: never normalized into one
    "\u202e",
    "\ufeff",
]
_KEYS = ["a", "b", "z", "A", "Z", "0", "1", "é", "\ufffd", "\U0001f600", "aa", "ab", "bé"]


def _random_value(rng: random.Random, depth: int = 0):
    if depth >= 3 or rng.random() < 0.45:
        return rng.choice(_ATOMS)
    if rng.random() < 0.5:
        return [_random_value(rng, depth + 1) for _ in range(rng.randrange(0, 4))]
    keys = rng.sample(_KEYS, rng.randrange(0, min(5, len(_KEYS))))
    return {k: _random_value(rng, depth + 1) for k in keys}


def _shuffled(value, rng: random.Random):
    """Same document, keys emitted in a different order."""
    if isinstance(value, dict):
        items = [(k, _shuffled(v, rng)) for k, v in value.items()]
        rng.shuffle(items)
        return dict(items)
    if isinstance(value, list):
        return [_shuffled(v, rng) for v in value]
    return value


def test_canonicalization_is_deterministic() -> None:
    rng = random.Random(SEED)
    for _ in range(ITERATIONS):
        value = _random_value(rng)
        assert canonical_json_bytes(value) == canonical_json_bytes(value)


def test_canonicalization_is_key_order_invariant() -> None:
    rng = random.Random(SEED + 1)
    for _ in range(ITERATIONS):
        value = _random_value(rng)
        reordered = _shuffled(value, rng)
        assert canonical_json_bytes(value) == canonical_json_bytes(reordered), (
            f"key order changed the canonical bytes for {value!r}"
        )


def test_canonical_bytes_reparse_to_a_fixpoint() -> None:
    rng = random.Random(SEED + 2)
    for _ in range(ITERATIONS):
        value = _random_value(rng)
        once = canonical_json_bytes(value)
        twice = canonical_json_bytes(json.loads(once.decode("utf-8")))
        assert once == twice, f"canonicalization is not a fixpoint for {value!r}"


def test_canonical_bytes_are_valid_utf8_json() -> None:
    rng = random.Random(SEED + 3)
    for _ in range(ITERATIONS):
        raw = canonical_json_bytes(_random_value(rng))
        json.loads(raw.decode("utf-8"))  # must not raise
        assert b"\x00" not in raw, "canonical output must not contain raw NUL bytes"


def test_distinct_documents_do_not_collide() -> None:
    """Injectivity over a generated corpus: equal bytes must mean equal content."""
    rng = random.Random(SEED + 4)
    seen: dict[bytes, object] = {}
    for _ in range(ITERATIONS * 3):
        value = _random_value(rng)
        raw = canonical_json_bytes(value)
        if raw in seen:
            assert seen[raw] == value, f"canonical collision: {seen[raw]!r} and {value!r} share bytes {raw!r}"
        else:
            seen[raw] = value


def test_precomposed_and_decomposed_unicode_stay_distinct() -> None:
    """No NFC or NFD normalization: the protocol commits to the bytes it was given."""
    precomposed = canonical_json_bytes({"k": "é"})
    decomposed = canonical_json_bytes({"k": "e\u0301"})
    assert precomposed != decomposed, "Unicode was normalized, so commitments would be ambiguous"


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), 2**53, -(2**53), 2**63, {"k": float("nan")}, [float("inf")]],
)
def test_out_of_space_numbers_are_refused(value) -> None:
    """NaN/Infinity and JS-unsafe integers are outside the declared value space."""
    with pytest.raises(Exception):
        canonical_json_bytes(value)


def test_hostile_values_never_crash_unexpectedly() -> None:
    """Unsupported types must raise a typed refusal, not an arbitrary error."""
    for value in [object(), {1: "int key"}, {(1, 2): "tuple key"}, b"bytes", {"k": object()}]:
        with pytest.raises(Exception):
            canonical_json_bytes(value)
