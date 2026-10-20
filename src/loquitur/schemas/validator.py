"""Validator for the bundled schemas, and the strict JSON loader it reads documents with.

The validator implements the JSON Schema keyword subset the bundled schemas use,
``SUPPORTED_SCHEMA_KEYWORDS``. It is not a general-purpose Draft 2020-12 implementation:
a schema that uses any other keyword is refused, never validated in part.
"""

from __future__ import annotations

import calendar
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn

import rfc8785

from .errors import LoquiturSchemasError
from .inventory import (
    PUBLIC_CANONICAL_SCHEMA_NAMES,
    PUBLIC_SCHEMA_NAMES_BY_ID,
    SchemaNotFoundError,
    load_schema_json,
)


class SchemaValidationUsageError(ValueError, LoquiturSchemasError):
    """Raised when validation cannot start because the request is malformed."""


SUPPORTED_SCHEMA_KEYWORDS: frozenset[str] = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "const",
        "enum",
        "minLength",
        "minItems",
        "minimum",
        "pattern",
        "uniqueItems",
        "example",
        "description",
        "deprecated",
        "oneOf",
    }
)

OBJECT_TYPE_TO_SCHEMA_NAME: dict[str, str] = {
    "change_summary": "change_summary.schema.json",
    "coverage_summary": "coverage_summary.schema.json",
    "lineage_summary": "lineage_summary.schema.json",
    "registry_entry": "registry_entry.schema.json",
    "trust_registry": "trust_registry.schema.json",
    "verification_receipt": "verification_receipt.schema.json",
    "verification_summary": "verification_summary.schema.json",
}


@dataclass(frozen=True)
class ValidationErrorDetail:
    """A stable, machine-readable schema validation error."""

    path: str
    code: str
    message: str
    expected: Any | None = None
    actual: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "code": self.code,
            "message": self.message,
        }
        if self.expected is not None:
            payload["expected"] = self.expected
        if self.actual is not None:
            payload["actual"] = self.actual
        return payload


@dataclass(frozen=True)
class ValidationResult:
    """Structured validation result for one JSON document."""

    ok: bool
    schema_name: str
    object_type: str | None
    errors: tuple[ValidationErrorDetail, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_name": self.schema_name,
            "object_type": self.object_type,
            "error_count": len(self.errors),
            "errors": [error.to_dict() for error in self.errors],
        }


def schema_name_for_object_type(object_type: str) -> str:
    """Return bundled schema filename for a canonical object type."""

    try:
        return OBJECT_TYPE_TO_SCHEMA_NAME[object_type]
    except KeyError as exc:
        raise SchemaNotFoundError(f"unsupported public canonical object_type: {object_type}") from exc


def resolve_schema_name(schema_or_object_type: str) -> str:
    """Resolve either a schema filename or a canonical object_type."""

    if schema_or_object_type in PUBLIC_SCHEMA_NAMES_BY_ID:
        return PUBLIC_SCHEMA_NAMES_BY_ID[schema_or_object_type]
    if schema_or_object_type in PUBLIC_CANONICAL_SCHEMA_NAMES:
        return schema_or_object_type
    if schema_or_object_type.endswith(".schema.json"):
        # Preserve the stronger not-found error from inventory.
        load_schema_json(schema_or_object_type)
        return schema_or_object_type
    return schema_name_for_object_type(schema_or_object_type)


# The protocol's nesting limit: a scalar has depth 0 and a container one more than its
# deepest child, and a document deeper than this is refused at load.
MAX_JSON_NESTING_DEPTH = 64

# RFC 8785 / ECMAScript safe-integer bound, applied by value at load.
_SAFE_INTEGER_MAX = 2**53 - 1

# A JSON string token (terminated or not) or a structural bracket. Scanning tokens rather
# than characters keeps brackets inside strings from counting as nesting.
_NESTING_TOKEN_RE = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"?|[\[\]{}]', re.DOTALL)
_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")
# Input strictness rule 9 (RFC 7493 section 2.1): the 66 noncharacters, U+FDD0..U+FDEF and the
# last two code points of each of the 17 planes. JSON decoding has already turned escapes, and
# escaped surrogate pairs, into the characters themselves.
_NONCHARACTER_RE = re.compile(
    "[\ufdd0-\ufdef"
    + "".join(chr(plane * 0x10000 + 0xFFFE) + chr(plane * 0x10000 + 0xFFFF) for plane in range(17))
    + "]"
)
# An integer spelled with more digits than this is beyond 2^53 - 1 (JSON has no leading zeros),
# decided without converting the text, so no digit-count limit of the host's int() is reached.
_SAFE_INTEGER_DIGITS = len(str(_SAFE_INTEGER_MAX))


