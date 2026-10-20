"""Schema compatibility gate for the bundled public schemas.

This module freezes a contract baseline for the seven public schemas (five canonical
objects and two registry schemas, as ``inventory.py`` separates them) and provides a
deterministic gate that detects incompatible changes. The set is ``PUBLIC_SCHEMA_NAMES``.
The gate is scoped to the published schema package: it does not compare OpenAPI output or
any implementation's internal schemas.

Each property's contract is frozen to its full depth, nested ``properties``, ``required``,
``items`` and ``oneOf`` included, so deleting the v2 signature branch, adding Ed25519 to an
algorithm enum the protocol specification says 0.1 schemas must reject, widening
``public_key_hex`` to ``^.*$`` or emptying a trust entry's ``required`` list is each a
breaking change. ``tests/test_schema_compatibility_gate.py`` holds the gate to each of these
by mutation.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from ._cli_support import USAGE_ERROR, UsageErrorParser
from .errors import LoquiturSchemasError
from .inventory import PUBLIC_SCHEMA_NAMES, load_schema_json

BASELINE_FILENAME = "public_canonical_v0_1_0.json"
BREAKING = "breaking"
REVIEW_REQUIRED = "review_required"

# Every keyword a consumer can rely on, upper bounds and `format` included: a schema that
# gains `maxLength: 1` on a bundle id or loses a `format` constraint changes what a producer
# may emit, in either direction.
_CONTRACT_KEYWORDS: tuple[str, ...] = (
    "type",
    "const",
    "enum",
    "format",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "pattern",
    "uniqueItems",
    "dependentRequired",
)


@dataclass(frozen=True)
class CompatibilityFinding:
    """Machine-readable schema compatibility finding."""

    severity: str
    schema_name: str
    path: str
    code: str
    message: str
    baseline: Any | None = None
    current: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity,
            "schema_name": self.schema_name,
            "path": self.path,
            "code": self.code,
            "message": self.message,
        }
        if self.baseline is not None:
            payload["baseline"] = self.baseline
        if self.current is not None:
            payload["current"] = self.current
        return payload


@dataclass(frozen=True)
class CompatibilityReport:
    """Structured compatibility report for stable public schemas."""

    ok: bool
    baseline_id: str
    baseline_package_version: str
    current_schema_count: int
    findings: tuple[CompatibilityFinding, ...]

    @property
    def breaking_findings(self) -> tuple[CompatibilityFinding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == BREAKING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "baseline_id": self.baseline_id,
            "baseline_package_version": self.baseline_package_version,
            "current_schema_count": self.current_schema_count,
            "finding_count": len(self.findings),
            "breaking_count": len(self.breaking_findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


class SchemaCompatibilityError(ValueError, LoquiturSchemasError):
    """Raised when the compatibility gate cannot evaluate inputs."""


def compatibility_baseline_root() -> Traversable:
    """Return package-data root containing compatibility baselines."""

    return resources.files("loquitur.schemas").joinpath("compatibility_baselines")


def load_bundled_compatibility_baseline(name: str = BASELINE_FILENAME) -> dict[str, Any]:
    """Load a bundled public-canonical schema compatibility baseline."""

    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise FileNotFoundError(f"unsafe compatibility baseline name: {name!r}")
    candidate = compatibility_baseline_root().joinpath(name)
    if not candidate.is_file():
        raise FileNotFoundError(f"compatibility baseline not bundled: {name}")
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):  # pragma: no cover - package corruption guard
        raise SchemaCompatibilityError(f"compatibility baseline is not a JSON object: {name}")
    return payload


def snapshot_public_canonical_contracts(
    schemas: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a deterministic contract snapshot for every public schema.

    All seven are covered, ``registry_entry`` and ``trust_registry`` included: they carry
    the signed wire and the issuer authorization, where a breaking change costs the most.
    """

    schema_map = dict(schemas) if schemas is not None else _load_bundled_schema_map()
    contracts: dict[str, Any] = {}
    for schema_name in PUBLIC_SCHEMA_NAMES:
        schema = schema_map.get(schema_name)
        if schema is None:
            raise SchemaCompatibilityError(f"stable public schema missing from snapshot input: {schema_name}")
        contracts[schema_name] = _schema_contract(schema_name, schema)
    return {
        "baseline_id": "public_canonical_v0_1_0",
        "package_name": "loquitur-schemas",
        "package_version": "0.1.0",
        # Per schema, because there is no single value: registry_entry and trust_registry
        # carry wire "v1" and the canonical five carry "v2". Read from the schemas rather
        # than restated beside them, so it cannot drift from them.
        "wire_schema_version": {
            schema_name: _declared_wire_schema_version(schema_name, schema_map[schema_name])
            for schema_name in PUBLIC_SCHEMA_NAMES
        },
        "scope": "every public protocol schema, canonical and registry",
        "schema_names": list(PUBLIC_SCHEMA_NAMES),
        "schemas": contracts,
    }


