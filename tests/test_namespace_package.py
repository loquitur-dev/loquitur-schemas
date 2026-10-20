"""``loquitur`` is a PEP 420 namespace shared with loquitur-verify, so no distribution may ship its ``__init__.py``.

A ``loquitur/__init__.py`` in this wheel would turn the namespace into a regular package owned by
whichever distribution installed last, and ``loquitur.verify`` would stop being importable beside
``loquitur.schemas``. The source tree and the files a built wheel lists are both held to it.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "loquitur/__init__.py"


def test_the_source_tree_has_no_namespace_init() -> None:
    assert not (ROOT / "src" / "loquitur" / "__init__.py").exists()


def test_a_built_wheel_lists_no_namespace_init(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist), str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        members = archive.namelist()
    assert FORBIDDEN not in members
    assert "loquitur/schemas/__init__.py" in members
    assert all(name.startswith(("loquitur/schemas/", "loquitur_schemas-")) for name in members), members
