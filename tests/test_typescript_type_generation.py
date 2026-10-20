from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from loquitur.schemas.typescript import (
    GENERATED_DECLARATION_FILENAME,
    GENERATED_DECLARATION_MANIFEST_FILENAME,
    generate_typescript_declaration_manifest,
    generate_typescript_declarations,
    load_typescript_declaration_manifest,
    load_typescript_declarations,
    main,
    write_typescript_declarations,
)

PACKAGE_TYPES = (
    Path(__file__).resolve().parents[1] / "src" / "loquitur" / "schemas" / "types" / GENERATED_DECLARATION_FILENAME
)

# The compile check below needs a TypeScript compiler, and it is the one test that asks
# whether the declarations this package ships typecheck. A skip reads as green, so
# a run that anybody relies on must not skip it.
#
# A contributor without Node should still be able to run the suite, so the skip stays by
# default. Where the answer is required, the environment says so: with LOQUITUR_REQUIRE_TSC
# set, a missing or hung compiler fails the test instead. The CI workflow installs a pinned
# compiler and sets it.
REQUIRE_TSC_ENV = "LOQUITUR_REQUIRE_TSC"


def _compiler_unavailable(message: str) -> None:
    if os.environ.get(REQUIRE_TSC_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        pytest.fail(f"{message}, and {REQUIRE_TSC_ENV} requires it")
    pytest.skip(message)


def test_typescript_declarations_are_generated_from_bundled_schemas() -> None:
    declarations = generate_typescript_declarations()

    assert "export interface VerificationSummary" in declarations
    assert 'object_type: "verification_summary";' in declarations
    assert 'schema_version: "v2";' in declarations
    assert "asset_type?: string | null;" in declarations
    assert 'export type VerificationStatus = "pass" | "warning" | "review" | "fail";' in declarations
    assert 'export type RegistryVerdict = "PASS" | "WARN" | "REVIEW" | "FAIL";' in declarations
    assert "status: VerificationStatus;" in declarations
    assert "export type LoquiturCanonicalObject" in declarations
    # The schemas that carry the signed wire and the issuer authorization are typed too,
    # and RegistryEntry is the interface that uses RegistryVerdict.
    assert "export interface RegistryEntry" in declarations
    assert "export interface TrustRegistry" in declarations
    assert 'object_type: "registry_entry";' in declarations
    assert 'object_type: "trust_registry";' in declarations
    assert "verdict: RegistryVerdict;" in declarations
    assert "export type LoquiturRegistryObject" in declarations


def test_committed_typescript_declarations_match_generator_output() -> None:
    assert PACKAGE_TYPES.read_text(encoding="utf-8") == generate_typescript_declarations()
    assert load_typescript_declarations() == generate_typescript_declarations()


def test_write_typescript_declarations_creates_importable_artifact(tmp_path: Path) -> None:
    output = write_typescript_declarations(tmp_path / GENERATED_DECLARATION_FILENAME)
    assert output.is_file()
    # Bytes: read_text would turn a CRLF file back into LF and pass it.
    assert output.read_bytes() == PACKAGE_TYPES.read_bytes()


def test_output_option_writes_the_committed_bytes(tmp_path: Path) -> None:
    output = tmp_path / GENERATED_DECLARATION_FILENAME
    assert main(["--output", str(output)]) == 0
    assert output.read_bytes() == PACKAGE_TYPES.read_bytes()


def test_stdout_output_is_byte_identical_to_the_committed_declarations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --output the generator writes to stdout, and the bytes keep LF.

    In process, so the test runs the checkout's generator and not an installed copy, and
    through a stdout that writes each LF of text as CRLF on every platform, as a Windows
    console does, so a return to text output fails here on any OS.
    """
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw, encoding="utf-8", newline="\r\n")
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main([]) == 0
    stdout.flush()
    assert b"\r" not in raw.getvalue()
    assert raw.getvalue() == PACKAGE_TYPES.read_bytes()


def test_stdout_without_a_byte_buffer_takes_the_text() -> None:
    """A text-only stdout, such as a StringIO, gets the declarations as text, LF and all."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main([]) == 0
    assert out.getvalue() == generate_typescript_declarations()


def test_no_stdout_writes_nothing_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without any stdout (pythonw, say) there is nothing to write to, as for print."""
    monkeypatch.setattr(sys, "stdout", None)
    assert main([]) == 0


def test_generated_typescript_types_compile_in_fresh_project(tmp_path: Path) -> None:
    tsc = shutil.which("tsc")
    if tsc is None:
        _compiler_unavailable("TypeScript compiler not installed in this environment")

    project = tmp_path / "ts-smoke"
    project.mkdir()
    write_typescript_declarations(project / GENERATED_DECLARATION_FILENAME)
    (project / "index.ts").write_text(
        "\n".join(
            [
                f'import type {{ LoquiturCanonicalObject, VerificationSummary }} from "./{GENERATED_DECLARATION_FILENAME}";',
                "const summary: VerificationSummary = {",
                '  object_type: "verification_summary",',
                '  schema_version: "v2",',
                '  bundle_id: "bundle-demo",',
                '  status: "pass",',
                '  reason_code_vocabulary_version: "loquitur.reason_codes.v1",',
                # reason_codes is required, and without it `tsc --noEmit` fails on TS2741:
                # a verdict must carry the grounds it rests on, so a summary that cites
                # nothing must not typecheck either.
                '  reason_codes: ["INTEGRITY_OK"],',
                "};",
                "const canonical: LoquiturCanonicalObject = summary;",
                "console.log(canonical.object_type);",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project / "tsconfig.json").write_text(
        "\n".join(
            [
                "{",
                '  "compilerOptions": {',
                '    "strict": true,',
                '    "noEmit": true,',
                '    "target": "ES2022",',
                '    "module": "ESNext",',
                '    "moduleResolution": "Bundler",',
                '    "skipLibCheck": false',
                "  },",
                '  "include": ["index.ts", "loquitur-protocol.d.ts"]',
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    try:
        completed = subprocess.run(
            [tsc, "-p", str(project / "tsconfig.json"), "--noEmit"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        _compiler_unavailable("TypeScript compiler timed out in this environment")

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_committed_typescript_manifest_matches_generator_output() -> None:
    manifest_path = PACKAGE_TYPES.parent / GENERATED_DECLARATION_MANIFEST_FILENAME
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == generate_typescript_declaration_manifest()
    assert load_typescript_declaration_manifest() == generate_typescript_declaration_manifest()


def _run_compile_test_without_a_compiler(tmp_path: Path, require: bool) -> subprocess.CompletedProcess[str]:
    """Run the compile test in a child pytest whose PATH holds no TypeScript compiler."""
    env = {key: value for key, value in os.environ.items() if key != REQUIRE_TSC_ENV}
    env["PATH"] = str(Path(sys.executable).parent)
    if require:
        env[REQUIRE_TSC_ENV] = "1"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-rs",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(tmp_path),
            f"{Path(__file__).resolve()}::test_generated_typescript_types_compile_in_fresh_project",
        ],
        env={**env, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_a_missing_compiler_skips_by_default_and_fails_when_required(tmp_path: Path) -> None:
    default = _run_compile_test_without_a_compiler(tmp_path / "default", require=False)
    assert default.returncode == 0 and "1 skipped" in default.stdout, default.stdout + default.stderr
    required = _run_compile_test_without_a_compiler(tmp_path / "required", require=True)
    assert required.returncode == 1 and "1 failed" in required.stdout, required.stdout + required.stderr
    assert REQUIRE_TSC_ENV in required.stdout
