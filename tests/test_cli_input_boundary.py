"""The validate CLI's input boundary: every unusable document is exit 64, never a traceback.

The published exit codes are ``1`` for valid JSON that violates the schema and ``64`` for a
usage or setup error, invalid JSON included. Bytes that are not UTF-8, a directory given as
the path and deeply nested JSON must not escape ``load_json_document`` as
``UnicodeDecodeError``, ``PermissionError`` or ``RecursionError``: the CLI would print a
traceback and exit ``1``, which a wrapper reads as "valid JSON that violates the schema".
Documents breaking the protocol's input strictness rules 2 to 4 (an integer beyond
2^53 - 1 in any spelling, a lone surrogate) are usage errors too, as the canonicalizer
refuses the same values.

Each usage row runs three ways: the library call, which must raise
``SchemaValidationUsageError`` and nothing else; ``cli.main``; and the installed console
script in a subprocess, whose stderr must carry no traceback. The lock rows pin what must
not move: a valid document exits 0, a schema-invalid one exits 1, and a document exactly at
each limit still loads. Refused rows and accepted rows run in the same tests, so each test
fails both if a refusal regresses and if an accepted document stops loading.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from loquitur.schemas import validator
from loquitur.schemas.cli import USAGE_ERROR, VALIDATION_FAILED, main
from loquitur.schemas.validator import (
    MAX_JSON_NESTING_DEPTH,
    SchemaValidationUsageError,
    load_json_document,
    validate_file,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA = "verification_receipt"
VALID = (FIXTURES / "verification_receipt.valid.json").read_bytes()
POLICY_VERSION = b'"policy_version": 1'


def _nested(depth: int) -> bytes:
    return b"[" * depth + b"0" + b"]" * depth


def _with_member(value: bytes) -> bytes:
    """The valid receipt plus one extra member, which the closed schema rejects."""
    body = VALID.rstrip()
    assert body.endswith(b"}")
    return body[:-1].rstrip() + b', "x": ' + value + b"}"


def _policy_version(spelling: bytes) -> bytes:
    assert VALID.count(POLICY_VERSION) == 1
    return VALID.replace(POLICY_VERSION, b'"policy_version": ' + spelling)


# id -> document bytes, or None for "the path is a directory"
USAGE_ROWS: dict[str, bytes | None] = {
    "ff-byte": b"\xff",
    "utf16-with-bom": b"\xff\xfe{\x00}\x00",
    "cesu8-surrogate": b'{"a": "\xed\xa0\x80"}',
    "overlong-utf8": b'{"a": "\xc0\xaf"}',
    "utf8-bom": b"\xef\xbb\xbf" + VALID,
    "directory": None,
    "depth-100000": _nested(100000),
    "depth-65": _with_member(_nested(MAX_JSON_NESTING_DEPTH)),
    "integer-2^53+1": _policy_version(b"9007199254740993"),
    "integer--(2^53+1)": _with_member(b"-9007199254740993"),
    "exponent-1e16": _policy_version(b"1e16"),
    "float-2^53": _policy_version(b"9007199254740992.0"),
    "overflow-1e400": _with_member(b"1e400"),
    "lone-surrogate-value": _with_member(b'"a\\ud800"'),
    "lone-surrogate-key": _with_member(b'{"\\udc00x": 1}'),
    "lone-low-surrogate-then-high": _with_member(b'"\\udc00\\ud800"'),
    # An integer longer than the host's int() digit-count limit (4300 by default).
    "integer-5000-digits": _with_member(b"1" * 5000),
    "negative-integer-5000-digits": _policy_version(b"-" + b"9" * 5000),
    # Excess precision: refused, not rounded.
    "excess-precision-2.0000000000000001": _policy_version(b"2.0000000000000001"),
    "underflow-4.9e-325": _with_member(b"4.9e-325"),
    "fraction-beyond-2^53": _with_member(b"9007199254740992.5"),
    "excess-digits-0.30000000000000004441": _with_member(b"0.30000000000000004441"),
    "exponent-too-large-for-decimal": _with_member(b"1e-99999999999999999999"),
    "integer-valued-1.5e300": _with_member(b"1.5e300"),
    # Input strictness rule 9: noncharacters, escaped or literal, in a value or a member name.
    "noncharacter-escape-fdd0-value": _with_member(b'"\\ufdd0"'),
    "noncharacter-escape-fdd0-key": _with_member(b'{"\\ufdd0": 1}'),
    "noncharacter-literal-ffff": _with_member('"\uffff"'.encode()),
    "noncharacter-pair-1fffe": _with_member(b'"\\ud83f\\udffe"'),
    "noncharacter-literal-10ffff-key": _with_member('{"\U0010ffff": 1}'.encode()),
    # Input strictness rule 6: depth 65 with an empty innermost container.
    "depth-65-empty-innermost": _with_member(b"[" * 63 + b"{}" + b"]" * 63),
}


def _materialise(tmp_path: Path, row: str) -> Path:
    data = USAGE_ROWS[row]
    path = tmp_path / row
    if data is None:
        path.mkdir()
    else:
        path.write_bytes(data)
    return path


# The UTF-8 BOM row and the ff-byte row: two different ways of not being UTF-8 JSON.
USAGE_GROUPS: list[tuple[str, ...]] = [("ff-byte", "utf8-bom")] + [
    (row,) for row in sorted(USAGE_ROWS) if row not in {"ff-byte", "utf8-bom"}
]
_GROUP_IDS = ["+".join(group) for group in USAGE_GROUPS]


def _console_script() -> Path:
    name = "loquitur-schema-validate.exe" if os.name == "nt" else "loquitur-schema-validate"
    script = Path(sys.executable).parent / name
    assert script.is_file(), f"console script not installed beside {sys.executable}"
    return script


@pytest.mark.parametrize("group", USAGE_GROUPS, ids=_GROUP_IDS)
@pytest.mark.parametrize(
    "call", [load_json_document, lambda p: validate_file(SCHEMA, p)], ids=["load", "validate_file"]
)
def test_the_library_raises_only_the_usage_error(
    tmp_path: Path, group: tuple[str, ...], call: Callable[[Path], object]
) -> None:
    for row in group:
        path = _materialise(tmp_path, row)
        with pytest.raises(SchemaValidationUsageError) as caught:
            call(path)
        assert type(caught.value) is SchemaValidationUsageError, row


@pytest.mark.parametrize("group", USAGE_GROUPS, ids=_GROUP_IDS)
def test_cli_main_exits_64_with_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], group: tuple[str, ...]
) -> None:
    for row in group:
        path = _materialise(tmp_path, row)
        assert main(["validate", SCHEMA, str(path), "--json"]) == USAGE_ERROR, row
        captured = capsys.readouterr()
        assert captured.out == ""
        assert len(captured.err.strip().splitlines()) == 1, captured.err


@pytest.mark.parametrize("group", USAGE_GROUPS, ids=_GROUP_IDS)
def test_console_script_exits_64_without_a_traceback(tmp_path: Path, group: tuple[str, ...]) -> None:
    for row in group:
        path = _materialise(tmp_path, row)
        proc = subprocess.run(
            [str(_console_script()), "validate", SCHEMA, str(path), "--json"],
            capture_output=True,
            timeout=120,
        )
        stderr = proc.stderr.decode("utf-8", "replace")
        assert proc.returncode == USAGE_ERROR, (row, stderr)
        assert proc.stdout == b""
        assert "Traceback" not in stderr


def test_python_m_cli_exits_64_on_bytes_that_are_not_utf8(tmp_path: Path) -> None:
    path = _materialise(tmp_path, "ff-byte")
    proc = subprocess.run(
        [sys.executable, "-m", "loquitur.schemas.cli", "validate", SCHEMA, str(path)],
        capture_output=True,
        timeout=120,
    )
    assert proc.returncode == USAGE_ERROR
    assert b"Traceback" not in proc.stderr


def test_a_host_stack_too_small_for_an_admitted_document_is_a_setup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A decoder out of stack on a document within the limit is exit 64, named for what it is.

    The pre-scan refuses depth 65 before the decoder runs, so the decoder can run out of stack
    only on a document the protocol admits, on a host whose stack is smaller than the document.
    The decoder's RecursionError is raised directly rather than reached by lowering
    ``sys.setrecursionlimit``, which the C decoder honors under Python 3.11 and ignores from
    3.12, so the test reaches the same state on every version. The refusal must name the
    interpreter's recursion limit, never the nesting limit of 64, which a 60-level document
    keeps.
    """
    path = tmp_path / "depth-60.json"
    path.write_bytes(_nested(60))

    def exhausted(*args: object, **kwargs: object) -> object:
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")

    monkeypatch.setattr(validator, "json", SimpleNamespace(loads=exhausted, JSONDecodeError=json.JSONDecodeError))
    with pytest.raises(SchemaValidationUsageError, match="recursion limit is too low to parse it$") as caught:
        load_json_document(path)
    assert type(caught.value) is SchemaValidationUsageError
    assert f"of {MAX_JSON_NESTING_DEPTH}" not in str(caught.value)
    assert main(["validate", SCHEMA, str(path), "--json"]) == USAGE_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1, captured.err


