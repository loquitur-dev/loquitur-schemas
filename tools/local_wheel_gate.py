#!/usr/bin/env python3
"""Local release gate for the loquitur-schemas package.

The script builds a wheel, holds it to src/, installs it into a temporary virtual
environment and runs the installed console scripts against public fixtures. It runs
locally and in CI, outside the package: the package never imports it.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def _run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def _has_pyproject_build_main() -> bool:
    try:
        import importlib.util

        if importlib.util.find_spec("build") is None:
            return False
        return importlib.util.find_spec("build.__main__") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _build_with_pyproject_build(schemas_root: Path, dist_dir: Path) -> bool:
    """Build with ``python -m build``, the standard build front end.

    Returns False only when ``build`` is not installed. A ``build`` that runs and *fails* is
    not a reason to fall back, so its ``CalledProcessError`` propagates: "build is missing"
    and "build is broken" are different outcomes, and the gate must not certify a wheel
    produced by a backend the release path never uses.
    """

    if not _has_pyproject_build_main():
        return False
    _run([sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)], cwd=schemas_root)
    return True


def _build_with_pip_wheel(schemas_root: Path, dist_dir: Path) -> bool:
    # Fallbacks are fine; silent fallbacks are not. Which backend produced the wheel decides
    # what the gate's verdict is worth, so each hand-off says so on stderr.
    print("note: `python -m build` is unavailable; falling back to `pip wheel`", file=sys.stderr)
    try:
        _run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--wheel-dir", str(dist_dir)], cwd=schemas_root)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("note: `pip wheel` failed; falling back to the setuptools backend", file=sys.stderr)
        return False


def _build_with_setuptools_backend(schemas_root: Path, dist_dir: Path) -> None:
    script = f"import setuptools.build_meta as backend; print(backend.build_wheel({str(dist_dir)!r}))"
    _run([sys.executable, "-c", script], cwd=schemas_root)


def purge_build_tree(schemas_root: Path) -> None:
    """Delete build/ and src/*.egg-info before building.

    setuptools copies src/ into build/lib and never removes anything from it, and a wheel-only
    build zips whatever build/lib holds, so a module deleted from src/ would still be packaged.
    Best-effort: the gate's own check of the wheel against the source tree stays the guard.
    """
    for path in [schemas_root / "build", *schemas_root.glob("src/*.egg-info")]:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def build_wheel(schemas_root: Path, dist_dir: Path, *, backend_only: bool = False) -> Path:
    if dist_dir.exists():
        try:
            shutil.rmtree(dist_dir)
        except PermissionError as exc:
            raise RuntimeError(
                f"could not remove existing dist directory {dist_dir}. "
                "Close any process holding files there, or pass --dist-dir pointing to a writable temporary directory."
            ) from exc
    dist_dir.mkdir(parents=True)
    purge_build_tree(schemas_root)
    if backend_only:
        _build_with_setuptools_backend(schemas_root, dist_dir)
    elif not _build_with_pyproject_build(schemas_root, dist_dir):
        if not _build_with_pip_wheel(schemas_root, dist_dir):
            _build_with_setuptools_backend(schemas_root, dist_dir)
    wheels = sorted(dist_dir.glob("loquitur_schemas-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one loquitur_schemas wheel in {dist_dir}, found {wheels}")
    return wheels[0]


def _source_package_files(schemas_root: Path) -> dict[str, bytes]:
    """The package files src/ declares, keyed as they appear inside a wheel.

    Dotfiles are excluded: a placeholder such as `.gitkeep`, which keeps an otherwise-empty
    directory in git, is not package data and is legitimately absent from the wheel.
    Excluding the whole class rather than one name keeps the next placeholder from being
    read as a packaging defect.
    """
    src_root = schemas_root / "src"
    return {
        path.relative_to(src_root).as_posix(): path.read_bytes()
        for path in sorted((src_root / "loquitur").rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith(".")
    }


def assert_wheel_matches_source(wheel: Path, schemas_root: Path) -> None:
    """Require the wheel's package members to be exactly the source tree's.

    Smoke-testing the installed console scripts cannot see a stale or out-of-tree member,
    and this package's wheel carries the JSON Schemas and the reason-code catalog
    themselves: a stale `catalog.json` is a wrong published vocabulary, and PyPI freezes it
    for the life of the version. loquitur-verify-py's wheel gate makes the same check.

    It rejects three things and accepts nothing else: a member that is not in src/, a
    src/ file missing from the wheel, and a member whose bytes differ from the file it
    claims to be.
    """
    import zipfile

    expected = _source_package_files(schemas_root)
    with zipfile.ZipFile(wheel) as archive:
        shipped = {name: archive.read(name) for name in archive.namelist() if name.startswith("loquitur/")}
    not_in_source = sorted(set(shipped) - set(expected))
    missing_from_wheel = sorted(set(expected) - set(shipped))
    bytes_differ = sorted(name for name in set(shipped) & set(expected) if shipped[name] != expected[name])
    if not_in_source or missing_from_wheel or bytes_differ:
        raise RuntimeError(
            f"{wheel.name} does not match src/: "
            f"not in src/={not_in_source}; missing from wheel={missing_from_wheel}; bytes differ={bytes_differ}"
        )


REPRODUCIBLE_EPOCH = "1700000000"


def check_reproducible(root: Path) -> str:
    """Build the wheel twice and require byte-identical output.

    Institutional supply-chain review expects a published artifact hash to be
    independently reproducible. Wheel archives embed modification timestamps, so
    reproducibility requires SOURCE_DATE_EPOCH to be fixed at build time; this
    verifies that it is sufficient rather than assuming it.
    """
    import hashlib
    import os

    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = REPRODUCIBLE_EPOCH
    env["PYTHONHASHSEED"] = "0"
    digests: list[str] = []
    for index in range(2):
        with tempfile.TemporaryDirectory(prefix=f"repro-{index}-") as tmp:
            dist = Path(tmp)
            # The return code is checked by hand rather than with `check=True`, which would
            # surface a bare CalledProcessError and leave pip's diagnosis in the captured
            # stream. This way the build's own words reach whoever is running the gate.
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "-w", str(dist)],
                env={**env, "PYTHONIOENCODING": "utf-8"},
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"reproducibility build failed (pip wheel exited {proc.returncode}):\n{proc.stderr or proc.stdout}"
                )
            wheels = sorted(dist.glob("*.whl"))
            if len(wheels) != 1:
                raise RuntimeError(f"expected exactly one wheel, found {wheels}")
            digests.append(hashlib.sha256(wheels[0].read_bytes()).hexdigest())
    if digests[0] != digests[1]:
        raise RuntimeError(
            f"wheel build is NOT reproducible with SOURCE_DATE_EPOCH={REPRODUCIBLE_EPOCH}: {digests[0]} != {digests[1]}"
        )
    return digests[0]


def input_boundary_failures(validate_cli: Path, case_dir: Path, schemas_root: Path) -> list[str]:
    """Run the installed validate CLI over the input-boundary rows; return what went wrong.

    The published contract is exit 1 for valid JSON that violates the schema and exit 64
    for a usage error, invalid JSON included. An installed CLI that crashed on bytes that
    are not UTF-8, on a directory or on deep nesting would exit 1 with a traceback, and the
    smoke test above, one valid document, cannot see that. These rows run against the
    wheel, not the source tree, so a packaging step that dropped the boundary fails here.
    """

    valid = (schemas_root / "tests" / "fixtures" / "verification_receipt.valid.json").read_bytes()
    body = valid.rstrip()[:-1].rstrip()
    rows: list[tuple[str, bytes | None, int]] = [
        ("ff-byte", b"\xff", 64),
        ("utf16-with-bom", b"\xff\xfe{\x00}\x00", 64),
        ("directory", None, 64),
        ("depth-100000", b"[" * 100000 + b"0" + b"]" * 100000, 64),
        ("depth-65", body + b', "x": ' + b"[" * 64 + b"0" + b"]" * 64 + b"}", 64),
        ("integer-2^53+1", valid.replace(b'"policy_version": 1', b'"policy_version": 9007199254740993'), 64),
        ("exponent-1e16", valid.replace(b'"policy_version": 1', b'"policy_version": 1e16'), 64),
        ("lone-surrogate", body + b', "x": "\\ud800"}', 64),
        ("valid", valid, 0),
        ("schema-invalid", valid.replace(b'"policy_version": 1', b'"policy_version": "1"'), 1),
    ]
    case_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for name, data, expected in rows:
        path = case_dir / name
        if data is None:
            path.mkdir(exist_ok=True)
        else:
            path.write_bytes(data)
        proc = subprocess.run(
            [str(validate_cli), "validate", "verification_receipt", str(path), "--json"],
            capture_output=True,
            timeout=300,
        )
        stderr = proc.stderr.decode("utf-8", "replace")
        if proc.returncode != expected:
            failures.append(f"{name}: exit {proc.returncode}, expected {expected}")
        elif "Traceback" in stderr:
            failures.append(f"{name}: traceback on stderr")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/install/smoke-test the loquitur-schemas wheel.")
    parser.add_argument("--schemas-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist-dir", type=Path, default=None)
    parser.add_argument("--no-deps", action="store_true", help="Install the built wheel with --no-deps.")
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Build with the configured setuptools backend directly; useful for offline RC checks.",
    )
    parser.add_argument(
        "--check-reproducible",
        action="store_true",
        help="Verify the wheel builds byte-identically twice with SOURCE_DATE_EPOCH fixed.",
    )
    args = parser.parse_args(argv)

    schemas_root = args.schemas_root.resolve()

    if args.check_reproducible:
        digest = check_reproducible(schemas_root)
        print(f"wheel_reproducible_ok sha256={digest}")
        return 0

    with tempfile.TemporaryDirectory(prefix="loquitur-schemas-wheel-gate-") as tmp:
        work_dir = Path(tmp)
        dist_dir = args.dist_dir.resolve() if args.dist_dir else work_dir / "dist"
        if args.backend_only:
            wheel = build_wheel(schemas_root, dist_dir, backend_only=True)
        else:
            wheel = build_wheel(schemas_root, dist_dir)

        # Before anything is installed: an artifact that does not match src/ must not be
        # smoke-tested into a green result. The smoke tests exercise the CLI, which a
        # stale schema or a stale catalog would survive.
        assert_wheel_matches_source(wheel, schemas_root)

        venv_dir = work_dir / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        if sys.platform == "win32":
            python = venv_dir / "Scripts" / "python.exe"
            validate_cli = venv_dir / "Scripts" / "loquitur-schema-validate.exe"
        else:
            python = venv_dir / "bin" / "python"
            validate_cli = venv_dir / "bin" / "loquitur-schema-validate"

        install_cmd = [str(python), "-m", "pip", "install"]
        if args.no_deps:
            install_cmd.append("--no-deps")
        install_cmd.append(str(wheel))
        _run(install_cmd)

        fixture = schemas_root / "tests" / "fixtures" / "registry_entry.catalog_valid.json"
        _run([str(validate_cli), "--version"])
        _run([str(validate_cli), "list"])
        _run([str(validate_cli), "validate", "registry_entry", str(fixture)])

        failures = input_boundary_failures(validate_cli, work_dir / "input-boundary", schemas_root)
        if failures:
            raise RuntimeError("installed CLI input boundary: " + "; ".join(failures))

    print(f"wheel_gate_ok {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
