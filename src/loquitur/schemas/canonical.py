"""Canonicalization and hashing of a registry entry.

This module defines registry-entry canonicalization and hashing only. The signing
payload is defined beside it in ``signing_envelope`` and ``registry_signing``, and the
bytes a root key signs over a trust registry in ``trust_root``. Verification is not in
this package: the signature step, issuer authorization and root authentication belong
to the verifiers, implemented once each.

Canonicalization uses RFC 8785 (JSON Canonicalization Scheme, JCS), the same
profile the ``loquitur-verify`` package uses. Both packages must agree byte for byte
on the canonical encoding of any shared object, or a verifier could recompute a
different commitment hash than the issuer produced. The shared JCS profile, in place
of a ``json.dumps`` profile of its own, keeps the two in step for non-ASCII strings
and integers at the edge of the ECMAScript range too.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Any

import rfc8785

from .errors import LoquiturSchemasError
from .validator import _NONCHARACTER_RE, MAX_JSON_NESTING_DEPTH, validate_instance

# RFC 8785 / ECMAScript safe-integer bound. Integers outside this range cannot be
# represented losslessly as JSON numbers under JCS and are rejected rather than
# silently encoded into a commitment an independent verifier could not reproduce.
_JS_SAFE_INT_MAX = 9_007_199_254_740_991


class RegistryCanonicalizationError(ValueError, LoquiturSchemasError):
    """Raised when a registry entry cannot be canonicalized safely."""


def _prepare_for_jcs(value: Any, *, path: str = "$") -> Any:
    """Validate JSON value types and reject values JCS cannot encode safely.

    Mirrors the verifier-side preparation so the two packages share identical
    canonicalization acceptance rules.
    """
    if value is None:
        return None
    if type(value) is bool:
        return value
    if isinstance(value, str):
        # Input strictness rule 9 (RFC 7493 section 2.1): no string holds a noncharacter. Refused
        # here as both verifiers' canonicalizers refuse it, so no helper of this package signs or
        # hashes a value a verifier would not canonicalize.
        if _NONCHARACTER_RE.search(value):
            raise RegistryCanonicalizationError(f"{path}: noncharacter is not admitted (input strictness rule 9)")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > _JS_SAFE_INT_MAX:
            raise RegistryCanonicalizationError(f"{path}: integer outside RFC8785/ECMAScript safe range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RegistryCanonicalizationError(f"{path}: non-finite float not allowed")
        if value.is_integer() and abs(value) > _JS_SAFE_INT_MAX:
            raise RegistryCanonicalizationError(f"{path}: integer-valued number outside RFC8785/ECMAScript safe range")
        return value
    if isinstance(value, (list, tuple)):
        return [_prepare_for_jcs(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RegistryCanonicalizationError(f"{path}: JSON object keys must be strings")
            if _NONCHARACTER_RE.search(key):
                raise RegistryCanonicalizationError(f"{path}: member name with a noncharacter is not admitted")
            out[key] = _prepare_for_jcs(item, path=f"{path}.{key}")
        return out
    raise RegistryCanonicalizationError(f"{path}: unsupported JSON value type: {type(value).__name__}")


def _value_nesting_exceeds(value: Any, limit: int) -> bool:
    """Return whether an in-memory value nests containers deeper than ``limit``, without recursing.

    The depth is the protocol's: a scalar has depth 0 and a list, tuple or dict one more than
    its deepest member. The walk stops at ``limit + 1``, so a value that contains itself is
    answered too.
    """

    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, Mapping):
            children: Any = item.values()
        elif isinstance(item, (list, tuple)):
            children = item
        else:
            continue
        if depth + 1 > limit:
            return True
        stack.extend((child, depth + 1) for child in children)
    return False


def canonical_json_bytes(value: Any) -> bytes:
    """Return RFC 8785 (JCS) canonical UTF-8 JSON bytes for JSON-compatible values.

    Object keys are ordered and whitespace removed per JCS; Unicode is preserved
    as UTF-8; non-standard floating-point values and out-of-range integers are
    rejected. This matches the ``loquitur-verify`` canonicalization profile.
    """

    # The protocol's nesting bound, decided before any recursive step. The preparation walk
    # and rfc8785 recurse per level, so a bound left to them would move with the
    # interpreter's recursion limit and with the frames a level costs, which differ between
    # Python versions. Every value that passes this check is one the protocol admits, so a
    # RecursionError from the steps below means the host's recursion limit cannot hold 64
    # levels, not that the value is nested too deeply: it propagates as itself, as it does
    # from the loquitur-verify canonicalizer.
    if _value_nesting_exceeds(value, MAX_JSON_NESTING_DEPTH):
        raise RegistryCanonicalizationError("value is nested too deeply to canonicalize")
    try:
        return rfc8785.dumps(_prepare_for_jcs(value))
    except RegistryCanonicalizationError:
        raise
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        # ValueError includes UnicodeError: a lone surrogate in a key or a value lands here.
        raise RegistryCanonicalizationError(f"value is not canonical JSON serializable: {exc}") from exc


def sha256_uri(payload: bytes) -> str:
    """Return a ``sha256:<hex>`` digest URI for bytes."""

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def canonicalize_registry_entry(entry: Mapping[str, Any]) -> bytes:
    """Return canonical bytes for a valid registry_entry object as provided."""

    if not isinstance(entry, Mapping):
        raise RegistryCanonicalizationError("registry entry must be a mapping/object")

    normalized_entry = dict(entry)
    result = validate_instance("registry_entry", normalized_entry)
    if not result.ok:
        errors = "; ".join(f"{error.path}:{error.code}" for error in result.errors)
        raise RegistryCanonicalizationError(f"invalid registry_entry cannot be canonicalized: {errors}")

    return canonical_json_bytes(normalized_entry)


def registry_entry_hash(entry: Mapping[str, Any]) -> str:
    """Return the deterministic SHA-256 digest URI for a registry entry."""

    return sha256_uri(canonicalize_registry_entry(entry))