def check_schema_compatibility(
    current_schemas: Mapping[str, Mapping[str, Any]] | None = None,
    baseline: Mapping[str, Any] | None = None,
) -> CompatibilityReport:
    """Compare current public canonical schemas against a frozen baseline.

    Incompatible changes are reported as ``breaking`` findings. Additive optional
    fields are reported as ``review_required`` because strict consumers can still
    be affected if producers emit the field before consumer migration.
    """

    baseline_payload = dict(baseline) if baseline is not None else load_bundled_compatibility_baseline()
    current_snapshot = snapshot_public_canonical_contracts(current_schemas)

    baseline_schemas = baseline_payload.get("schemas")
    current_schema_contracts = current_snapshot.get("schemas")
    if not isinstance(baseline_schemas, dict) or not isinstance(current_schema_contracts, dict):
        raise SchemaCompatibilityError("compatibility baseline/current snapshot must contain a schemas object")

    findings: list[CompatibilityFinding] = []
    for schema_name in baseline_payload.get("schema_names", PUBLIC_SCHEMA_NAMES):
        if schema_name not in current_schema_contracts:
            findings.append(
                CompatibilityFinding(
                    severity=BREAKING,
                    schema_name=str(schema_name),
                    path="$",
                    code="schema_removed",
                    message="stable public schema was removed",
                    baseline=True,
                    current=False,
                )
            )
            continue
        baseline_contract = baseline_schemas.get(schema_name)
        current_contract = current_schema_contracts[schema_name]
        if not isinstance(baseline_contract, dict) or not isinstance(current_contract, dict):
            raise SchemaCompatibilityError(f"invalid schema contract in compatibility payload: {schema_name}")
        findings.extend(_compare_schema_contract(str(schema_name), baseline_contract, current_contract))

    breaking = tuple(finding for finding in findings if finding.severity == BREAKING)
    return CompatibilityReport(
        ok=not breaking,
        baseline_id=str(baseline_payload.get("baseline_id", "<unknown>")),
        baseline_package_version=str(baseline_payload.get("package_version", "<unknown>")),
        current_schema_count=len(current_schema_contracts),
        findings=tuple(findings),
    )