def _nesting_depth_exceeds(text: str, limit: int) -> bool:
    """Return whether ``text`` nests brackets deeper than ``limit``, without recursing."""

    depth = 0
    for token in _NESTING_TOKEN_RE.finditer(text):
        char = token.group()
        if char in "[{":
            depth += 1
            if depth > limit:
                return True
        elif char in "]}":
            depth -= 1
    return False


def _canonical_input_violation(document: Any) -> str | None:
    """Return the first input-strictness rule the parsed document breaks, if any.

    Rules 2 to 4 of the protocol's input strictness, applied to the whole document, keys
    included: an integer-valued number beyond 2^53 - 1 whatever its spelling, a
    non-finite number (overflow such as ``1e400`` parses to infinity), and a lone
    surrogate. JSON decoding pairs escaped surrogates, so any surrogate left in a string
    is a lone one. The walk is iterative, so no document depth reaches the interpreter
    stack.
    """

    stack: list[Any] = [document]
    while stack:
        value = stack.pop()
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            if abs(value) > _SAFE_INTEGER_MAX:
                return "integer outside the safe range"
        elif isinstance(value, float):
            if not math.isfinite(value):
                return "non-finite number"
            if value.is_integer() and abs(value) > _SAFE_INTEGER_MAX:
                return "integer outside the safe range"
        elif isinstance(value, str):
            if _LONE_SURROGATE_RE.search(value):
                return "lone surrogate"
            if _NONCHARACTER_RE.search(value):
                return "noncharacter"
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                if _LONE_SURROGATE_RE.search(key):
                    return "lone surrogate in a member name"
                if _NONCHARACTER_RE.search(key):
                    return "noncharacter in a member name"
                stack.append(item)
    return None


def _integer_violation(text: str) -> str | None:
    """Return the strictness rule a JSON integer spelling breaks, read from its text, if any."""

    if len(text.lstrip("-")) > _SAFE_INTEGER_DIGITS or abs(int(text)) > _SAFE_INTEGER_MAX:
        return "integer outside the safe range"
    return None


