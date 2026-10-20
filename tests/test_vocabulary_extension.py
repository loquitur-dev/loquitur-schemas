"""A value registered after this package was built needs no change to any schema it bundles.

verification-vocabularies.md §9: registering a value is a new minor version of one vocabulary
document, and changes no schema. A copy of each bundled vocabulary gains a value in a temporary
directory; documents carrying it validate against the unchanged bundled schemas, whose bytes are
the same before and after; the value is unknown against the bundled vocabulary and known against
the extended one. The loader refuses what §6 refuses, and agrees with the meta-schema it mirrors.
"""

from __future__ import annotations

import copy
import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from loquitur.schemas import (
    RegisteredVocabularyError,
    load_registered_vocabulary,
    load_schema_json,
    validate_instance,
    value_status,
)

ADDED = {"asset_type": "example_asset", "workflow": "example_asset_initial", "anchoring_method": "example_method"}


def _data_digests() -> dict[str, str]:
    root = resources.files("loquitur.schemas").joinpath("data")
    return {
        entry.name: hashlib.sha256(entry.read_bytes()).hexdigest()
        for entry in root.iterdir()
        if entry.name.endswith(".schema.json")
    }


def _meta_schema() -> dict[str, Any]:
    data = resources.files("loquitur.schemas").joinpath("data", "registered_vocabularies", "schema.json")
    return json.loads(data.read_bytes().decode("utf-8"))


def _extended(kind: str) -> dict[str, Any]:
    document = copy.deepcopy(load_registered_vocabulary(kind))
    document["version"] = "1.1.0"
    value = {"since": "1.1.0", "status": "active", "title": "Example", "profile": None}
    if kind == "workflow":
        value["asset_types"] = ["example_asset"]
    document["values"][ADDED[kind]] = value
    return document


def _write(tmp_path: Path, name: str, document: Any) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def test_a_registered_value_needs_no_schema_change(tmp_path: Path) -> None:
    before = _data_digests()
    held = {}
    for kind in ADDED:
        path = _write(tmp_path, f"{kind}.json", _extended(kind))
        held[kind] = load_registered_vocabulary(kind, path)
        assert value_status(ADDED[kind], load_registered_vocabulary(kind)) == "unknown"
        assert value_status(ADDED[kind], held[kind]) == "known"

    entry = copy.deepcopy(load_schema_json("registry_entry.schema.json")["example"])
    entry["asset_type"], entry["workflow"] = ADDED["asset_type"], ADDED["workflow"]
    entry["anchor"] = {"method": ADDED["anchoring_method"], "system": "example:1", "anchor_reference": "ref"}
    assert validate_instance("registry_entry", entry).ok
    receipt = copy.deepcopy(load_schema_json("verification_receipt.schema.json")["example"])
    receipt["asset_type"] = ADDED["asset_type"]
    assert validate_instance("verification_receipt", receipt).ok
    registry = copy.deepcopy(load_schema_json("trust_registry.schema.json")["example"])
    for trust_entry in registry["entries"]:
        trust_entry["allowed_asset_types"] = [ADDED["asset_type"]]
        trust_entry["allowed_workflows"] = [ADDED["workflow"]]
    assert validate_instance("trust_registry", registry).ok
    assert _data_digests() == before


@pytest.mark.parametrize("value", [7, None, "", "Fund_NAV", "fund-nav", " ", "a" * 65, "_fund"])
def test_a_value_that_is_not_an_identifier_is_invalid(value: object) -> None:
    assert value_status(value, load_registered_vocabulary("asset_type")) == "invalid"


def test_a_deprecated_value_is_known(tmp_path: Path) -> None:
    document = copy.deepcopy(load_registered_vocabulary("asset_type"))
    document["version"] = "1.1.0"
    document["values"]["property"]["status"] = "deprecated"
    held = load_registered_vocabulary("asset_type", _write(tmp_path, "asset_type.json", document))
    assert value_status("property", held) == "known"


def _refused_documents() -> list[tuple[str, str, Any]]:
    base = load_registered_vocabulary("workflow")
    cases: list[tuple[str, str, Any]] = [("not_an_object", "workflow", [base])]

    def changed(name: str, change: Any, kind: str = "workflow") -> None:
        document = copy.deepcopy(base)
        change(document)
        cases.append((name, kind, document))

    changed("kind_mismatch", lambda d: None, "asset_type")
    changed("schema_version_v2", lambda d: d.update(schema_version="v2"))
    changed("version_malformed", lambda d: d.update(version="1.0"))
    changed("version_suffix", lambda d: d.update(version="1.0.0-rc1"))
    changed("unknown_member", lambda d: d.update(extra=True))
    changed("values_empty", lambda d: d.update(values={}))
    changed("value_malformed", lambda d: d["values"].update({"Fund-NAV": d["values"]["fund_nav_update"]}))
    changed("since_after_version", lambda d: d["values"]["fund_nav_update"].update(since="1.1.0"))
    changed("status_unknown", lambda d: d["values"]["fund_nav_update"].update(status="retired"))
    changed("title_blank", lambda d: d["values"]["fund_nav_update"].update(title="\u3000"))
    changed("profile_empty", lambda d: d["values"]["fund_nav_update"].update(profile=""))
    changed("workflow_without_asset_types", lambda d: d["values"]["fund_nav_update"].pop("asset_types"))
    changed("asset_types_empty", lambda d: d["values"]["fund_nav_update"].update(asset_types=[]))
    changed("value_extra_member", lambda d: d["values"]["fund_nav_update"].update(note="x"))
    return cases


@pytest.mark.parametrize(("name", "kind", "document"), _refused_documents(), ids=lambda case: str(case))
def test_the_loader_refuses_what_section_6_refuses(tmp_path: Path, name: str, kind: str, document: Any) -> None:
    with pytest.raises(RegisteredVocabularyError):
        load_registered_vocabulary(kind, _write(tmp_path, f"{name}.json", document))


def test_a_duplicate_value_is_not_strict_json(tmp_path: Path) -> None:
    value = '{"since": "1.0.0", "status": "active", "title": "Real property", "profile": null}'
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"object_type": "registered_vocabulary", "schema_version": "v1", "kind": "asset_type", '
        f'"version": "1.0.0", "values": {{"property": {value}, "property": {value}}}}}',
        encoding="utf-8",
    )
    with pytest.raises(RegisteredVocabularyError):
        load_registered_vocabulary("asset_type", path)


@pytest.mark.parametrize(("name", "kind", "document"), _refused_documents(), ids=lambda case: str(case))
def test_the_loader_agrees_with_the_meta_schema_on_each_document(name: str, kind: str, document: Any) -> None:
    """A document the meta-schema refuses is refused; the rest break a rule of §6 it cannot state."""
    meta_errors = list(jsonschema.Draft202012Validator(_meta_schema()).iter_errors(document))
    prose = {"kind_mismatch", "since_after_version", "title_blank", "workflow_without_asset_types"}
    assert bool(meta_errors) == (name not in prose), (name, [error.message for error in meta_errors])