# --------------------------------------------------------------------------- locks

LOCK_ROWS: dict[str, tuple[bytes, int]] = {
    "valid": (VALID, 0),
    "schema-invalid": (_policy_version(b'"1"'), VALIDATION_FAILED),
    "depth-64-loads-then-fails-schema": (_with_member(_nested(MAX_JSON_NESTING_DEPTH - 1)), VALIDATION_FAILED),
    "integer-2^53-1": (_policy_version(b"9007199254740991"), 0),
    "float-2^53-1": (_policy_version(b"9007199254740991.0"), 0),
    "integer-valued-float": (_policy_version(b"1.0"), 0),
    "fractional-still-schema-invalid": (_policy_version(b"1.5"), VALIDATION_FAILED),
}


AT_THE_LIMITS: dict[str, tuple[str, object]] = {
    "depth-64": (_nested(MAX_JSON_NESTING_DEPTH).decode(), json.loads(_nested(MAX_JSON_NESTING_DEPTH))),
    "brackets-in-a-string": ('{"s": "' + "[" * 200 + '"}', {"s": "[" * 200}),
    "escaped-quote-before-brackets": ('{"s": "\\"[[[[\\\\", "t": ["]"]}', {"s": '"[[[[\\', "t": ["]"]}),
    "surrogate-pair": ('{"pair": "\\ud83d\\ude00"}', {"pair": "\U0001f600"}),
    "numbers-in-range": (
        '{"n": -9007199254740991, "f": 0.5, "e": 1.25e-300}',
        {"n": -9007199254740991, "f": 0.5, "e": 1.25e-300},
    ),
    # Each of these spells exactly the decimal value of its RFC 8785 serialization.
    "numbers-without-excess-precision": (
        '{"a": 0.1, "b": 1.0, "c": 1e0, "d": 1E2, "e": -0, "f": 1e-7, "g": 5e-324, "h": 0e99999999999999999999}',
        {"a": 0.1, "b": 1.0, "c": 1.0, "d": 100.0, "e": 0, "f": 1e-7, "g": 5e-324, "h": 0.0},
    ),
    # Input strictness rule 7: U+FEFF inside a string is a scalar value like any other.
    "byte-order-mark-inside-a-string": ('{"s": "\\ufeff\ufeff"}', {"s": "\ufeff\ufeff"}),
    # Input strictness rule 9: the neighbors of the noncharacters are ordinary characters.
    "noncharacter-neighbours": (
        '{"\ufdcf": "\\ufdf0\\ufffd\\ud83f\\udffd"}',
        {"\ufdcf": "\ufdf0\ufffd\U0001fffd"},
    ),
    # Input strictness rule 6: depth 64 with an empty innermost container.
    "depth-64-empty-innermost": ("[" * 63 + "[]" + "]" * 63, json.loads("[" * 63 + "[]" + "]" * 63)),
}