def _decimal_or_none(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        # An exponent beyond what the decimal module represents (more than about 10^18).
        return None


def _float_violation(text: str, value: float) -> str | None:
    """Return the strictness rule a JSON number with a fraction or an exponent breaks, if any.

    ``value`` is the binary64 value nearest to ``text``, ties to even, which is how ``float``
    reads it. The number is valid only when the decimal value ``text`` spells equals the decimal
    value of the RFC 8785 serialization of ``value``: more precision or a smaller magnitude than
    binary64 holds is refused, not rounded.
    """

    if not math.isfinite(value):
        return "non-finite number"
    if value.is_integer() and abs(value) > _SAFE_INTEGER_MAX:
        return "integer outside the safe range"
    spelt = _decimal_or_none(text)
    if spelt is None:
        # Only a zero mantissa survives an exponent that large as a finite value.
        mantissa = text.lower().split("e", 1)[0]
        return None if value == 0 and not mantissa.strip("-+.0") else "number with excess precision"
    if spelt != Decimal(rfc8785.dumps(value).decode("ascii")):
        return "number with excess precision"
    return None


# The instant form every published schema holds a date-time member to. The pattern admits
# shapes that name no instant (February 30, second 60); input strictness rule 8 refuses them.
INSTANT_PATTERN = "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:([0-5][0-9]|60)Z$"
_INSTANT_FIELDS_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z")


def is_calendar_instant(value: object) -> bool:
    """Return whether ``value`` is ``YYYY-MM-DDTHH:MM:SSZ`` naming a real UTC second (input strictness rule 8).

    The second is one of the proleptic Gregorian calendar: year 0001 or later, a day that
    exists in its month (February 29 only in a leap year), hour at most 23, minute and second
    at most 59, so a leap second written as ``60`` is not an instant.
    """

    if not isinstance(value, str):
        return False
    match = _INSTANT_FIELDS_RE.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second = (int(group) for group in match.groups())
    if year < 1 or not 1 <= month <= 12:
        return False
    return 1 <= day <= calendar.monthrange(year, month)[1] and hour <= 23 and minute <= 59 and second <= 59


def _calendar_instant_error(path: str, value: str) -> ValidationErrorDetail:
    return ValidationErrorDetail(
        path=path,
        code="calendar_instant",
        message=f"string at {path} names no calendar instant",
        expected="a real UTC second, YYYY-MM-DDTHH:MM:SSZ",
        actual=value,
    )


def calendar_instant_errors(schema_or_object_type: str, instance: Any) -> tuple[ValidationErrorDetail, ...]:
    """Return an error for every string the schema holds to the instant pattern that names no calendar instant.

    JSON Schema cannot say that a date exists: the instant pattern admits
    ``2026-02-30T00:00:00Z``. ``validate_instance`` adds the rule the verifiers apply on top
    (input strictness rule 8): a string in the instant form that names no calendar second is a
    ``calendar_instant`` error, and a string outside the form a ``pattern_mismatch``. This
    function reports every such string, in the form or not, as a ``calendar_instant`` error,
    and nothing else the instance breaks.
    """

    schema = load_schema_json(resolve_schema_name(schema_or_object_type))
    errors: list[ValidationErrorDetail] = []
    _collect_instant_errors(schema, instance, "$", errors)
    return tuple(errors)


def _collect_instant_errors(schema: Any, value: Any, path: str, errors: list[ValidationErrorDetail]) -> None:
    # The walk follows the schema, which is a few levels deep, never the instance's own depth.
    if not isinstance(schema, Mapping):
        return
    if schema.get("pattern") == INSTANT_PATTERN and isinstance(value, str) and not is_calendar_instant(value):
        if all(error.path != path for error in errors):
            errors.append(_calendar_instant_error(path, value))
    for branch in schema.get("oneOf", ()) if isinstance(schema.get("oneOf"), list) else ():
        _collect_instant_errors(branch, value, path, errors)
    properties = schema.get("properties")
    if isinstance(value, dict) and isinstance(properties, Mapping):
        for key, child in properties.items():
            if key in value:
                _collect_instant_errors(child, value[key], f"{path}.{key}", errors)
    items = schema.get("items")
    if isinstance(value, list) and isinstance(items, Mapping):
        for index, item in enumerate(value):
            _collect_instant_errors(items, item, f"{path}[{index}]", errors)


def input_strictness_violation(value: Any) -> str | None:
    """Return the input strictness rule an in-memory JSON value breaks, if any.

    The value-level rules a loaded document is held to and an in-memory value can break: an
    integer-valued number beyond 2^53 - 1, a non-finite number, a lone surrogate or a
    noncharacter, in a value or a member name.
    """

    return _canonical_input_violation(value)


def load_json_document(path: str | Path) -> Any:
    """Return the JSON document at ``path``, read under the protocol's input strictness.

    Every way the file can fail to be a strict JSON document raises
    ``SchemaValidationUsageError``, which the CLI maps to exit 64: a missing or unreadable
    path, bytes that are not UTF-8 or that start with a byte-order mark, invalid JSON, a
    duplicate member name, a non-finite number, nesting deeper than
    ``MAX_JSON_NESTING_DEPTH``, an integer-valued number beyond 2^53 - 1, a number with excess
    precision, a lone surrogate, or a noncharacter. These are the protocol's input strictness
    rules, which align JSON input with I-JSON (RFC 7493) under RFC 8785. Numbers are read from
    their text, so an integer of any length is refused by value and never reaches the host's
    digit-count limit for ``int``. Neither ``UnicodeDecodeError``, ``OSError`` nor any other
    ``ValueError`` escapes from here.
    """

    json_path = Path(path)

    def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        # I-JSON: duplicate member names are invalid input.
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise SchemaValidationUsageError(f"invalid JSON document {json_path}: duplicate object key {key!r}")
            obj[key] = value
        return obj

    def _reject_constant(name: str) -> NoReturn:  # NaN/Infinity are not valid canonical input
        raise SchemaValidationUsageError(f"invalid JSON document {json_path}: non-finite number {name}")

    def _refuse(violation: str) -> NoReturn:
        raise SchemaValidationUsageError(f"JSON document {json_path} violates canonical input strictness: {violation}")

    def _read_integer(text: str) -> int:
        violation = _integer_violation(text)
        if violation is not None:
            _refuse(violation)
        return int(text)

    def _read_float(text: str) -> float:
        value = float(text)
        violation = _float_violation(text, value)
        if violation is not None:
            _refuse(violation)
        return value

    try:
        text = json_path.read_bytes().decode("utf-8")
        if _nesting_depth_exceeds(text, MAX_JSON_NESTING_DEPTH):
            raise SchemaValidationUsageError(
                f"JSON document {json_path}: nesting exceeds the parser limit of {MAX_JSON_NESTING_DEPTH}"
            )
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
            parse_int=_read_integer,
            parse_float=_read_float,
        )
    except SchemaValidationUsageError:
        raise
    except FileNotFoundError as exc:
        raise SchemaValidationUsageError(f"JSON document not found: {json_path}") from exc
    except OSError as exc:
        raise SchemaValidationUsageError(f"cannot read JSON document {json_path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise SchemaValidationUsageError(
            f"invalid JSON document {json_path}: not UTF-8 (byte {exc.start}: {exc.reason})"
        ) from exc
    except RecursionError as exc:
        # The scan above refuses every document deeper than the limit before the decoder runs,
        # so a RecursionError here comes from a document the protocol admits and a host whose
        # stack cannot hold it: a setup error, named as one rather than as a nesting rule the
        # document keeps. Only an interpreter whose C decoder counts against a lowered
        # sys.setrecursionlimit reaches it, which Python 3.11 does and 3.12 onwards does not.
        raise SchemaValidationUsageError(
            f"JSON document {json_path}: the interpreter's recursion limit is too low to parse it"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SchemaValidationUsageError(f"invalid JSON document {json_path}: {exc.msg}") from exc
    except ValueError as exc:
        # Defense in depth: every number is read by the hooks above, so no decoder ValueError
        # (such as the host's digit-count limit for int) is expected here; one that occurs is
        # still a document that cannot be read, never a traceback.
        raise SchemaValidationUsageError(f"invalid JSON document {json_path}: {exc}") from exc
    violation = _canonical_input_violation(document)
    if violation is not None:
        _refuse(violation)
    return document


def validate_file(schema_or_object_type: str, json_path: str | Path) -> ValidationResult:
    """Validate a JSON file against one bundled canonical schema."""

    instance = load_json_document(json_path)
    return validate_instance(schema_or_object_type, instance)


def validate_instance(schema_or_object_type: str, instance: Any) -> ValidationResult:
    """Validate a Python JSON value against one bundled canonical schema."""

    schema_name = resolve_schema_name(schema_or_object_type)
    schema = load_schema_json(schema_name)
    _assert_supported_schema(schema_name, schema)
    errors = tuple(_validate_value(schema, instance, "$"))
    object_type = instance.get("object_type") if isinstance(instance, dict) else None
    return ValidationResult(ok=not errors, schema_name=schema_name, object_type=object_type, errors=errors)


def validate_by_object_type(instance: Mapping[str, Any]) -> ValidationResult:
    """Validate a canonical object by its own object_type field."""

    object_type = instance.get("object_type")
    if not isinstance(object_type, str):
        return ValidationResult(
            ok=False,
            schema_name="<unresolved>",
            object_type=None,
            errors=(
                ValidationErrorDetail(
                    path="$.object_type",
                    code="missing_or_invalid_object_type",
                    message="object_type must be a string to resolve a public schema",
                    expected=sorted(OBJECT_TYPE_TO_SCHEMA_NAME),
                    actual=object_type,
                ),
            ),
        )
    try:
        schema_name = schema_name_for_object_type(object_type)
    except SchemaNotFoundError:
        return ValidationResult(
            ok=False,
            schema_name="<unresolved>",
            object_type=object_type,
            errors=(
                ValidationErrorDetail(
                    path="$.object_type",
                    code="unsupported_object_type",
                    message=f"unsupported public canonical object_type: {object_type}",
                    expected=sorted(OBJECT_TYPE_TO_SCHEMA_NAME),
                    actual=object_type,
                ),
            ),
        )
    return validate_instance(schema_name, instance)


def _assert_supported_schema(schema_name: str, schema: Any) -> None:
    """Fail closed if a bundled schema starts using unsupported keywords.

    Property names are not JSON Schema keywords, so recurse only through known
    schema-bearing keyword values rather than through every mapping value.
    """

    if not isinstance(schema, dict):
        return

    unsupported = sorted(str(key) for key in schema if str(key) not in SUPPORTED_SCHEMA_KEYWORDS)
    if unsupported:
        raise SchemaValidationUsageError(
            f"schema {schema_name} uses unsupported validator keywords: {', '.join(unsupported)}"
        )

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for child_schema in properties.values():
            _assert_supported_schema(schema_name, child_schema)

    items = schema.get("items")
    if isinstance(items, dict):
        _assert_supported_schema(schema_name, items)

    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        _assert_supported_schema(schema_name, additional)

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        for child_schema in one_of:
            _assert_supported_schema(schema_name, child_schema)


def _validate_value(schema: Mapping[str, Any], value: Any, path: str) -> list[ValidationErrorDetail]:
    errors: list[ValidationErrorDetail] = []

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        candidate_errors = [_validate_value(candidate, value, path) for candidate in one_of]
        matches = [index for index, failures in enumerate(candidate_errors) if not failures]
        if len(matches) == 1:
            return []
        if not matches:
            # Preserve actionable child failures rather than hiding them behind
            # a generic oneOf error. Select the closest branch(es), then
            # de-duplicate identical details. This is deterministic and keeps
            # strict additional-property paths visible to callers.
            minimum = min(len(failures) for failures in candidate_errors)
            selected = [failures for failures in candidate_errors if len(failures) == minimum]
            detailed: list[ValidationErrorDetail] = []
            seen: set[tuple[str, str, str]] = set()
            for failures in selected:
                for failure in failures:
                    marker = (failure.path, failure.code, failure.message)
                    if marker not in seen:
                        seen.add(marker)
                        detailed.append(failure)
            if detailed:
                return detailed
        return [
            ValidationErrorDetail(
                path=path,
                code="one_of_mismatch",
                message=f"value at {path} must match exactly one allowed schema",
                expected=len(one_of),
                actual=len(matches),
            )
        ]

    if "type" in schema and not _matches_type(value, schema["type"]):
        errors.append(
            ValidationErrorDetail(
                path=path,
                code="type_mismatch",
                message=f"value at {path} has wrong type",
                expected=schema["type"],
                actual=_json_type(value),
            )
        )
        # Continue no deeper once the container type is wrong.
        return errors

    if "const" in schema and value != schema["const"]:
        errors.append(
            ValidationErrorDetail(
                path=path,
                code="const_mismatch",
                message=f"value at {path} does not match required constant",
                expected=schema["const"],
                actual=value,
            )
        )

    if "enum" in schema and value not in schema["enum"]:
        errors.append(
            ValidationErrorDetail(
                path=path,
                code="enum_mismatch",
                message=f"value at {path} is not one of the allowed values",
                expected=schema["enum"],
                actual=value,
            )
        )

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            errors.append(
                ValidationErrorDetail(
                    path=path,
                    code="min_length",
                    message=f"string at {path} is shorter than minLength",
                    expected=schema["minLength"],
                    actual=len(value),
                )
            )
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            errors.append(
                ValidationErrorDetail(
                    path=path,
                    code="pattern_mismatch",
                    message=f"string at {path} does not match required pattern",
                    expected=schema["pattern"],
                    actual=value,
                )
            )
        elif schema.get("pattern") == INSTANT_PATTERN and not is_calendar_instant(value):
            # Input strictness rule 8, which the pattern cannot express: a string in the instant
            # form must name a real UTC second, as the verifiers and the signing gate require.
            errors.append(_calendar_instant_error(path, value))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(
                ValidationErrorDetail(
                    path=path,
                    code="minimum",
                    message=f"number at {path} is below minimum",
                    expected=schema["minimum"],
                    actual=value,
                )
            )

    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            errors.append(
                ValidationErrorDetail(
                    path=path,
                    code="min_items",
                    message=f"array at {path} has fewer items than minItems",
                    expected=schema["minItems"],
                    actual=len(value),
                )
            )
        if schema.get("uniqueItems") is True:
            seen_items: set[str] = set()
            for index, item in enumerate(value):
                # By value, as Draft 2020-12 compares instances: 2 and 2.0 are one item.
                item_marker = json_value_key(item)
                if item_marker in seen_items:
                    errors.append(
                        ValidationErrorDetail(
                            path=f"{path}[{index}]",
                            code="unique_items",
                            message="array item is duplicated but uniqueItems is true",
                            actual=item,
                        )
                    )
                    break
                seen_items.add(item_marker)
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_validate_value(item_schema, item, f"{path}[{index}]"))

    if isinstance(value, dict):
        declared_properties = schema.get("properties")
        declared_required = schema.get("required")
        properties: dict[str, Any] = declared_properties if isinstance(declared_properties, dict) else {}
        required: list[Any] = declared_required if isinstance(declared_required, list) else []
        for required_name in required:
            if required_name not in value:
                errors.append(
                    ValidationErrorDetail(
                        path=f"{path}.{required_name}",
                        code="required",
                        message=f"required field missing: {required_name}",
                        expected="present",
                        actual="missing",
                    )
                )
        if schema.get("additionalProperties") is False:
            for key in sorted(value):
                if key not in properties:
                    errors.append(
                        ValidationErrorDetail(
                            path=f"{path}.{key}",
                            code="additional_property",
                            message=f"unexpected field: {key}",
                            expected="not present",
                            actual=value[key],
                        )
                    )
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                errors.extend(_validate_value(child_schema, value[key], f"{path}.{key}"))

    return errors


