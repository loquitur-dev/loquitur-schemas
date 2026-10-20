"""The package root re-exports names of two modules that are also run with ``python -m``.

``loquitur.schemas.typescript`` and ``loquitur.schemas.compatibility`` are documented
commands. If the package imported them eagerly, runpy would warn on stderr that the module
was found in ``sys.modules`` before execution. The names are therefore resolved lazily, and
these tests hold that, and that the public names are unchanged.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import loquitur.schemas as schemas

SRC = Path(__file__).resolve().parents[1] / "src"
LAZY_MODULES = ("compatibility", "typescript")


def _lazy_names() -> list[tuple[str, str]]:
    return sorted(schemas._LAZY_SUBMODULES.items())


@pytest.mark.parametrize(("name", "module"), _lazy_names())
def test_lazy_name_is_the_object_of_its_module(name: str, module: str) -> None:
    owner = importlib.import_module(f"loquitur.schemas.{module}")
    assert getattr(schemas, name) is getattr(owner, name)
    assert name in schemas.__all__
    assert name in dir(schemas)


def test_every_name_in_all_resolves() -> None:
    for name in schemas.__all__:
        assert hasattr(schemas, name), name


def test_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        schemas.no_such_name  # noqa: B018


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, env=env, check=False)


def test_importing_the_package_does_not_import_the_two_modules() -> None:
    code = (
        "import sys, loquitur.schemas\n"
        "bad = [m for m in ('loquitur.schemas.typescript', 'loquitur.schemas.compatibility')"
        " if m in sys.modules]\n"
        "sys.exit(1 if bad else 0)\n"
    )
    assert _run("-c", code).returncode == 0


@pytest.mark.parametrize("module", LAZY_MODULES)
def test_module_runs_without_a_runpy_warning(module: str) -> None:
    done = _run("-W", "error", "-m", f"loquitur.schemas.{module}", "--help")
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""


def test_package_main_is_unaffected() -> None:
    done = _run("-W", "error", "-m", "loquitur.schemas", "--help")
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
