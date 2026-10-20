"""README quickstart drift gate.

Every CLI command documented in ``README.md`` must (a) appear verbatim in the
README and (b) execute successfully against the in-repo entry points. This
prevents documented-flag drift: documenting an option or invocation that the
installed CLI does not implement. Every ``python`` code block of the README
runs from the repository root, as the README tells the reader to run it.

The command list below is pinned on purpose. Editing a documented command in
the README without updating this test (or vice versa) fails the gate.
"""

from __future__ import annotations

import re
import shlex
import tomllib
from pathlib import Path

import pytest

from loquitur.schemas import cli as validate_cli
from loquitur.schemas import compatibility as compat_cli
from loquitur.schemas import typescript as typescript_cli

ROOT = Path(__file__).resolve().parents[1]
README_TEXT = (ROOT / "README.md").read_text(encoding="utf-8")

ENTRY_POINTS = {
    "loquitur-schema-validate": validate_cli.main,
    "python -m loquitur.schemas.typescript": typescript_cli.main,
    "python -m loquitur.schemas.compatibility": compat_cli.main,
}

DOCUMENTED_COMMANDS: tuple[str, ...] = (
    "loquitur-schema-validate --version",
    "loquitur-schema-validate list",
    "loquitur-schema-validate validate verification_summary.schema.json tests/fixtures/verification_summary.valid.json",
    "loquitur-schema-validate validate registry_entry.schema.json tests/fixtures/registry_entry.valid.json",
    "loquitur-schema-validate validate trust_registry.schema.json tests/fixtures/trust_registry.valid.json",
    "loquitur-schema-validate validate verification_summary tests/fixtures/verification_summary.valid.json",
    "loquitur-schema-validate validate registry_entry tests/fixtures/registry_entry.valid.json",
    "loquitur-schema-validate validate trust_registry tests/fixtures/trust_registry.valid.json",
    "loquitur-schema-validate validate registry_entry tests/fixtures/registry_entry.valid.json --json",
    "python -m loquitur.schemas.typescript",
    "python -m loquitur.schemas.typescript --output loquitur-protocol.d.ts",
    "python -m loquitur.schemas.compatibility",
    "python -m loquitur.schemas.compatibility --json",
)

PYTHON_BLOCKS = tuple(re.findall(r"^```python\n(.*?)^```$", README_TEXT, flags=re.MULTILINE | re.DOTALL))


@pytest.mark.parametrize("command", DOCUMENTED_COMMANDS)
def test_documented_command_appears_verbatim_in_readme(command: str) -> None:
    assert command in README_TEXT, f"command not documented verbatim in README: {command!r}"


@pytest.mark.parametrize("command", DOCUMENTED_COMMANDS)
def test_documented_command_executes_successfully(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = shlex.split(command)
    # A module is run as `python -m <module>`, and the module name is its program.
    split = 3 if argv[:2] == ["python", "-m"] else 1
    program, args = " ".join(argv[:split]), argv[split:]
    assert program in ENTRY_POINTS, f"unknown documented entry point: {program!r}"

    # File outputs are redirected into tmp_path; fixture inputs stay
    # repo-relative, so execute from the repository root.
    if "--output" in args:
        index = args.index("--output") + 1
        if args[index] != "-":
            args[index] = str(tmp_path / args[index])
    monkeypatch.chdir(ROOT)

    exit_code = ENTRY_POINTS[program](args)
    captured = capsys.readouterr()
    assert exit_code == 0, (
        f"documented command failed (exit {exit_code}): {command!r}\n"
        f"stdout: {captured.out[:500]}\nstderr: {captured.err[:500]}"
    )


def test_readme_has_a_python_example() -> None:
    assert PYTHON_BLOCKS, "README.md shows no Python usage"


@pytest.mark.parametrize("block", PYTHON_BLOCKS, ids=[f"block{i}" for i in range(len(PYTHON_BLOCKS))])
def test_readme_python_block_runs(
    block: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    exec(compile(block, "README.md", "exec"), {"__name__": "readme_example"})
    out = capsys.readouterr().out
    # The registry-entry example prints its two digests, one per line.
    assert re.findall(r"^sha256:[0-9a-f]{64}$", out, flags=re.MULTILINE), out


def test_the_install_check_is_introduced_on_one_line() -> None:
    """Other documentation finds the install check by the phrase that introduces it, on one line."""
    lines = README_TEXT.splitlines()
    assert "To check the install:" in lines
    following = lines[lines.index("To check the install:") + 1 :]
    assert following[:3] == ["", "```bash", "loquitur-schema-validate --version"]


def test_the_install_check_prints_the_package_version() -> None:
    """The version the README says the install check prints is the one pyproject.toml declares."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    printed = re.findall(r"^It prints `loquitur-schemas (\S+)`\.$", README_TEXT, flags=re.MULTILINE)
    assert printed == [project["version"]]
