"""What ``canonical_json_bytes`` refuses, and the one error class it refuses with.

The canonicalizer in ``loquitur-verify`` is a separate implementation of the same RFC 8785
profile, and the two must refuse the same inputs the same way: a lone surrogate in a
member name or a value, and a value nested deeply enough to exhaust the interpreter stack.
Here each is ``RegistryCanonicalizationError`` and nothing else. The refused rows and the
accepted inputs run in one table, so the table fails both if a refusal escapes as another
exception and if an accepted input is refused.

The nesting bound is the protocol's, input strictness rule 6: depth 64 canonicalizes and 65 is
refused, decided without recursion, so no recursion limit and no Python version moves it. A
RecursionError from the recursive steps after the bound is therefore a host fault, never a
refusal of the value, and it propagates as itself.
"""

from __future__ import annotations

from typing import Any

import pytest

import loquitur.schemas.canonical as canonical
from loquitur.schemas.canonical import RegistryCanonicalizationError, canonical_json_bytes


def _deep_list(depth: int) -> Any:
    value: Any = 0
    for _ in range(depth):
        value = [value]
    return value


def _deep_object(depth: int) -> Any:
    value: Any = 0
    for _ in range(depth):
        value = {"a": value}
    return value


def _outcome(value: Any) -> object:
    """The canonical bytes, or the refusal: its class, and for nesting whether it says so."""
    try:
        return canonical_json_bytes(value)
    except RegistryCanonicalizationError as exc:
        return ("RegistryCanonicalizationError", "nested too deeply" in str(exc))
    except Exception as exc:  # noqa: BLE001 - an escaping exception is the defect a row detects
        return ("escaped", type(exc).__name__)


def test_the_package_error_is_the_only_refusal_and_valid_input_still_canonicalises() -> None:
    refused = ("RegistryCanonicalizationError", False)
    nested_refusal = ("RegistryCanonicalizationError", True)
    rows = {
        # Nesting deep enough to exhaust a default interpreter stack. A fixed depth: the bound,
        # not the recursion limit, refuses it, so it never reaches the stack as RecursionError.
        "nesting-array": (_deep_list(4000), nested_refusal),
        "nesting-object": (_deep_object(4000), nested_refusal),
        # Lone surrogates.
        "lone-low-surrogate-key": ({"\udc00x": 1}, refused),
        "lone-high-surrogate-key": ({"\ud800": 1}, refused),
        "lone-value": ({"a": "\ud800"}, refused),
        "lone-value-in-array": ({"a": ["ok", "\udfff"]}, refused),
        "reversed-pair": ({"a": "\udc00\ud800"}, refused),
        # Accepted: a surrogate pair is one character, and 64 levels is the protocol limit.
        "surrogate-pair": ({"a": "\U0001f600"}, b'{"a":"\xf0\x9f\x98\x80"}'),
        "depth-64": (_deep_list(64), b"[" * 64 + b"0" + b"]" * 64),
        "depth-64-object": (_deep_object(64), b'{"a":' * 64 + b"0" + b"}" * 64),
        # One level past the protocol limit, refused by the bound itself on every Python, far
        # below where the interpreter's own recursion limit would stop it.
        "depth-65": (_deep_list(65), nested_refusal),
        "depth-65-object": (_deep_object(65), nested_refusal),
        "depth-65-through-a-tuple": ((_deep_list(64),), nested_refusal),
    }
    got = {name: _outcome(value) for name, (value, _expected) in rows.items()}
    assert got == {name: expected for name, (_value, expected) in rows.items()}


def test_a_host_out_of_stack_on_an_admitted_value_is_not_a_nesting_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """65 levels is refused by the bound; a RecursionError on 64 levels propagates as itself.

    The encoder's RecursionError is raised directly, the state a host reaches when its recursion
    limit cannot hold 64 levels, the same on every Python version. It must not be reported as
    nested too deeply: the value keeps input strictness rule 6.
    """

    def exhausted(value: object) -> bytes:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(canonical.rfc8785, "dumps", exhausted)
    assert _outcome(_deep_list(65)) == ("RegistryCanonicalizationError", True)
    with pytest.raises(RecursionError):
        canonical_json_bytes(_deep_list(64))


# Input strictness rule 9: a noncharacter in a value or a member name is refused, as both
# verifiers' canonicalizers refuse it.
_NONCHARACTERS = ("\ufdd0", "\ufdef", "\ufffe", "\uffff", "\U0001fffe", "\U0010ffff")


@pytest.mark.parametrize("nc", _NONCHARACTERS, ids=lambda c: f"U+{ord(c):04X}")
def test_a_noncharacter_in_a_value_or_a_member_name_is_refused(nc: str) -> None:
    for value in ({"a": f"x{nc}y"}, [nc], {nc: 1}, {"outer": {f"k{nc}": [1]}}):
        with pytest.raises(RegistryCanonicalizationError):
            canonical_json_bytes(value)


def test_the_neighbours_of_the_noncharacters_are_canonicalised() -> None:
    for ok in ("\ufdcf", "\ufdf0", "\ufffd", "\U0001fffd", "\ue000"):
        assert canonical_json_bytes({ok: ok})