def _matches_type(value: Any, schema_type: Any) -> bool:
    if isinstance(schema_type, list):
        return any(_matches_type(value, item) for item in schema_type)
    if schema_type == "null":
        return value is None
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        # Draft 2020-12 section 6.1.1: an integer is any number with a zero fractional part,
        # whatever its spelling. `2.0` and `2` are also the same RFC 8785 bytes, so telling
        # them apart would give identical committed bytes two different verdicts.
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        return isinstance(value, float) and math.isfinite(value) and value.is_integer()
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "object":
        return isinstance(value, dict)
    return False


def json_value_key(value: Any) -> str:
    """Return a key under which two values are equal exactly when they are the same JSON value.

    A string is keyed as itself. Anything else is serialized with the members of each object
    sorted by name and every number written as the binary64 value it is read as
    (canonicalization-and-hashing.md: every comparison reads that value), so 1, 1.0 and 1e0
    are one value, as are ``2**60`` and ``float(2**60)``, and two objects that differ only in
    member order are one value. Booleans are not numbers in JSON and are left alone.

    Unlike RFC 8785 canonicalization the key never refuses a value: a lone surrogate, a
    noncharacter, an integer beyond 2^53 - 1 or a nesting deeper than
    ``MAX_JSON_NESTING_DEPTH`` is keyed by its value too, so two such values that are equal
    are found equal. NaN and the infinities, which JSON cannot spell, are keyed as ``nan``,
    ``inf`` and ``-inf``, which no finite number is written as; an integer too large for
    binary64 is read, as binary64 rounds it, as the infinity of its sign. The walk is
    iterative, so no value depth reaches the interpreter stack.
    """

    if isinstance(value, str):
        return "s:" + value
    parts: list[str] = []
    # Each pending item is either a fragment written as it stands or a value still to write.
    pending: list[tuple[bool, Any]] = [(False, value)]
    while pending:
        is_fragment, item = pending.pop()
        if is_fragment:
            parts.append(item)
        elif item is None or isinstance(item, (bool, str)):
            # ensure_ascii escapes a lone surrogate instead of failing to encode it.
            parts.append(json.dumps(item))
        elif isinstance(item, (int, float)):
            parts.append(_binary64_spelling(item))
        elif isinstance(item, (list, tuple)):
            pending.append((True, "]"))
            for index in reversed(range(len(item))):
                pending.append((False, item[index]))
                if index:
                    pending.append((True, ","))
            pending.append((True, "["))
        elif isinstance(item, Mapping):
            members = sorted(
                ((name if isinstance(name, str) else repr(name), member) for name, member in item.items()),
                key=lambda pair: pair[0],
            )
            pending.append((True, "}"))
            for index in reversed(range(len(members))):
                name, member = members[index]
                pending.append((False, member))
                pending.append((True, json.dumps(name) + ":"))
                if index:
                    pending.append((True, ","))
            pending.append((True, "{"))
        else:
            # Not a JSON value at all; keyed by its repr, in a form no JSON value is written as.
            parts.append("?" + json.dumps(repr(item)))
    return "j:" + "".join(parts)


def _binary64_spelling(number: int | float) -> str:
    """Return how ``json_value_key`` writes ``number``: the binary64 value it is read as."""

    try:
        reading = float(number)
    except OverflowError:
        reading = math.inf if number > 0 else -math.inf
    if math.isfinite(reading) and reading.is_integer():
        # -0.0 is written 0, as RFC 8785 writes it.
        return str(int(reading))
    return repr(reading)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__
