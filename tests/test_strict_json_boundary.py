"""Strict JSON parse boundary for the schemas package.

Mirrors the protocol "Input strictness" rules on the schemas-side untrusted
boundary (``load_json_document``, used by the validate CLI): duplicate object
member names and non-finite numbers are rejected at parse time, and the
canonicalization guard applies the value-based safe-integer rule (an
integer-valued number beyond 2^53 - 1 is invalid regardless of spelling).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from loquitur.schemas.canonical import RegistryCanonicalizationError, canonical_json_bytes
from loquitur.schemas.validator import SchemaValidationUsageError, load_json_document


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "doc.json"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1, "a": 2}',
        '{"outer": {"k": 1, "k": 2}}',
        '{"a": 1, "\\u0061": 2}',  # escape-equivalent duplicate
    ],
)
def test_load_json_document_rejects_duplicate_keys(tmp_path: Path, text: str) -> None:
    with pytest.raises(SchemaValidationUsageError, match="duplicate object key"):
        load_json_document(_write(tmp_path, text))


@pytest.mark.parametrize("text", ['{"n": NaN}', '{"n": Infinity}', '{"n": -Infinity}'])
def test_load_json_document_rejects_non_finite(tmp_path: Path, text: str) -> None:
    with pytest.raises(SchemaValidationUsageError, match="non-finite number"):
        load_json_document(_write(tmp_path, text))


def test_load_json_document_accepts_clean(tmp_path: Path) -> None:
    assert load_json_document(_write(tmp_path, '{"a": 1, "b": [{"a": 2}]}')) == {
        "a": 1,
        "b": [{"a": 2}],
    }


@pytest.mark.parametrize(
    "value",
    [1e16, float(2**53), -1e300],
    ids=["float-1e16", "float-2^53", "float--1e300"],
)
def test_canonical_guard_rejects_integer_valued_beyond_safe_range(value: float) -> None:
    with pytest.raises(RegistryCanonicalizationError):
        canonical_json_bytes({"n": value})


def test_canonical_guard_accepts_safe_and_fractional() -> None:
    assert canonical_json_bytes({"n": 9007199254740991.0}) == b'{"n":9007199254740991}'
    assert canonical_json_bytes({"n": 0.5}) == b'{"n":0.5}'
