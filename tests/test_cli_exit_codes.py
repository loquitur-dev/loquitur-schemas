"""Exit status of the three commands on a usage error.

README.md documents exit 64 for a usage or setup error. ``argparse`` exits 2 on its own
usage errors, so each command is held here to 64 for every way of being used wrongly:
an unknown option, a missing argument, an unknown subcommand, no subcommand at all, an
input it cannot read and an output it cannot write. Each failure also says what went wrong
on stderr, and never as a Python traceback.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from loquitur.schemas import cli, compatibility, typescript

USAGE_ERROR = 64

Main = Callable[[Sequence[str] | None], int]

COMMANDS: dict[str, Main] = {
    "loquitur-schema-validate": cli.main,
    "python -m loquitur.schemas.compatibility": compatibility.main,
    "python -m loquitur.schemas.typescript": typescript.main,
}


def _exit_status(main: Main, argv: list[str]) -> int:
    """Run a command's main and return its exit status, whether returned or raised."""

    try:
        return main(argv)
    except SystemExit as exc:
        assert isinstance(exc.code, int), exc.code
        return exc.code


@pytest.mark.parametrize("program", sorted(COMMANDS))
def test_unknown_option_exits_64(program: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert _exit_status(COMMANDS[program], ["--no-such-option"]) == USAGE_ERROR
    err = capsys.readouterr().err
    assert f"usage: {program}" in err
    assert "unrecognized arguments: --no-such-option" in err


@pytest.mark.parametrize("program", sorted(COMMANDS))
def test_help_still_exits_0(program: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert _exit_status(COMMANDS[program], ["--help"]) == 0
    assert f"usage: {program}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["validate", "registry_entry"], "the following arguments are required: json_path"),
        (["frobnicate"], "invalid choice: 'frobnicate'"),
        (["list", "--json"], "unrecognized arguments: --json"),
    ],
)
def test_validate_usage_errors_exit_64(argv: list[str], expected: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert _exit_status(cli.main, argv) == USAGE_ERROR
    assert expected in capsys.readouterr().err


def test_validate_without_subcommand_exits_64_with_help_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert _exit_status(cli.main, []) == USAGE_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage: loquitur-schema-validate" in captured.err
    assert "{list,validate}" in captured.err


@pytest.mark.parametrize("name", ["nosuch", "nosuch.schema.json"])
def test_unknown_schema_names_what_is_accepted(name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = tmp_path / "doc.json"
    document.write_text("{}", encoding="utf-8")
    assert _exit_status(cli.main, ["validate", name, str(document)]) == USAGE_ERROR
    err = capsys.readouterr().err
    assert name in err
    assert "loquitur-schema-validate list" in err


def test_validate_help_describes_both_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert _exit_status(cli.main, ["validate", "--help"]) == 0
    out = capsys.readouterr().out
    assert "bundled schema filename" in out
    assert "path of the JSON document to validate" in out


def test_typescript_manifest_without_file_output_exits_64(capsys: pytest.CaptureFixture[str]) -> None:
    assert _exit_status(typescript.main, ["--manifest-output", "m.json"]) == USAGE_ERROR
    assert "--manifest-output requires a file --output" in capsys.readouterr().err


def test_typescript_unwritable_output_exits_64(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A directory cannot be opened for writing on any platform.
    assert _exit_status(typescript.main, ["--output", str(tmp_path)]) == USAGE_ERROR
    err = capsys.readouterr().err
    assert err.startswith("cannot write ")
    assert "Traceback" not in err


@pytest.mark.parametrize("option", ["--baseline", "--current-schema-root"])
def test_compat_unreadable_input_exits_64(option: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    if option == "--baseline":
        # A directory where a file is expected: not "not found", and not readable.
        target = tmp_path
        expected = "cannot read baseline file"
    else:
        # A schema root whose first schema is a directory.
        for name in compatibility.PUBLIC_SCHEMA_NAMES:
            (tmp_path / name).mkdir()
        target = tmp_path
        expected = "cannot read schema file"
    assert _exit_status(compatibility.main, [option, str(target)]) == USAGE_ERROR
    assert expected in capsys.readouterr().err


def test_compat_baseline_not_utf8_exits_64(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(b'{"x": "\xff"}')
    assert _exit_status(compatibility.main, ["--baseline", str(baseline)]) == USAGE_ERROR
    assert "baseline file is not UTF-8" in capsys.readouterr().err


def test_compat_changelog_not_utf8_exits_64(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_bytes(b"\xff\xfe\xfa")
    with pytest.raises(compatibility.SchemaCompatibilityError, match="changelog file is not UTF-8"):
        compatibility._require_changelog(str(changelog))
    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(compatibility.SchemaCompatibilityError, match="cannot read changelog file"):
        compatibility._require_changelog(str(directory))


def test_the_package_runs_as_the_validate_command() -> None:
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-m", "loquitur.schemas", "--version"], capture_output=True, text=True, check=False
    )
    assert (done.returncode, done.stdout.split()[:1], done.stderr) == (0, ["loquitur-schemas"], "")
