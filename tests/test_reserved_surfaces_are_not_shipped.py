"""The registry/Merkle surfaces are withheld from the package, and that must stay true.

`loquitur.schemas.merkle` and `loquitur.schemas.transparency_log` would implement
semantics that `loquitur-protocol` does not define: no tree-head format, no `log_id`, no
checkpoints, no inclusion or consistency proofs. A `log_id` is a derivation committed to
inside signed tree-head bytes, and shipping one in a release would fix that derivation by
accident, for whoever built on it.

Without these tests the boundary is a comment. A comment does not notice a file copied
into `src/`, or a new module that imports one, which is exactly how a withheld surface
appears in a wheel.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "loquitur" / "schemas"
RESERVED_AREA = REPO / "reserved"
RESERVED = RESERVED_AREA / "transparency-log"
WITHHELD = ("merkle", "transparency_log")


def test_the_withheld_modules_are_not_inside_the_package() -> None:
    present = sorted(name for name in WITHHELD if (PACKAGE / f"{name}.py").exists())
    assert not present, (
        f"{present} is under src/loquitur/schemas/ and would ship in the wheel. "
        "loquitur-protocol defines none of what it implements."
    )


def test_the_withheld_modules_are_still_in_the_repository() -> None:
    """Withheld, not deleted. If this fails the work was lost, not reserved.

    The reserved area is whole or absent: a checkout without it has nothing to check, and a
    checkout with the area and without a module has lost the module.
    """
    if not RESERVED_AREA.exists():
        return
    missing = sorted(name for name in WITHHELD if not (RESERVED / f"{name}.py").exists())
    assert not missing, f"{missing} is absent from {RESERVED}; the reserved copy is the only copy"


def test_the_withheld_modules_are_not_importable() -> None:
    """The property an integrator observes: the import fails.

    `find_spec` rather than `import`, so this reports "absent" instead of dying on the
    ImportError it is trying to assert.
    """
    for name in WITHHELD:
        assert importlib.util.find_spec(f"loquitur.schemas.{name}") is None, (
            f"loquitur.schemas.{name} resolves to a module; the withheld surface is importable"
        )


def test_no_shipped_module_imports_a_withheld_one() -> None:
    """A live import would drag the module back in, or break at runtime for an integrator.

    Both `from .merkle import ...` and `from loquitur.schemas.merkle import ...` count,
    at any nesting depth: an import inside a function body is one a top-level-only scan
    would not see.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # `from . import merkle` carries the name in the alias, not the module.
                names = {alias.name for alias in node.names} if node.level and not module else set()
                tail = module.rsplit(".", 1)[-1]
                if tail in WITHHELD or names & set(WITHHELD):
                    offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.rsplit(".", 1)[-1] in WITHHELD:
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert not offenders, f"shipped modules import a withheld surface at {offenders}"


def test_the_reserved_area_is_not_an_importable_package() -> None:
    """`transparency-log` is hyphenated on purpose.

    `src/loquitur/` has no `__init__.py`, so `loquitur.schemas` is a namespace package.
    Reserved copies filed under `loquitur/schemas/` inside the area would make
    `loquitur.schemas.merkle` importable through a second namespace portion whenever the
    repository root is on sys.path, which a test runner or an editable install can arrange,
    and the withheld surface would be importable after all. A directory name that is not
    a legal Python identifier cannot be a package portion under any sys.path. Where the
    reserved area is absent, there is nothing to import.
    """
    if not RESERVED_AREA.exists():
        return
    assert RESERVED.is_dir()
    assert not RESERVED.name.isidentifier(), (
        f"{RESERVED.name} is a legal Python identifier; the reserved area could become importable"
    )
