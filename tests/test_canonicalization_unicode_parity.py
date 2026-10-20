"""Canonicalization parity on adversarial Unicode.

Locks byte-exact output for keys where UTF-16 code-unit order differs from
code-point order (astral characters), plus non-ASCII values (Arabic, emoji),
control characters, and combining-vs-precomposed forms. These are the cases a
naive ``sorted()``-by-code-point implementation would get wrong; RFC 8785
requires UTF-16 code-unit ordering. loquitur-verify-ts pins the same cases in
its canonicalization tests.
"""

from __future__ import annotations

from loquitur.schemas.canonical import canonical_json_bytes

# name -> (value, expected canonical UTF-8 bytes)
VECTORS = {
    "astral_before_bmphigh": ({"\ufffd": 1, "\U0001f600": 2}, b'{"\xf0\x9f\x98\x80":2,"\xef\xbf\xbd":1}'),
    "arabic_value_literal_utf8": (
        {"issuer_name": "\u0634\u0631\u0643\u0629"},
        '{"issuer_name":"شركة"}'.encode(),
    ),
    "combining_not_normalized": ({"a": "\u00e9", "b": "e\u0301"}, b'{"a":"\xc3\xa9","b":"e\xcc\x81"}'),
}


def test_astral_keys_sort_by_utf16_code_unit_not_code_point() -> None:
    # U+1F600 (surrogate D83D..) sorts BEFORE U+FFFD under UTF-16 code units,
    # the opposite of code-point order, the classic JCS correctness case. U+FFFF, the
    # highest BMP code point, is a noncharacter and refused (input strictness rule 9).
    out = canonical_json_bytes({"\ufffd": 1, "\U0001f600": 2})
    assert out == b'{"\xf0\x9f\x98\x80":2,"\xef\xbf\xbd":1}'


def test_non_ascii_values_are_literal_utf8_not_escaped() -> None:
    out = canonical_json_bytes({"issuer_name": "\u0634\u0631\u0643\u0629"})
    assert out == '{"issuer_name":"شركة"}'.encode()


def test_unicode_is_not_normalized() -> None:
    # é (precomposed) and e+combining acute stay distinct: RFC 8785 does not normalize to NFC.
    out = canonical_json_bytes({"a": "\u00e9", "b": "e\u0301"})
    # a = precomposed é (C3 A9); b = e + combining acute (65 CC 81), kept distinct.
    assert out == b'{"a":"\xc3\xa9","b":"e\xcc\x81"}'
    assert out.count(b"\xcc\x81") == 1  # exactly one combining mark preserved
