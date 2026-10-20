"""Loader of the reason-code catalog.

This module loads the public reason-code catalog, the companion of the
``loquitur.reason_codes.v1`` vocabulary, from package data and exposes it as frozen,
typed data. The catalog gives three narratives for every reason code of the vocabulary,
one per audience:

- ``technical``: a neutral voice, for engineers who integrate a verifier;
- ``compliance``: an assertive voice, for security, audit and compliance officers;
- ``executive``: an assertive non-technical voice, for board and investor reporting.

The catalog is a static JSON file with a public schema. A narrative renderer derives its
output deterministically from the reason codes and the verdict, so this loader returns
frozen dataclasses that are safe to cache.

The catalog contract is narrow:

- every reason code of the ``loquitur.reason_codes.v1`` vocabulary is in the catalog;
- every entry carries all three audience narratives;
- the catalog schema bounds the length of each narrative.

This module renders no narrative for a verdict; it loads and exposes the catalog data.
The renderer is ``loquitur.verify.narrative`` in ``loquitur-verify-py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources.abc import Traversable
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from .errors import LoquiturSchemasError
from .inventory import schema_data_root

CATALOG_VERSION: Final[str] = "2.0.0"
CATALOG_VOCABULARY: Final[str] = "loquitur.reason_codes.v1"
CATALOG_AUDIENCES: Final[tuple[str, ...]] = ("technical", "compliance", "executive")
CATALOG_RELATIVE_PATH: Final[Path] = (
    Path("reason_codes_catalog") / f"v{CATALOG_VERSION.rsplit('.', 1)[0]}" / "catalog.json"
)


class ReasonCodesCatalogError(LoquiturSchemasError):
    """Raised when the reason codes catalog cannot be loaded or is malformed."""


@dataclass(frozen=True)
class TechnicalNarrative:
    """Narrative for engineers who integrate a verifier."""

    headline: str
    detail: str


@dataclass(frozen=True)
class ComplianceNarrative:
    """Narrative for security, audit and compliance officers."""

    headline: str
    consequence: str
    required_action: str


@dataclass(frozen=True)
class ExecutiveNarrative:
    """Narrative for board, investor and other non-technical readers."""

    summary: str


@dataclass(frozen=True)
class CatalogEntry:
    """Catalog entry for a single reason code.

    Each entry binds a reason code to three audience narratives. Severity and category
    are copied from the reason-code taxonomy so that a reader who has this package and
    nothing else can use the catalog on its own.
    """

    code: str
    severity: str
    category: str
    technical: TechnicalNarrative
    compliance: ComplianceNarrative
    executive: ExecutiveNarrative


@dataclass(frozen=True)
class ReasonCodesCatalog:
    """Loaded and validated reason codes catalog.

    The instance is frozen and safe to cache: ``entries`` and ``composition_templates`` are
    read-only mappings all the way down, since the one cached instance is shared by every
    caller in the process. A renderer reads it as a lookup table
    indexed by reason code, and as the only source of the lead and closing templates of
    each audience's verdict narrative.
    """

    catalog_version: str
    reason_code_vocabulary: str
    audiences: tuple[str, ...]
    entries: Mapping[str, CatalogEntry]
    composition_templates: Mapping[str, Mapping[str, Mapping[str, Mapping[str, str]]]]

    def get(self, code: str) -> CatalogEntry:
        """Return the catalog entry for ``code``.

        Raises:
            ReasonCodesCatalogError: If ``code`` is not in the catalog. The bundled catalog
                holds every code of ``loquitur.reason_codes.v1``, so a missing entry means
                a catalog of another version or a code outside the vocabulary.
        """
        try:
            return self.entries[code]
        except KeyError as exc:
            raise ReasonCodesCatalogError(
                f"reason code {code!r} is not present in catalog "
                f"v{self.catalog_version} ({self.reason_code_vocabulary})"
            ) from exc

    def template(self, audience: str, context: str, section: str, key: str) -> str:
        """Return one composition template of the catalog.

        Every coordinate of the template is an explicit argument, so a renderer takes its
        verdict prose from the catalog and holds none of its own.

        Raises:
            ReasonCodesCatalogError: If the catalog has no template at these coordinates.
        """
        try:
            return self.composition_templates[audience][context][section][key]
        except KeyError as exc:
            raise ReasonCodesCatalogError(
                f"missing narrative composition template: "
                f"audience={audience!r} context={context!r} "
                f"section={section!r} key={key!r}"
            ) from exc

    def __contains__(self, code: object) -> bool:
        return isinstance(code, str) and code in self.entries

    def __iter__(self) -> Iterator[str]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)


def catalog_data_path() -> Traversable:
    """Return the catalog JSON traversable resource.

    The package reads its bundled data through ``importlib.resources``, so the path works
    whether the package is installed from a wheel, in editable mode or from a zip file.
    """
    root = schema_data_root()
    target: Traversable = root
    for part in CATALOG_RELATIVE_PATH.parts:
        target = target.joinpath(part)
    return target


def _parse_composition_templates(
    payload: object,
) -> Mapping[str, Mapping[str, Mapping[str, Mapping[str, str]]]]:
    """Parse catalog-level verdict lead and closing templates.

    The templates live in the catalog, not in a verifier, so every consumer renders its
    narrative from the same text.
    """
    if not isinstance(payload, dict):
        raise ReasonCodesCatalogError("composition_templates must be a JSON object")
    parsed: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for audience in CATALOG_AUDIENCES:
        audience_payload = payload.get(audience)
        if not isinstance(audience_payload, dict):
            raise ReasonCodesCatalogError(f"composition_templates.{audience} must be a JSON object")
        parsed[audience] = {}
        for context in ("offline_verification", "registry_entry", "common"):
            context_payload = audience_payload.get(context)
            if not isinstance(context_payload, dict):
                raise ReasonCodesCatalogError(f"composition_templates.{audience}.{context} must be a JSON object")
            parsed[audience][context] = {}
            required_sections = ("closing",) if context == "common" else ("lead",)
            for section in required_sections:
                section_payload = context_payload.get(section)
                if not isinstance(section_payload, dict):
                    raise ReasonCodesCatalogError(
                        f"composition_templates.{audience}.{context}.{section} must be a JSON object"
                    )
                parsed[audience][context][section] = {}
                for key, text in section_payload.items():
                    if not isinstance(key, str) or not isinstance(text, str):
                        raise ReasonCodesCatalogError(
                            f"composition template keys and values must be strings under {audience}.{context}.{section}"
                        )
                    parsed[audience][context][section][key] = text
    return parsed


def _read_only(value: Any) -> Any:
    """Return ``value`` with every dict made a read-only mapping and every list a tuple, recursively.

    Reading is unchanged (indexing, iteration, ``in``, ``len``, ``.items()``), but an assignment
    raises ``TypeError``, so no caller can change the catalog every other caller reads.
    """
    if isinstance(value, dict):
        return MappingProxyType({key: _read_only(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_read_only(item) for item in value)
    return value


@lru_cache(maxsize=1)
def _closed_entry_values() -> tuple[frozenset[str], frozenset[str]]:
    """Return the closed ``severity`` and ``category`` sets, read from the catalog schema.

    The sets are read, not restated: a copy of the two closed vocabularies in the parser
    would be a second definition of each, and the parser exists to catch drift, not to
    cause it.
    """
    schema_path = schema_data_root().joinpath("reason_codes_catalog").joinpath("schema.json")
    try:
        properties = json.loads(schema_path.read_text(encoding="utf-8"))["$defs"]["CatalogEntry"]["properties"]
        return frozenset(properties["severity"]["enum"]), frozenset(properties["category"]["enum"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReasonCodesCatalogError(
            f"cannot read the closed severity and category sets from the catalog schema at {schema_path}: {exc}"
        ) from exc


def _entry_object(code: str, field: str, payload: Mapping[str, object]) -> Mapping[str, object]:
    """Return the JSON object at ``field``, or raise naming the entry and the field."""
    value = payload.get(field)
    if not isinstance(value, dict):
        raise ReasonCodesCatalogError(f"catalog entry for {code!r} has a missing or non-object {field}: {value!r}")
    return value


def _entry_text(code: str, field: str, container: Mapping[str, object]) -> str:
    """Return the string at ``field``, or raise; a value that is not a string is not coerced.

    ``str()`` of a JSON ``null`` is the four-letter text ``"None"``, which a renderer would
    take for prose and print to a reader.
    """
    value = container.get(field.rsplit(".", 1)[-1])
    if not isinstance(value, str):
        raise ReasonCodesCatalogError(f"catalog entry for {code!r} has a missing or non-string {field}: {value!r}")
    return value


def _parse_entry(code: str, payload: Mapping[str, object]) -> CatalogEntry:
    """Parse one catalog entry from its JSON object.

    The loader does not validate the catalog against its schema, so this parser is the only
    check between a malformed bundled catalog and a narrative rendered from it.

    Every field is type-checked, never coerced, and every structural check raises rather
    than asserts, so it holds under ``python -O`` too. Severity is what ``verdict_grounds``
    turns into a verdict: a severity coerced from ``12`` to ``"12"`` would be a verdict the
    parser invented, and an entry filed under one key that declares another code would be
    read under the wrong code.
    """
    severities, categories = _closed_entry_values()

    declared_code = _entry_text(code, "code", payload)
    if declared_code != code:
        raise ReasonCodesCatalogError(
            f"catalog entry filed under {code!r} declares code {declared_code!r}; the map key and the entry "
            f"must name the same reason code, since every consumer indexes by the key"
        )

    severity = _entry_text(code, "severity", payload)
    if severity not in severities:
        raise ReasonCodesCatalogError(
            f"catalog entry for {code!r} declares severity {severity!r}, outside the closed set {sorted(severities)}"
        )

    category = _entry_text(code, "category", payload)
    if category not in categories:
        raise ReasonCodesCatalogError(
            f"catalog entry for {code!r} declares category {category!r}, outside the closed set {sorted(categories)}"
        )

    technical_raw = _entry_object(code, "technical", payload)
    compliance_raw = _entry_object(code, "compliance", payload)
    executive_raw = _entry_object(code, "executive", payload)

    return CatalogEntry(
        code=declared_code,
        severity=severity,
        category=category,
        technical=TechnicalNarrative(
            headline=_entry_text(code, "technical.headline", technical_raw),
            detail=_entry_text(code, "technical.detail", technical_raw),
        ),
        compliance=ComplianceNarrative(
            headline=_entry_text(code, "compliance.headline", compliance_raw),
            consequence=_entry_text(code, "compliance.consequence", compliance_raw),
            required_action=_entry_text(code, "compliance.required_action", compliance_raw),
        ),
        executive=ExecutiveNarrative(
            summary=_entry_text(code, "executive.summary", executive_raw),
        ),
    )


@lru_cache(maxsize=1)
def load_reason_codes_catalog() -> ReasonCodesCatalog:
    """Load the bundled reason-code catalog.

    The loader reads the JSON file from the package data root, parses it into frozen
    dataclasses and returns one :class:`ReasonCodesCatalog` instance, cached for the life
    of the process.

    Raises:
        ReasonCodesCatalogError: If the catalog file is missing, unreadable or structurally
            invalid, or targets another reason-code vocabulary.
    """
    path = catalog_data_path()
    if not path.is_file():
        raise ReasonCodesCatalogError(
            f"catalog file not found at {path}: the package is installed without its "
            f"reason-code catalog, which is a packaging error"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReasonCodesCatalogError(f"cannot read or parse the catalog at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ReasonCodesCatalogError(f"catalog at {path} is not a JSON object")

    catalog_version = raw.get("catalog_version")
    vocabulary = raw.get("reason_code_vocabulary")
    audiences = raw.get("audiences")
    entries_raw = raw.get("entries")
    composition_templates_raw = raw.get("composition_templates")

    if not isinstance(catalog_version, str):
        raise ReasonCodesCatalogError("catalog_version must be a string")
    if vocabulary != CATALOG_VOCABULARY:
        raise ReasonCodesCatalogError(
            f"catalog targets vocabulary {vocabulary!r}; the loader expects {CATALOG_VOCABULARY!r}"
        )
    if not isinstance(audiences, list) or tuple(audiences) != CATALOG_AUDIENCES:
        raise ReasonCodesCatalogError(f"catalog audiences must be exactly {CATALOG_AUDIENCES}, got {audiences!r}")
    if not isinstance(entries_raw, dict):
        raise ReasonCodesCatalogError("catalog entries must be a JSON object")

    parsed_entries = {
        code: _parse_entry(code, payload) for code, payload in entries_raw.items() if isinstance(payload, dict)
    }
    parsed_composition_templates = _parse_composition_templates(composition_templates_raw)
    if len(parsed_entries) != len(entries_raw):
        raise ReasonCodesCatalogError("at least one catalog entry is not a JSON object")

    return ReasonCodesCatalog(
        catalog_version=catalog_version,
        reason_code_vocabulary=vocabulary,
        audiences=CATALOG_AUDIENCES,
        entries=_read_only(parsed_entries),
        composition_templates=_read_only(parsed_composition_templates),
    )


__all__ = [
    "CATALOG_AUDIENCES",
    "CATALOG_VERSION",
    "CATALOG_VOCABULARY",
    "CatalogEntry",
    "ComplianceNarrative",
    "ExecutiveNarrative",
    "ReasonCodesCatalog",
    "ReasonCodesCatalogError",
    "TechnicalNarrative",
    "catalog_data_path",
    "load_reason_codes_catalog",
]
