"""The ``loquitur-schema-validate`` command: list the bundled schemas and validate documents."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from ._cli_support import USAGE_ERROR, UsageErrorParser
from .inventory import SchemaNotFoundError, list_schema_names
from .validator import SchemaValidationUsageError, validate_file

VALIDATION_FAILED = 1

# Printed after a schema name or object_type that resolves to no bundled schema.
UNKNOWN_SCHEMA_HINT = (
    "accepted: a name printed by 'loquitur-schema-validate list', with or without its '.schema.json' suffix"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = UsageErrorParser(
        prog="loquitur-schema-validate",
        description="Validate JSON documents against bundled Loquitur public schemas.",
    )
    parser.add_argument("--version", action="store_true", help="print package version and exit")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list", help="list bundled schema filenames")

    validate = subparsers.add_parser(
        "validate",
        help="validate one JSON document against a bundled schema or canonical object_type",
    )
    validate.add_argument(
        "schema_or_object_type",
        help="bundled schema filename (verification_summary.schema.json) or object_type (verification_summary)",
    )
    validate.add_argument("json_path", help="path of the JSON document to validate")
    validate.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable validation result as JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.version:
        print(f"loquitur-schemas {__version__}")
        return 0

    if args.command == "list":
        for name in list_schema_names():
            print(name)
        return 0

    if args.command == "validate":
        try:
            result = validate_file(args.schema_or_object_type, args.json_path)
        except SchemaNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            print(UNKNOWN_SCHEMA_HINT, file=sys.stderr)
            return USAGE_ERROR
        except SchemaValidationUsageError as exc:
            print(str(exc), file=sys.stderr)
            return USAGE_ERROR
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        elif result.ok:
            print(f"schema validation ok: {result.schema_name}")
        else:
            print(f"schema validation failed: {result.schema_name}")
            for error in result.errors:
                print(f"- {error.path}: {error.code}: {error.message}")
        return 0 if result.ok else VALIDATION_FAILED

    # No subcommand is a usage error like any other: the help goes to stderr and the exit
    # status is the one README.md documents for usage errors.
    parser.print_help(sys.stderr)
    return USAGE_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