def test_documents_inside_every_limit_load_and_keep_their_exit_code(tmp_path: Path) -> None:
    got_exit = {}
    for row, (data, _expected) in LOCK_ROWS.items():
        path = tmp_path / f"{row}.json"
        path.write_bytes(data)
        got_exit[row] = main(["validate", SCHEMA, str(path)])
    assert got_exit == {row: expected for row, (_data, expected) in LOCK_ROWS.items()}
    got_loaded = {}
    for row, (text, _expected) in AT_THE_LIMITS.items():
        path = tmp_path / f"limit-{row}.json"
        path.write_bytes(text.encode("utf-8"))
        got_loaded[row] = load_json_document(path)
    assert got_loaded == {row: expected for row, (_text, expected) in AT_THE_LIMITS.items()}


def test_console_script_keeps_exit_0_and_1(tmp_path: Path) -> None:
    rows = ["valid", "schema-invalid", "integer-valued-float"]
    got = {}
    for row in rows:
        data, _expected = LOCK_ROWS[row]
        path = tmp_path / f"{row}.json"
        path.write_bytes(data)
        proc = subprocess.run([str(_console_script()), "validate", SCHEMA, str(path)], capture_output=True, timeout=120)
        got[row] = proc.returncode
    assert got == {row: LOCK_ROWS[row][1] for row in rows}
