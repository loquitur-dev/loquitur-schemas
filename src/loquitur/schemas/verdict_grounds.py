"""The verdict is a function of the grounds it cites (LCP-0008).

A ``verification_summary`` that asserts ``status: "pass"`` while citing no reason code,
or that contradicts the codes it cites (``AUTHORIZATION_ISSUER_KEY_REVOKED``, of severity
``fail``, beside ``status: "pass"``), does not conform. The verdict follows from the grounds
it cites, so a reader can check it instead of taking it on trust.

The module applies the seven rules VG-1 to VG-7 of verdict-grounds.md. Only VG-1, that
``reason_codes`` is present, non-empty and free of duplicates, also lives in
``verification_summary.schema.json``. The other six are here alone, for two reasons.

Five of them need the reason-code catalog, which holds each code's severity and which no
schema language can reach from the document: every cited code is in the catalog (VG-2), the
status equals the mapped maximum severity of the cited codes (VG-3), a ``pass`` cites at
least one ``info``-severity code (VG-4), every cited code of an actionable severity
(``fail`` or ``review``) carries a ``reason_context`` entry saying what to act on (VG-6),
because a bare code names neither the key nor the instant the reader has to fix, and
every code a ``reason_context`` entry cites is in the catalog (VG-7).

The sixth, VG-5 -- that a ``pass`` carries non-empty ``key_checks`` -- can be expressed in
JSON Schema with ``if``/``then``, but not in this project's schemas.
``loquitur.schemas.validator`` accepts a closed set of nineteen keywords and rejects
anything else; ``if``, ``then``, ``$ref`` and ``minProperties`` are outside it. A dialect
that small keeps a second validator easy to write, and the protocol rests on a third party
being able to re-verify. Widening it for one conditional would put that cost on every
implementation, so the conditional rule is here instead.

Within this package the rules live in one module, beside the catalog that supplies the
severities, so each has one definition here: code that uses loquitur-schemas imports a rule
from this module instead of carrying a copy of its own. The two reference verifiers are the
exception, by design: they do not depend on this package at run time, so loquitur-verify-py
and loquitur-verify-ts each implement the rules themselves, all seven for a summary and VG-1
to VG-4 for a registry entry. What keeps them in step is the conformance corpus: its
cross-repository gate runs every summary-checks run through both verifiers and holds each to
the rules the run declares and to the other. This module is held to the same rules by its
own tests.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from itertools import islice
from typing import Final

from .reason_codes_catalog import ReasonCodesCatalog, load_reason_codes_catalog
from .validator import json_value_key
from .verification_vocabulary import VERIFICATION_STATUSES

__all__ = [
    "SEVERITY_ORDER",
    "SEVERITY_TO_STATUS",
    "STATUSES_REQUIRING_CONTEXT",
    "max_severity",
    "status_for_codes",
    "verdict_grounds_errors",
]

# Ascending. The maximum over the cited codes decides the verdict, so a single `fail`
# among twenty `info` codes still produces a failing summary: citing more grounds can never
# hide a failure.
SEVERITY_ORDER: Final[tuple[str, ...]] = ("info", "warn", "review", "fail")

SEVERITY_TO_STATUS: Final[Mapping[str, str]] = {
    "info": "pass",
    "warn": "warning",
    "review": "review",
    "fail": "fail",
}

# `fail` and `review` are the severities a reader has to act on, and a bare code does not
# say what to act on: "the issuing key had already expired" identifies neither the key nor
# the instant. `info` and `warn` are exempt because there is nothing to remedy.
STATUSES_REQUIRING_CONTEXT: Final[frozenset[str]] = frozenset({"fail", "review"})


def max_severity(codes: Iterable[str], catalog: ReasonCodesCatalog | None = None) -> str | None:
    """Return the highest severity among ``codes``, or ``None`` if ``codes`` is empty.

    A summary citing a code the vocabulary does not define is not a summary whose verdict
    can be checked, and skipping the unknown code would let the maximum come out too low,
    which would turn an unrecognized failure into a pass. The function raises instead.

    Raises:
        ReasonCodesCatalogError: Through ``catalog.get``, if a code is not in the catalog.
    """
    cat = catalog if catalog is not None else load_reason_codes_catalog()
    highest: str | None = None
    for code in codes:
        severity = cat.get(code).severity
        if highest is None or SEVERITY_ORDER.index(severity) > SEVERITY_ORDER.index(highest):
            highest = severity
    return highest


def status_for_codes(codes: Iterable[str], catalog: ReasonCodesCatalog | None = None) -> str | None:
    """Return the status the cited ``codes`` imply, or ``None`` for no codes."""
    severity = max_severity(codes, catalog)
    return None if severity is None else SEVERITY_TO_STATUS[severity]


# How much of a document value a message may quote. The values are untrusted, so the quote is
# bounded in depth, in width and in length: a message about a value must never cost more than
# a small constant, and never recurse as deep as the value does.
_QUOTE_DEPTH: Final[int] = 3
_QUOTE_ITEMS: Final[int] = 4
_QUOTE_CHARS: Final[int] = 60
_LABEL_CHARS: Final[int] = 200


def _quote(value: object, depth: int = _QUOTE_DEPTH) -> str:
    """Return a bounded, non-recursive rendering of ``value`` for a message.

    A small value reads as its ``repr``, so the messages about the usual malformed entries stay
    what they were. A value that nests deeper than ``_QUOTE_DEPTH``, holds more than
    ``_QUOTE_ITEMS`` members or is longer than ``_QUOTE_CHARS`` characters is cut with ``...``,
    and a container met again inside itself is cut by the same depth limit. Nothing here
    depends on how deep or wide the document is.
    """

    if value is None or isinstance(value, (bool, float)):
        return repr(value)
    if isinstance(value, int):
        try:
            return repr(value)
        except ValueError:  # an integer with more digits than the interpreter will print
            return "an integer"
    if isinstance(value, str):
        return repr(value) if len(value) <= _QUOTE_CHARS else repr(value[:_QUOTE_CHARS])[:-1] + "...'"
    if isinstance(value, (list, tuple)):
        opening, closing = "[", "]"
        items = [_quote(item, depth - 1) for item in value[:_QUOTE_ITEMS]] if depth > 0 else []
        omitted = len(value) > (_QUOTE_ITEMS if depth > 0 else 0)
    elif isinstance(value, Mapping):
        opening, closing = "{", "}"
        members = list(islice(value.items(), _QUOTE_ITEMS)) if depth > 0 else []
        items = [f"{_quote(key, 0)}: {_quote(member, depth - 1)}" for key, member in members]
        omitted = len(value) > (_QUOTE_ITEMS if depth > 0 else 0)
    else:
        return f"a value of type {type(value).__name__}"
    return opening + ", ".join(items + (["..."] if omitted else [])) + closing


def _label(entry: object) -> str:
    """Return how an entry of ``reason_codes`` or ``reason_context`` is named in a message.

    A string is named as itself, cut at ``_LABEL_CHARS`` characters; anything else (a number,
    null, a boolean, an array, an object) by a bounded rendering of it (``_quote``), so that a
    message about it can always be built, however the value is nested or wide.
    """

    if isinstance(entry, str):
        return entry if len(entry) <= _LABEL_CHARS else entry[:_LABEL_CHARS] + "..."
    return _quote(entry)


def _context_label(entry: object, catalog: ReasonCodesCatalog) -> str | None:
    """Return how a ``reason_context`` entry that names no catalog code is reported, else ``None``.

    An entry names a catalog code only when it is an object whose ``code`` is a string the
    catalog defines. A ``code`` of another type is named by a bounded rendering, as an entry of
    ``reason_codes`` is; an entry with no ``code``, or that is not an object, is named by
    what it lacks.
    """

    if not isinstance(entry, Mapping):
        return f"{_quote(entry)} (not an object)"
    if "code" not in entry:
        return "an entry without a code"
    code = entry["code"]
    if isinstance(code, str) and code in catalog:
        return None
    return _label(code)


def _identity(entry: object) -> str:
    """Return a key under which two entries are equal exactly when they are the same JSON value.

    The key is ``json_value_key``'s, the one the validator's ``uniqueItems`` uses, so the schema
    and this module find the same duplicates. Numbers compare by the binary64 value they are
    read as (canonicalization-and-hashing.md: every comparison reads that value): 1, 1.0 and
    1e0 are one entry, cited twice, as both reference verifiers find. Members compare in any
    order, and a value canonicalization would refuse (a noncharacter, a lone surrogate, an
    integer beyond 2^53 - 1) is still compared by value.
    """

    return json_value_key(entry)


def verdict_grounds_errors(summary: Mapping[str, object], catalog: ReasonCodesCatalog | None = None) -> list[str]:
    """Return the LCP-0008 rule violations in ``summary``; empty means conforming.

    This checks the three rules JSON Schema cannot carry, plus the two context rules: that
    actionable codes carry context, and that a context entry cites a code the catalog
    defines. It also checks VG-1 (``reason_codes`` is present, non-empty and free of
    duplicates), which the schema enforces too: a caller may reach this function without
    validating against the schema first, and verdict-grounds.md requires a conforming
    checker to apply the rule independently of schema validation. Run both checks; each
    covers what the other cannot.

    Errors are returned rather than raised so that a caller can report every violation at
    once. The exceptions are the two preconditions the specification says terminate the
    check: a VG-1 violation (absent, empty or duplicated codes) and a code the catalog does
    not define are each reported alone.

    Nothing in the document makes this function raise. The rules apply to any JSON value,
    valid against the schema or not (verdict-grounds.md section 1). An entry of
    ``reason_codes`` that is not a string (a number, null, a boolean, an array or an object)
    is a code the catalog does not define (VG-2). A ``reason_context`` entry that is not an
    object, has no ``code`` or whose ``code`` is not a string names no catalog code and is
    reported under VG-7, and a ``reason_context`` that is not an array is treated as absent.
    A ``key_checks`` that is not an array, an object or null is treated as absent (VG-5).
    A ``status`` outside the closed status vocabulary is reported as
    ``verdict_outside_vocabulary`` before the VG-3 contradiction it also is.
    """
    cat = catalog if catalog is not None else load_reason_codes_catalog()
    errors: list[str] = []

    if not isinstance(summary, Mapping):
        errors.append("reason_codes_absent: a verdict must cite the grounds for it")
        return errors

    status = summary.get("status")
    raw_codes = summary.get("reason_codes")
    entries: Sequence[object] = tuple(raw_codes) if isinstance(raw_codes, (list, tuple)) else ()

    if not entries:
        # The schema also rejects this. It is checked here too because this function is the
        # one a verifier calls, and a caller may not have run the schema.
        errors.append("reason_codes_absent: a verdict must cite the grounds for it")
        return errors

    # VG-1 also requires the entries to be unique, and VG-1 is a terminating precondition:
    # a duplicate is reported alone, before the catalog lookup and the severity rules. Equality
    # is JSON equality, so two equal non-string entries are a duplicate too; counting is one
    # pass, linear in the number of entries.
    seen: dict[str, object] = {}
    repeated: dict[str, object] = {}
    for entry in entries:
        key = _identity(entry)
        if key in seen:
            repeated[key] = seen[key]
        else:
            seen[key] = entry
    if repeated:
        duplicated = sorted(_label(entry) for entry in repeated.values())
        errors.append("reason_codes_duplicated: " + ", ".join(duplicated) + " (VG-1 requires unique entries)")
        return errors

    unknown_codes = sorted(_label(c) for c in entries if not isinstance(c, str) or c not in cat)
    if unknown_codes:
        errors.append(
            "reason_code_not_in_catalog: "
            + ", ".join(unknown_codes)
            + " (vocabulary "
            + cat.reason_code_vocabulary
            + ")"
        )
        return errors

    # From here on, every entry is a string the catalog defines.
    codes: Sequence[str] = tuple(c for c in entries if isinstance(c, str))

    if not (isinstance(status, str) and status in VERIFICATION_STATUSES):
        # VG-3 also refuses this status, since no such value equals an implied status; the
        # diagnostic says what is wrong with it, because the two defects call for different
        # fixes.
        errors.append(
            f"verdict_outside_vocabulary: status={_quote(_label(status))} is not one of "
            + ", ".join(VERIFICATION_STATUSES)
        )

    implied = status_for_codes(codes, cat)
    if status != implied:
        errors.append(
            f"status_contradicts_grounds: status={_quote(status)} but the cited codes imply "
            f"{implied!r} (highest severity {max_severity(codes, cat)!r})"
        )

    if status == "pass" and not any(cat.get(c).severity == "info" for c in codes):
        errors.append(
            "pass_without_affirmative_ground: a pass must cite at least one info-severity "
            "code, such as INTEGRITY_OK or AUTHORIZATION_VERIFIED"
        )

    if status == "pass":
        # A pass says what it checked. `key_checks` is typed as array-or-object-or-null,
        # so emptiness has three shapes and all three mean the same thing here. A value of
        # any other type is treated as absent (section 1: the rules apply to any JSON value):
        # a string or true is not a key check.
        checks = summary.get("key_checks")
        if not (isinstance(checks, (list, tuple, Mapping)) and checks):
            errors.append("pass_without_key_checks: a pass must report the checks it ran, not only that they succeeded")

    # A reason_context that is not an array is treated as absent: it has no entries for VG-7,
    # and the obligations of VG-6 stay unmet.
    raw_context = summary.get("reason_context")
    context: Sequence[object] = tuple(raw_context) if isinstance(raw_context, (list, tuple)) else ()
    context_codes = {
        entry["code"] for entry in context if isinstance(entry, Mapping) and isinstance(entry.get("code"), str)
    }
    # `reason_context[].code` is a plain string in the schema rather than a second copy of
    # the enum, and the schema names this function as the place the vocabulary is checked:
    # a context entry citing a code the catalog does not define is refused here, and so is
    # an entry that names no code at all (not an object, no `code`, or a `code` that is not
    # a string), which explains nothing for VG-6 either.
    unknown_context_codes = sorted({label for entry in context if (label := _context_label(entry, cat)) is not None})
    if unknown_context_codes:
        errors.append(
            "reason_context_code_not_in_catalog: "
            + ", ".join(unknown_context_codes)
            + " (vocabulary "
            + cat.reason_code_vocabulary
            + ")"
        )

    missing_context = sorted(
        c for c in codes if cat.get(c).severity in STATUSES_REQUIRING_CONTEXT and c not in context_codes
    )
    if missing_context:
        errors.append(
            "reason_context_missing: "
            + ", ".join(missing_context)
            + " are actionable severities and must carry context saying what to act on"
        )

    return errors
