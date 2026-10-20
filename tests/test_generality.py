"""The bundled schemas hold no domain value, as the protocol's do.

loquitur-protocol tests/test_generality.py holds this of the protocol's schemas; this module
holds it of the copies this package ships, which are byte for byte the same files, so that a
mirror that drifted back to an enumeration fails here too (verification-vocabularies.md §5 and
§7).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from loquitur.schemas import PUBLIC_SCHEMA_NAMES, load_registered_vocabulary, load_schema_json

IDENT = "^[a-z0-9][a-z0-9_]{0,63}$"
GOVERNED = {
    ("registry_entry.schema.json", "/properties/asset_type"),
    ("registry_entry.schema.json", "/properties/workflow"),
    ("registry_entry.schema.json", "/properties/anchor/properties/method"),
    ("trust_registry.schema.json", "/properties/entries/items/properties/allowed_asset_types/items"),
    ("trust_registry.schema.json", "/properties/entries/items/properties/allowed_workflows/items"),
    ("verification_receipt.schema.json", "/properties/asset_type"),
    ("verification_summary.schema.json", "/properties/asset_type"),
    ("coverage_summary.schema.json", "/properties/asset_type"),
    ("change_summary.schema.json", "/properties/asset_type"),
    ("lineage_summary.schema.json", "/properties/asset_type"),
}
CHAIN_NAMES = {"algorand", "ethereum", "polygon", "hedera", "bitcoin", "solana", "tezos", "avalanche"}


def resolve(document: Any, pointer: str) -> Any:
    for token in pointer.split("/")[1:]:
        document = document[token]
    return document


def strings(node: Any) -> Iterator[str]:
    """Every key and string value of ``node`` outside `example` and `description`."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("example", "description"):
                continue
            yield key
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)
    elif isinstance(node, str):
        yield node


@pytest.mark.parametrize(("name", "pointer"), sorted(GOVERNED))
def test_governed_pointers_are_identifiers(name: str, pointer: str) -> None:
    node = resolve(load_schema_json(name), pointer)
    assert node["pattern"] == IDENT
    assert not {"enum", "const"} & set(node)


def test_the_registry_entry_lists_no_anchoring_system() -> None:
    schema = load_schema_json("registry_entry.schema.json")
    assert set(schema["properties"]["anchor"]["properties"]) == {"method", "system", "anchor_reference"}
    forbidden = CHAIN_NAMES | set(load_registered_vocabulary("anchoring_method")["values"]) | {"chain"}
    assert not forbidden & set(strings(schema))


def test_no_registered_asset_type_or_workflow_appears_in_a_bundled_schema() -> None:
    values = set(load_registered_vocabulary("asset_type")["values"]) | set(
        load_registered_vocabulary("workflow")["values"]
    )
    for name in PUBLIC_SCHEMA_NAMES:
        found = values & set(strings(load_schema_json(name)))
        assert not found, (name, sorted(found))


def test_the_bundled_vocabularies_are_the_protocol_documents_of_this_release() -> None:
    for kind in ("asset_type", "workflow", "anchoring_method"):
        document = load_registered_vocabulary(kind)
        assert document["kind"] == kind and document["version"] == "1.0.0"
        assert json.loads(json.dumps(document)) == document
