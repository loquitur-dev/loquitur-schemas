"""Gate: every bundled schema's embedded ``example`` must validate against itself.

The bundled schemas carry an OpenAPI-style ``example`` keyword, which JSON Schema
validators (including this package's subset validator) treat as inert documentation
rather than a validated value, so an embedded example could drift out of conformance
with its own schema (for example a ``reason_codes`` entry that is not in the enum) and ship
as a broken copy-paste source for integrators.

This test makes the embedded examples a validated invariant. Any schema that
declares an ``object_type`` const and carries an ``example`` (or ``examples``)
must have that example pass ``validate_instance`` against the schema, so an edit
that breaks an example fails before publication instead of after.
"""

from __future__ import annotations

from typing import Any

import pytest

from loquitur.schemas.inventory import PUBLIC_SCHEMA_NAMES, load_schema_json
from loquitur.schemas.validator import validate_instance


def _examples_for(schema: dict[str, Any]) -> list[Any]:
    found: list[Any] = []
    if "example" in schema:
        found.append(schema["example"])
    examples = schema.get("examples")
    if isinstance(examples, list):
        found.extend(examples)
    return found


def _object_type_const(schema: dict[str, Any]) -> str | None:
    props = schema.get("properties", {})
    object_type = props.get("object_type", {}) if isinstance(props, dict) else {}
    const = object_type.get("const") if isinstance(object_type, dict) else None
    return const if isinstance(const, str) else None


@pytest.mark.parametrize("schema_name", PUBLIC_SCHEMA_NAMES)
def test_bundled_schema_example_validates_against_itself(schema_name: str) -> None:
    schema = load_schema_json(schema_name)
    object_type = _object_type_const(schema)
    examples = _examples_for(schema)

    if object_type is None or not examples:
        pytest.skip(f"{schema_name}: no object_type const or no embedded example to validate")

    for index, example in enumerate(examples):
        result = validate_instance(object_type, example)
        assert result.ok, (
            f"{schema_name}: embedded example[{index}] does not validate against its own schema: "
            + "; ".join(f"{e.path}:{e.code}:{e.message}" for e in result.errors)
        )


def test_at_least_one_schema_example_is_covered() -> None:
    """Guard against the parametrization silently degenerating to all-skips."""
    covered = 0
    for schema_name in PUBLIC_SCHEMA_NAMES:
        schema = load_schema_json(schema_name)
        if _object_type_const(schema) is not None and _examples_for(schema):
            covered += 1
    assert covered >= 5, f"expected embedded examples on the canonical objects, only {covered} covered"
