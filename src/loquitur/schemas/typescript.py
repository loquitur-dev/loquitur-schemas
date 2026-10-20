"""TypeScript declarations generated from the bundled schemas, the same bytes on every run."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from ._cli_support import USAGE_ERROR, UsageErrorParser
from .errors import LoquiturSchemasError
from .inventory import (
    PUBLIC_CANONICAL_SCHEMA_NAMES,
    PUBLIC_REGISTRY_SCHEMA_NAMES,
    PUBLIC_SCHEMA_NAMES,
    load_schema_json,
    load_schema_text,
)
from .verification_vocabulary import REGISTRY_VERDICTS, VERIFICATION_STATUSES

GENERATED_DECLARATION_FILENAME = "loquitur-protocol.d.ts"
GENERATED_DECLARATION_MANIFEST_FILENAME = "loquitur-protocol.manifest.json"
GENERATOR_ID = "loquitur.schemas.typescript.v2"

_SCHEMA_TO_INTERFACE_NAME: dict[str, str] = {
    "change_summary.schema.json": "ChangeSummary",
    "coverage_summary.schema.json": "CoverageSummary",
    "lineage_summary.schema.json": "LineageSummary",
    "verification_receipt.schema.json": "VerificationReceipt",
    "verification_summary.schema.json": "VerificationSummary",
    "registry_entry.schema.json": "RegistryEntry",
    "trust_registry.schema.json": "TrustRegistry",
}


class TypeScriptGenerationError(ValueError, LoquiturSchemasError):
    """Raised when a bundled schema cannot be mapped to TypeScript safely."""


def typescript_data_root() -> Traversable:
    """Return the package-data directory that holds the shipped declarations and their manifest."""

    return resources.files("loquitur.schemas").joinpath("types")


def load_typescript_declarations(name: str = GENERATED_DECLARATION_FILENAME) -> str:
    """Return the text of the shipped declaration file ``name``.

    Raises:
        FileNotFoundError: If ``name`` is not a plain file name or no such file is shipped.
    """
    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise FileNotFoundError(f"unsafe TypeScript declaration name: {name!r}")
    candidate = typescript_data_root().joinpath(name)
    if not candidate.is_file():
        raise FileNotFoundError(f"TypeScript declaration not bundled: {name}")
    return candidate.read_text(encoding="utf-8")


def load_typescript_declaration_manifest(
    name: str = GENERATED_DECLARATION_MANIFEST_FILENAME,
) -> dict[str, Any]:
    """Return the shipped declaration manifest ``name`` as a JSON object.

    Raises:
        FileNotFoundError: If ``name`` is not a plain file name or no such file is shipped.
        TypeScriptGenerationError: If the manifest is not a JSON object.
    """
    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise FileNotFoundError(f"unsafe TypeScript manifest name: {name!r}")
    candidate = typescript_data_root().joinpath(name)
    if not candidate.is_file():
        raise FileNotFoundError(f"TypeScript declaration manifest not bundled: {name}")
    value = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeScriptGenerationError("TypeScript declaration manifest must be an object")
    return value


def generate_typescript_declarations() -> str:
    """Return the TypeScript declarations of every bundled public schema.

    Raises:
        TypeScriptGenerationError: If a bundled schema uses a construct the generator does not map.
    """
    lines: list[str] = [
        "// Generated from loquitur-schemas bundled JSON Schemas.",
        "// Do not hand-edit. Regenerate from loquitur.schemas.typescript.",
        "// Contract: protocol 0.1 closed canonical objects and verification vocabularies.",
        "",
        "export type LoquiturJsonObject = Record<string, unknown>;",
        f"export type VerificationStatus = {_literal_union(VERIFICATION_STATUSES)};",
        f"export type RegistryVerdict = {_literal_union(REGISTRY_VERDICTS)};",
        "",
    ]

    # Every public schema, registry_entry and trust_registry included: they carry the
    # signed wire and the issuer authorization, and registry_entry is the schema whose
    # `verdict` uses RegistryVerdict.
    for schema_name in PUBLIC_SCHEMA_NAMES:
        lines.extend(_render_interface(_interface_name_for_schema(schema_name), load_schema_json(schema_name)))
        lines.append("")

    # Two unions, not one: a registry entry is a public commitment surface, not a canonical
    # object, and merging them would make LoquiturCanonicalObject a name that lies about
    # half its members.
    lines.extend(_render_union("LoquiturCanonicalObject", PUBLIC_CANONICAL_SCHEMA_NAMES))
    lines.extend(_render_union("LoquiturRegistryObject", PUBLIC_REGISTRY_SCHEMA_NAMES))
    return "\n".join(lines)


def generate_typescript_declaration_manifest() -> dict[str, Any]:
    """Return the manifest that pins the generated declarations and the schemas they come from."""
    declarations = generate_typescript_declarations().encode("utf-8")
    # Both digest maps are keyed by filename, registry schemas exactly as canonical ones,
    # so the manifest pins every schema it declares, trust_registry included.
    return {
        "schema_version": "loquitur.typescript_declaration_manifest.v1",
        "generator_id": GENERATOR_ID,
        "output_path": GENERATED_DECLARATION_FILENAME,
        "output_sha256": hashlib.sha256(declarations).hexdigest(),
        "canonical_schema_sha256": _schema_digests(PUBLIC_CANONICAL_SCHEMA_NAMES),
        "registry_schema_sha256": _schema_digests(PUBLIC_REGISTRY_SCHEMA_NAMES),
        "verification_statuses": list(VERIFICATION_STATUSES),
        "registry_verdicts": list(REGISTRY_VERDICTS),
        "canonical_interface_count": len(PUBLIC_CANONICAL_SCHEMA_NAMES),
        "registry_interface_count": len(PUBLIC_REGISTRY_SCHEMA_NAMES),
    }


def _schema_digests(schema_names: Sequence[str]) -> dict[str, str]:
    return {name: hashlib.sha256(load_schema_text(name).encode("utf-8")).hexdigest() for name in schema_names}


def _render_union(union_name: str, schema_names: Sequence[str]) -> list[str]:
    lines = [f"export type {union_name} ="]
    for index, schema_name in enumerate(schema_names):
        prefix = "  | " if index else "    "
        lines.append(f"{prefix}{_interface_name_for_schema(schema_name)}")
    lines[-1] = f"{lines[-1]};"
    lines.append("")
    return lines


def write_typescript_declarations(
    output_path: str | Path,
    *,
    manifest_output_path: str | Path | None = None,
) -> Path:
    """Write the declarations to ``output_path``, and the manifest when a path is given.

    Returns:
        The path the declarations were written to.

    Raises:
        OSError: If a file cannot be written.
    """
    # Written with an explicit LF newline, never the platform default. `write_text`
    # translates "\n" to "\r\n" on Windows, and the manifest's output_sha256 is computed
    # over the LF form, so a CRLF file would not match its own manifest. A hash-locked
    # generated artifact must be byte-identical on every platform.
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generate_typescript_declarations(), encoding="utf-8", newline="\n")
    if manifest_output_path is not None:
        manifest_target = Path(manifest_output_path)
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        manifest_target.write_text(
            json.dumps(generate_typescript_declaration_manifest(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return target


def _interface_name_for_schema(schema_name: str) -> str:
    try:
        return _SCHEMA_TO_INTERFACE_NAME[schema_name]
    except KeyError as exc:
        raise TypeScriptGenerationError(f"no TypeScript interface name configured for {schema_name}") from exc


def _render_interface(interface_name: str, schema: Mapping[str, Any]) -> list[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise TypeScriptGenerationError(f"schema for {interface_name} has no object properties")
    required = schema.get("required", [])
    if not isinstance(required, list):
        raise TypeScriptGenerationError(f"schema for {interface_name} has invalid required list")
    required_set = {str(item) for item in required}
    lines = [f"export interface {interface_name} {{"]
    for property_name in sorted(properties):
        property_schema = properties[property_name]
        if not isinstance(property_schema, dict):
            raise TypeScriptGenerationError(
                f"property {property_name!r} in {interface_name} is not a JSON Schema object"
            )
        optional = "" if property_name in required_set else "?"
        if property_name == "status" and interface_name in {"VerificationReceipt", "VerificationSummary"}:
            rendered = "VerificationStatus"
        elif property_name == "verdict" and interface_name == "RegistryEntry":
            # Byte-identical to REGISTRY_VERDICTS, so naming the alias here narrows nothing
            # and ties the field to the exported RegistryVerdict type.
            rendered = "RegistryVerdict"
        else:
            rendered = _schema_to_typescript(property_schema)
        lines.append(f"  {_quote_property_name(property_name)}{optional}: {rendered};")
    lines.append("}")
    return lines


def _schema_to_typescript(schema: Mapping[str, Any]) -> str:
    if "const" in schema:
        return _literal_to_typescript(schema["const"])
    if "enum" in schema:
        enum_values = schema["enum"]
        if not isinstance(enum_values, list):
            raise TypeScriptGenerationError("enum must be a list")
        return _dedupe_union(_literal_to_typescript(value) for value in enum_values)
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return _dedupe_union(_single_type_to_typescript(item, schema) for item in schema_type)
    if isinstance(schema_type, str):
        return _single_type_to_typescript(schema_type, schema)
    return "unknown"


def _single_type_to_typescript(schema_type: str, schema: Mapping[str, Any]) -> str:
    if schema_type == "null":
        return "null"
    if schema_type == "boolean":
        return "boolean"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "string":
        return "string"
    if schema_type == "array":
        items = schema.get("items")
        item_type = _schema_to_typescript(items) if isinstance(items, dict) else "unknown"
        if " | " in item_type:
            item_type = f"({item_type})"
        return f"{item_type}[]"
    if schema_type == "object":
        return "LoquiturJsonObject"
    raise TypeScriptGenerationError(f"unsupported JSON Schema type for TypeScript generation: {schema_type}")


def _literal_to_typescript(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeScriptGenerationError(f"unsupported enum/const literal: {value!r}")


def _literal_union(values: Sequence[str]) -> str:
    return " | ".join(json.dumps(value, ensure_ascii=False) for value in values)


def _dedupe_union(parts: Any) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part not in seen:
            seen.add(part)
            result.append(part)
    return " | ".join(result) if result else "never"


def _quote_property_name(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
        return name
    return json.dumps(name)


def main(argv: Sequence[str] | None = None) -> int:
    parser = UsageErrorParser(
        prog="python -m loquitur.schemas.typescript",
        description="Generate TypeScript declarations from bundled Loquitur public schemas.",
    )
    parser.add_argument("--output", "-o", default="-", help="output .d.ts path; use '-' for stdout")
    parser.add_argument("--manifest-output", default=None, help="optional generated declaration manifest path")
    args = parser.parse_args(list(argv) if argv is not None else None)
    declarations = generate_typescript_declarations()
    if args.output == "-":
        if args.manifest_output is not None:
            parser.error("--manifest-output requires a file --output")
        # Bytes, not text: a text-mode stdout writes each LF as CRLF on Windows, and the
        # declarations are bound by digest, so stdout must carry the same bytes as --output.
        # A stdout with no byte buffer (a StringIO, say) takes the text, whose newlines are
        # already LF, and without any stdout there is nothing to write to, as for print.
        stdout = sys.stdout
        if stdout is None:
            return 0
        buffer = getattr(stdout, "buffer", None)
        if buffer is None:
            stdout.write(declarations)
            stdout.flush()
            return 0
        stdout.flush()
        buffer.write(declarations.encode("utf-8"))
        buffer.flush()
        return 0
    try:
        write_typescript_declarations(args.output, manifest_output_path=args.manifest_output)
    except OSError as exc:
        print(f"cannot write {exc.filename or args.output}: {exc.strerror}", file=sys.stderr)
        return USAGE_ERROR
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
