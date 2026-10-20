"""Registered vocabularies: the values of asset types, workflows and anchoring methods.

loquitur-protocol `verification-vocabularies.md` §5 to §9. The schemas hold `asset_type`,
`workflow` and `anchor.method` to an identifier grammar and nothing more; the values are
registered in one versioned document per kind. This package bundles the protocol's documents,
byte for byte, under `data/registered_vocabularies/`, beside the schema they satisfy.

Two functions are public: `load_registered_vocabulary`, which returns the bundled document of a
kind or reads and checks one an operator supplies, and `value_status`, which says whether a value
is known, unknown or invalid against a document.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

from .errors import LoquiturSchemasError
from .validator import SchemaValidationUsageError, load_json_document

__all__ = [
    "REGISTERED_VOCABULARY_KINDS",
    "RegisteredVocabularyError",
    "load_registered_vocabulary",
    "value_status",
]

REGISTERED_VOCABULARY_KINDS: tuple[str, ...] = ("asset_type", "workflow", "anchoring_method")

# verification-vocabularies.md §7: the identifier grammar of every governed member.
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_]{0,63}")
# §6: MAJOR.MINOR.PATCH, each at most nine digits with no leading zero, and no suffix.
_VERSION = re.compile(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})")
_DOCUMENT_MEMBERS = frozenset({"object_type", "schema_version", "kind", "version", "values"})
_VALUE_MEMBERS = frozenset({"since", "status", "title", "profile"})
_STATUSES = ("active", "deprecated")
# The whitespace set W of bundle-objects.md: a string made only of these code points is empty.
_W = frozenset(
    [*range(0x09, 0x0E), *range(0x1C, 0x20), 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B)]
    + [0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF]
)


class RegisteredVocabularyError(ValueError, LoquiturSchemasError):
    """A registered vocabulary document is refused (verification-vocabularies.md §8)."""


def load_registered_vocabulary(kind: str, path: str | Path | None = None) -> dict[str, Any]:
    """Return the registered vocabulary document of ``kind``.

    With no ``path``, the document this package bundles. With a ``path``, the document there,
    read under input strictness and refused unless it satisfies verification-vocabularies.md §6
    and registers ``kind``.

    Raises:
        RegisteredVocabularyError: If ``kind`` is not a kind of §5, or the document is refused.
    """
    if kind not in REGISTERED_VOCABULARY_KINDS:
        raise RegisteredVocabularyError(f"not a kind of registered vocabulary: {kind!r}")
    if path is None:
        data = resources.files("loquitur.schemas").joinpath("data", "registered_vocabularies", f"{kind}.json")
        document: Any = json.loads(data.read_bytes().decode("utf-8"))
    else:
        try:
            document = load_json_document(path)
        except SchemaValidationUsageError as exc:
            raise RegisteredVocabularyError(str(exc)) from exc
    problems = _contract_problems(document)
    if problems:
        raise RegisteredVocabularyError(f"the {kind} vocabulary is malformed: {problems[0]}")
    if document["kind"] != kind:
        raise RegisteredVocabularyError(f"the document registers the kind {document['kind']}, not {kind}")
    return dict(document)


def value_status(value: object, vocabulary: Mapping[str, Any]) -> str:
    """Return whether ``value`` is ``"known"``, ``"unknown"`` or ``"invalid"`` (§7).

    Invalid when it is not an identifier; known when it names a value of ``vocabulary``,
    active or deprecated; unknown otherwise.
    """
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        return "invalid"
    return "known" if value in vocabulary["values"] else "unknown"


def _version(text: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(text)
    assert match is not None
    return int(match[1]), int(match[2]), int(match[3])


def _not_empty(value: object) -> bool:
    return isinstance(value, str) and any(ord(character) not in _W for character in value)


def _contract_problems(document: Any) -> list[str]:
    """Return every way ``document`` breaks verification-vocabularies.md §6, first problem first."""
    if not isinstance(document, dict):
        return ["the document is not an object"]
    problems: list[str] = []
    if set(document) != _DOCUMENT_MEMBERS:
        problems.append(f"the document's members are not exactly {sorted(_DOCUMENT_MEMBERS)}")
    if document.get("object_type") != "registered_vocabulary":
        problems.append("object_type is not registered_vocabulary")
    if document.get("schema_version") != "v1":
        problems.append("schema_version is not v1")
    if document.get("kind") not in REGISTERED_VOCABULARY_KINDS:
        problems.append("kind is not a kind of registered vocabulary")
    version = document.get("version")
    if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        problems.append("version is not MAJOR.MINOR.PATCH")
        version = None
    values = document.get("values")
    if not isinstance(values, dict) or not values:
        problems.append("values is not an object with at least one member")
        return problems
    for name, entry in values.items():
        where = f"values/{name}"
        if _IDENTIFIER.fullmatch(name) is None:
            problems.append(f"{where}: the value is not an identifier")
        if not isinstance(entry, dict):
            problems.append(f"{where} is not an object")
            continue
        allowed = _VALUE_MEMBERS | ({"asset_types"} if document.get("kind") == "workflow" else set())
        if not _VALUE_MEMBERS <= set(entry) <= allowed:
            problems.append(f"{where}: the members are not those of a registered value of this kind")
        if document.get("kind") == "workflow" and "asset_types" not in entry:
            problems.append(f"{where}: a workflow carries asset_types")
        since = entry.get("since")
        if not isinstance(since, str) or _VERSION.fullmatch(since) is None:
            problems.append(f"{where}: since is not MAJOR.MINOR.PATCH")
        elif version is not None and _version(since) > _version(version):
            problems.append(f"{where}: since is later than version")
        if entry.get("status") not in _STATUSES:
            problems.append(f"{where}: status is neither active nor deprecated")
        if not _not_empty(entry.get("title")):
            problems.append(f"{where}: title is not a string with a code point outside W")
        if entry.get("profile") is not None and not _not_empty(entry.get("profile")):
            problems.append(f"{where}: profile is neither null nor a string with a code point outside W")
        if "asset_types" in entry:
            asset_types = entry["asset_types"]
            if (
                not isinstance(asset_types, list)
                or not asset_types
                or len(set(map(str, asset_types))) != len(asset_types)
                or not all(isinstance(item, str) and _IDENTIFIER.fullmatch(item) for item in asset_types)
            ):
                problems.append(f"{where}: asset_types is not a non-empty array of distinct identifiers")
    return problems