def load_schema_map_from_root(root: str | Path) -> dict[str, dict[str, Any]]:
    """Load public canonical schema JSON files from a filesystem root."""

    schema_root = Path(root)
    loaded: dict[str, dict[str, Any]] = {}
    for schema_name in PUBLIC_SCHEMA_NAMES:
        path = schema_root / schema_name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SchemaCompatibilityError(f"schema file not found: {path}") from exc
        except OSError as exc:
            raise SchemaCompatibilityError(f"cannot read schema file {path}: {exc.strerror}") from exc
        except UnicodeDecodeError as exc:
            raise SchemaCompatibilityError(f"schema file is not UTF-8: {path}") from exc
        except json.JSONDecodeError as exc:
            raise SchemaCompatibilityError(f"invalid JSON schema file {path}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise SchemaCompatibilityError(f"schema file is not a JSON object: {path}")
        loaded[schema_name] = value
    return loaded


def _load_bundled_schema_map() -> dict[str, dict[str, Any]]:
    return {schema_name: load_schema_json(schema_name) for schema_name in PUBLIC_SCHEMA_NAMES}


def _declared_wire_schema_version(schema_name: str, schema: Mapping[str, Any]) -> str:
    properties = schema.get("properties")
    declared = properties.get("schema_version") if isinstance(properties, dict) else None
    values = declared.get("enum") if isinstance(declared, dict) else None
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
        raise SchemaCompatibilityError(f"public schema does not pin a single wire schema_version: {schema_name}")
    return values[0]


def _schema_contract(schema_name: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise SchemaCompatibilityError(f"public schema has no properties object: {schema_name}")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise SchemaCompatibilityError(f"public schema has invalid required list: {schema_name}")
    return {
        "$id": schema.get("$id"),
        "type": schema.get("type"),
        "additionalProperties": schema.get("additionalProperties"),
        "required": sorted(required),
        "properties": {
            property_name: _property_contract(property_schema)
            for property_name, property_schema in sorted(properties.items())
            if isinstance(property_name, str)
        },
    }


def _property_contract(schema: Any) -> dict[str, Any]:
    """Reduce one property schema to the constraints a consumer can rely on.

    It descends into ``items``, a dict-valued ``additionalProperties``, ``properties``,
    ``required`` and ``oneOf``/``anyOf``/``allOf``, as ``validator.py``'s
    ``_assert_supported_schema`` does, because a property whose contract lives in a nested
    object (``registry_entry.signature``, a trust entry) would otherwise be recorded as
    ``{}``, and a change to it would go unseen.
    """

    if not isinstance(schema, dict):
        raise SchemaCompatibilityError("property schema must be a JSON object")
    payload: dict[str, Any] = {}
    for key in _CONTRACT_KEYWORDS:
        if key in schema:
            payload[key] = _normalize_json(schema[key])
    if "items" in schema:
        items = schema["items"]
        if isinstance(items, dict):
            payload["items"] = _property_contract(items)
        else:
            payload["items"] = _normalize_json(items)
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        payload["additionalProperties"] = _property_contract(additional)
    elif "additionalProperties" in schema:
        payload["additionalProperties"] = additional

    nested = schema.get("properties")
    if isinstance(nested, dict):
        payload["properties"] = {str(name): _property_contract(nested[name]) for name in sorted(nested)}
    if "required" in schema:
        required = schema["required"]
        # Sorted, because a consumer relies on the SET of mandatory fields; reordering the
        # list in the source must not read as a contract change.
        payload["required"] = (
            sorted(str(item) for item in required) if isinstance(required, list) else _normalize_json(required)
        )
    for branch_key in ("oneOf", "anyOf", "allOf"):
        branches = schema.get(branch_key)
        if isinstance(branches, list):
            payload[branch_key] = [
                _property_contract(branch) if isinstance(branch, dict) else _normalize_json(branch)
                for branch in branches
            ]
    return payload


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    return value


def _compare_schema_contract(
    schema_name: str,
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
) -> list[CompatibilityFinding]:
    findings: list[CompatibilityFinding] = []
    for key in ("type", "additionalProperties"):
        if baseline.get(key) != current.get(key):
            findings.append(
                CompatibilityFinding(
                    severity=BREAKING,
                    schema_name=schema_name,
                    path=f"$.{key}",
                    code=f"top_level_{key}_changed",
                    message=f"top-level {key} changed for stable public schema",
                    baseline=baseline.get(key),
                    current=current.get(key),
                )
            )

    baseline_required = set(_as_string_list(baseline.get("required"), f"{schema_name}.required"))
    current_required = set(_as_string_list(current.get("required"), f"{schema_name}.required"))
    for field in sorted(baseline_required - current_required):
        findings.append(
            CompatibilityFinding(
                severity=BREAKING,
                schema_name=schema_name,
                path="$.required",
                code="required_field_removed",
                message=f"required field was removed: {field}",
                baseline=field,
                current=None,
            )
        )
    for field in sorted(current_required - baseline_required):
        findings.append(
            CompatibilityFinding(
                severity=BREAKING,
                schema_name=schema_name,
                path="$.required",
                code="required_field_added",
                message=f"new required field was added: {field}",
                baseline=None,
                current=field,
            )
        )

    baseline_properties = _as_mapping(baseline.get("properties"), f"{schema_name}.properties")
    current_properties = _as_mapping(current.get("properties"), f"{schema_name}.properties")
    for field in sorted(set(baseline_properties) - set(current_properties)):
        findings.append(
            CompatibilityFinding(
                severity=BREAKING,
                schema_name=schema_name,
                path=f"$.properties.{field}",
                code="property_removed",
                message=f"public property was removed: {field}",
                baseline=baseline_properties[field],
                current=None,
            )
        )
    for field in sorted(set(current_properties) - set(baseline_properties)):
        severity = BREAKING if field in current_required else REVIEW_REQUIRED
        findings.append(
            CompatibilityFinding(
                severity=severity,
                schema_name=schema_name,
                path=f"$.properties.{field}",
                code="property_added",
                message=f"public property was added: {field}",
                baseline=None,
                current=current_properties[field],
            )
        )
    for field in sorted(set(baseline_properties) & set(current_properties)):
        if baseline_properties[field] != current_properties[field]:
            findings.append(
                CompatibilityFinding(
                    severity=BREAKING,
                    schema_name=schema_name,
                    path=f"$.properties.{field}",
                    code="property_contract_changed",
                    message=f"public property contract changed: {field}",
                    baseline=baseline_properties[field],
                    current=current_properties[field],
                )
            )
    return findings


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SchemaCompatibilityError(f"expected object for {label}")
    return value


def _as_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaCompatibilityError(f"expected string list for {label}")
    return value


def _load_baseline_from_path(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchemaCompatibilityError(f"baseline file not found: {path}") from exc
    except OSError as exc:
        raise SchemaCompatibilityError(f"cannot read baseline file {path}: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise SchemaCompatibilityError(f"baseline file is not UTF-8: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaCompatibilityError(f"invalid baseline JSON {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise SchemaCompatibilityError(f"baseline file is not a JSON object: {path}")
    return value


def _require_changelog(path: str | None) -> None:
    if path is None:
        raise SchemaCompatibilityError("--allow-breaking requires --changelog with a non-empty changelog entry")
    changelog = Path(path)
    try:
        text = changelog.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SchemaCompatibilityError(f"changelog file not found: {changelog}") from exc
    except OSError as exc:
        raise SchemaCompatibilityError(f"cannot read changelog file {changelog}: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise SchemaCompatibilityError(f"changelog file is not UTF-8: {changelog}") from exc
    if not text.strip():
        raise SchemaCompatibilityError(f"changelog file is empty: {changelog}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = UsageErrorParser(
        prog="python -m loquitur.schemas.compatibility",
        description="Check stable Loquitur public schemas against the bundled compatibility baseline.",
    )
    parser.add_argument(
        "--current-schema-root",
        help=(
            "filesystem directory containing current public canonical *.schema.json files; defaults to bundled schemas"
        ),
    )
    parser.add_argument(
        "--baseline",
        help="compatibility baseline JSON path; defaults to bundled public_canonical_v0_1_0.json",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable report JSON")
    parser.add_argument(
        "--allow-breaking",
        action="store_true",
        help="return success for breaking changes only when a changelog entry is supplied",
    )
    parser.add_argument(
        "--changelog",
        help="non-empty changelog file required when --allow-breaking is used",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        baseline = _load_baseline_from_path(args.baseline)
        current = load_schema_map_from_root(args.current_schema_root) if args.current_schema_root else None
        report = check_schema_compatibility(current_schemas=current, baseline=baseline)
        if report.breaking_findings and args.allow_breaking:
            _require_changelog(args.changelog)
    except (FileNotFoundError, SchemaCompatibilityError) as exc:
        print(str(exc), file=sys.stderr)
        return USAGE_ERROR

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif report.ok:
        print(f"schema compatibility ok: {report.baseline_id}")
        for finding in report.findings:
            print(f"- {finding.severity}: {finding.schema_name}: {finding.code}: {finding.message}")
    else:
        print(f"schema compatibility failed: {report.baseline_id}")
        for finding in report.findings:
            print(f"- {finding.severity}: {finding.schema_name}: {finding.code}: {finding.message}")

    if report.ok or (report.breaking_findings and args.allow_breaking):
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
