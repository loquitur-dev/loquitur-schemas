from __future__ import annotations

import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from loquitur.schemas.cli import main
from loquitur.schemas.inventory import (
    SchemaNotFoundError,
    load_schema_json,
    load_schema_text,
    schema_data_root,
)


def test_package_import_and_metadata() -> None:
    import loquitur.schemas as schemas

    assert schemas.__version__ == "0.1.0"
    assert schema_data_root().joinpath("README.md").is_file()


def test_the_package_version_is_the_same_in_pyproject_module_and_readme() -> None:
    import loquitur.schemas as schemas

    root = Path(__file__).resolve().parents[1]
    declared = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    readme = (root / "README.md").read_text(encoding="utf-8")
    printed = re.findall(r"^It prints `loquitur-schemas (\S+)`\.$", readme, flags=re.MULTILINE)
    assert [declared] == [schemas.__version__] == printed


def test_load_schema_returns_text_and_json() -> None:
    text = load_schema_text("verification_summary.schema.json")
    assert "verification_summary" in text
    schema = load_schema_json("verification_summary.schema.json")
    assert schema["properties"]["object_type"]["const"] == "verification_summary"


def test_load_schema_rejects_missing_and_unsafe_names() -> None:
    for name in ["../x.schema.json", "nested/x.schema.json", ""]:
        try:
            load_schema_text(name)
        except SchemaNotFoundError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"expected SchemaNotFoundError for {name!r}")


def test_cli_help_version_and_list(capsys) -> None:
    assert main(["--version"]) == 0
    assert "loquitur-schemas 0.1.0" in capsys.readouterr().out

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "verification_summary.schema.json" in out
    assert "registry_entry.schema.json" in out

    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "loquitur-schema-validate" in capsys.readouterr().out


def test_cli_validate_missing_file_exits_usage_error(capsys) -> None:
    assert main(["validate", "verification_summary.schema.json", "sample.json"]) == 64
    assert "JSON document not found" in capsys.readouterr().err


# The import boundary is an allow-list. Importing loquitur.schemas may load a module of the
# standard library, a module of the loquitur namespace, or a module of a distribution in the
# runtime dependency closure: the distributions pyproject.toml declares under `dependencies`,
# followed through the metadata of what is installed. Everything else is refused, whatever it is
# called, so this file names nothing it refuses, and a package that does not exist yet is refused
# by the same rule as one that does. A module an extension creates in memory, with no file, no
# spec and no search path, belongs to the extension that made it and is admitted with it.
REPO = Path(__file__).resolve().parents[1]

_REQUIREMENT_NAME = re.compile(r"\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")

PROBE = """
import json, sys
allowed = set(json.loads(sys.argv[1]))
before = set(sys.modules)
{statement}
def admitted(name):
    top = name.partition(".")[0]
    if top in sys.stdlib_module_names or top == "loquitur" or top in allowed:
        return True
    module = sys.modules.get(name)
    return (
        getattr(module, "__spec__", None) is None
        and getattr(module, "__file__", None) is None
        and not hasattr(module, "__path__")
    )
print(json.dumps(sorted(name for name in set(sys.modules) - before if not admitted(name))))
"""


def _distribution_name(requirement: str) -> str:
    match = _REQUIREMENT_NAME.match(requirement)
    assert match is not None, requirement
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def runtime_dependency_closure() -> set[str]:
    """The runtime distributions pyproject.toml declares, and the ones they require, as installed."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    queue = [_distribution_name(text) for text in project.get("dependencies", ())]
    closure: set[str] = set()
    while queue:
        name = queue.pop()
        if name in closure:
            continue
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        closure.add(name)
        queue.extend(
            _distribution_name(text) for text in distribution.requires or () if "extra" not in text.partition(";")[2]
        )
    return closure


def allowed_top_level_modules() -> list[str]:
    closure = runtime_dependency_closure()
    return sorted(
        module
        for module, distributions in importlib.metadata.packages_distributions().items()
        if any(_distribution_name(name) in closure for name in distributions)
    )


def modules_refused_at(statement: str, extra_path: Path | None = None) -> list[str]:
    """The modules that ``statement`` loads in a fresh interpreter and the allow-list refuses.

    A before/after diff of sys.modules inside this process could not fail: this file's own
    top-level ``from loquitur.schemas.cli import main`` has already imported the package. A
    fresh interpreter is the only honest way to ask what importing the package loads, and it
    inherits this session's import path, so a module is findable there exactly when it is here:
    a path entry only makes a module findable, and the probe reports only what is loaded.
    """
    env = dict(os.environ)
    path = [os.fspath(extra_path)] if extra_path is not None else []
    env["PYTHONPATH"] = os.pathsep.join(path + [p for p in sys.path if p])
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(statement=statement), json.dumps(allowed_top_level_modules())],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={**env, "PYTHONIOENCODING": "utf-8"},
    )
    assert "No module named 'loquitur'" not in result.stderr, (
        "the probe could not import loquitur.schemas at all, so this gate measured nothing. "
        "That is an environment fault, not a boundary violation: install the package or "
        f"check sys.path.\n{result.stderr}"
    )
    assert result.returncode == 0, f"probe failed: {result.stderr}"
    loaded: list[str] = json.loads(result.stdout)
    return loaded


def test_the_runtime_closure_is_read_from_pyproject() -> None:
    closure = runtime_dependency_closure()
    assert {"cryptography", "rfc8785"} <= closure
    assert "pytest" not in closure


def test_package_import_loads_only_its_runtime_closure() -> None:
    """The protocol-only import boundary, measured in a clean interpreter."""
    loaded = modules_refused_at("import loquitur.schemas")
    assert loaded == [], (
        f"importing loquitur.schemas pulled in {loaded}, which the protocol-only distribution must not require"
    )


def test_the_import_boundary_refuses_a_module_outside_the_closure(tmp_path: Path) -> None:
    """Non-vacuity: the probe sees a module the allow-list refuses, whatever it is called.

    One is a package of no distribution at all, as a module of an unpublished repository would
    be; the other is a tooling distribution installed beside the package and not required by it.
    """
    package = tmp_path / "not_a_dependency"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    assert modules_refused_at("import loquitur.schemas, not_a_dependency", tmp_path) == ["not_a_dependency"]
    assert "pytest" in modules_refused_at("import loquitur.schemas, pytest")


def test_the_input_helpers_are_exported_from_the_package_root() -> None:
    import loquitur.schemas as schemas
    from loquitur.schemas import validator

    for name in ("load_json_document", "input_strictness_violation", "is_calendar_instant", "calendar_instant_errors"):
        assert name in schemas.__all__, name
        assert getattr(schemas, name) is getattr(validator, name), name
