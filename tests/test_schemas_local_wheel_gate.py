from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_gate_module():
    gate_path = Path(__file__).resolve().parents[1] / "tools" / "local_wheel_gate.py"
    spec = importlib.util.spec_from_file_location("schemas_local_wheel_gate_for_tests", gate_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_testing_doc_states_the_reproducibility_epoch_the_gate_uses() -> None:
    gate = _load_gate_module()
    text = (Path(__file__).resolve().parents[1] / "docs" / "maintainers" / "testing.md").read_text(encoding="utf-8")
    assert "python tools/local_wheel_gate.py --check-reproducible" in text
    assert f"`SOURCE_DATE_EPOCH` fixed to {gate.REPRODUCIBLE_EPOCH}," in text


def test_pyproject_build_probe_handles_missing_build_without_traceback(monkeypatch) -> None:
    gate = _load_gate_module()

    def fake_find_spec(name: str):
        if name == "build":
            return None
        raise AssertionError(f"unexpected probe for {name}")

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert gate._has_pyproject_build_main() is False


def test_pyproject_build_probe_handles_partial_build_install_without_traceback(monkeypatch) -> None:
    gate = _load_gate_module()

    class DummySpec:
        pass

    def fake_find_spec(name: str):
        if name == "build":
            return DummySpec()
        if name == "build.__main__":
            raise ModuleNotFoundError("No module named 'build.__main__'")
        raise AssertionError(f"unexpected probe for {name}")

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    assert gate._has_pyproject_build_main() is False


def test_main_uses_temporary_dist_dir_by_default(monkeypatch, tmp_path) -> None:
    gate = _load_gate_module()
    schemas_root = tmp_path / "schemas"
    schemas_root.mkdir()
    captured: dict[str, Path] = {}

    def fake_build_wheel(root: Path, dist_dir: Path) -> Path:
        captured["root"] = root
        captured["dist_dir"] = dist_dir
        dist_dir.mkdir(parents=True, exist_ok=True)
        wheel = dist_dir / "loquitur_schemas-0.1.0-py3-none-any.whl"
        wheel.write_text("fake", encoding="utf-8")
        return wheel

    class DummyEnvBuilder:
        def __init__(self, **_: object) -> None:
            pass

        def create(self, _: Path) -> None:
            pass

    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> None:
        calls.append(args)

    monkeypatch.setattr(gate, "build_wheel", fake_build_wheel)
    monkeypatch.setattr(gate.venv, "EnvBuilder", DummyEnvBuilder)
    monkeypatch.setattr(gate, "_run", fake_run)
    # This test is about WHERE main() puts the dist directory, and it gets there with a
    # wheel that is a text file. The wheel/source comparison is stubbed for the same
    # reason the builder, the venv and the subprocess runner are: it is a different
    # property, and it has its own tests below.
    monkeypatch.setattr(gate, "assert_wheel_matches_source", lambda wheel, root: None)
    boundary_calls: list[Path] = []
    monkeypatch.setattr(gate, "input_boundary_failures", lambda cli, case_dir, root: boundary_calls.append(cli) or [])

    assert gate.main(["--schemas-root", str(schemas_root)]) == 0
    assert boundary_calls, "expected the installed CLI's input boundary rows to run"
    assert captured["root"] == schemas_root.resolve()
    assert captured["dist_dir"] != schemas_root.resolve() / "dist"
    assert schemas_root.resolve() not in captured["dist_dir"].parents
    assert calls, "expected install and CLI smoke commands to be invoked"


def _wheel_from(tmp_path: Path, members: dict[str, bytes]) -> Path:
    import zipfile

    wheel = tmp_path / "loquitur_schemas-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return wheel


def _schemas_root_with(tmp_path: Path, files: dict[str, bytes]) -> Path:
    root = tmp_path / "schemas"
    for name, payload in files.items():
        target = root / "src" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return root


def test_wheel_matching_source_is_accepted(tmp_path) -> None:
    """The control. Without it the three rejections below could all be false alarms."""
    gate = _load_gate_module()
    source = {"loquitur/schemas/cli.py": b"x = 1\n", "loquitur/schemas/data/a.schema.json": b"{}\n"}
    root = _schemas_root_with(tmp_path, source)
    wheel = _wheel_from(tmp_path, {name: payload for name, payload in source.items()})

    gate.assert_wheel_matches_source(wheel, root)


def test_wheel_carrying_a_module_not_in_source_is_rejected(tmp_path) -> None:
    import pytest

    gate = _load_gate_module()
    source = {"loquitur/schemas/cli.py": b"x = 1\n"}
    root = _schemas_root_with(tmp_path, source)
    wheel = _wheel_from(tmp_path, {**source, "loquitur/schemas/smuggled.py": b"# not in src/\n"})

    with pytest.raises(RuntimeError, match="not in src/"):
        gate.assert_wheel_matches_source(wheel, root)


def test_wheel_missing_a_source_file_is_rejected(tmp_path) -> None:
    import pytest

    gate = _load_gate_module()
    root = _schemas_root_with(
        tmp_path,
        {"loquitur/schemas/cli.py": b"x = 1\n", "loquitur/schemas/data/a.schema.json": b"{}\n"},
    )
    wheel = _wheel_from(tmp_path, {"loquitur/schemas/cli.py": b"x = 1\n"})

    with pytest.raises(RuntimeError, match="missing from wheel"):
        gate.assert_wheel_matches_source(wheel, root)


def test_wheel_with_stale_bytes_is_rejected(tmp_path) -> None:
    """The case the CLI smoke tests cannot see.

    A stale `catalog.json` or schema still installs and still answers `--version`, so the
    published vocabulary can be wrong while every other check in this gate is green.
    """
    import pytest

    gate = _load_gate_module()
    root = _schemas_root_with(tmp_path, {"loquitur/schemas/data/catalog.json": b'{"code": "INTEGRITY_OK"}\n'})
    wheel = _wheel_from(tmp_path, {"loquitur/schemas/data/catalog.json": b'{"code": "STALE"}\n'})

    with pytest.raises(RuntimeError, match="bytes differ"):
        gate.assert_wheel_matches_source(wheel, root)


def test_dotfiles_in_source_are_not_treated_as_missing_package_data(tmp_path) -> None:
    """A `.gitkeep` keeps an empty directory in git and is not package data.

    Excluded as a class rather than by name, so the next placeholder does not read as a
    packaging defect.
    """
    gate = _load_gate_module()
    root = _schemas_root_with(
        tmp_path,
        {"loquitur/schemas/types/.gitkeep": b"", "loquitur/schemas/cli.py": b"x = 1\n"},
    )
    wheel = _wheel_from(tmp_path, {"loquitur/schemas/cli.py": b"x = 1\n"})

    gate.assert_wheel_matches_source(wheel, root)


def test_input_boundary_rows_pass_against_the_installed_console_script(tmp_path) -> None:
    """The gate's rows, run here against the console script of the environment under test.

    The gate runs them against a freshly installed wheel; running them here keeps the rows
    themselves honest, so a wrong expected exit code fails in the suite and not only at
    release time.
    """
    import os
    import sys

    gate = _load_gate_module()
    name = "loquitur-schema-validate.exe" if os.name == "nt" else "loquitur-schema-validate"
    script = Path(sys.executable).parent / name
    assert script.is_file(), f"console script not installed beside {sys.executable}"
    schemas_root = Path(__file__).resolve().parents[1]

    assert gate.input_boundary_failures(script, tmp_path / "rows", schemas_root) == []


def test_main_fails_when_an_input_boundary_row_fails(monkeypatch, tmp_path) -> None:
    import pytest

    gate = _load_gate_module()

    def fake_build_wheel(root: Path, dist_dir: Path) -> Path:
        dist_dir.mkdir(parents=True, exist_ok=True)
        return dist_dir / "loquitur_schemas-0.1.0-py3-none-any.whl"

    class DummyEnvBuilder:
        def __init__(self, **_: object) -> None:
            pass

        def create(self, _: Path) -> None:
            pass

    monkeypatch.setattr(gate, "build_wheel", fake_build_wheel)
    monkeypatch.setattr(gate.venv, "EnvBuilder", DummyEnvBuilder)
    monkeypatch.setattr(gate, "_run", lambda args, **_: None)
    monkeypatch.setattr(gate, "assert_wheel_matches_source", lambda wheel, root: None)
    monkeypatch.setattr(gate, "input_boundary_failures", lambda cli, case_dir, root: ["ff-byte: exit 1, expected 64"])

    with pytest.raises(RuntimeError, match="ff-byte: exit 1, expected 64"):
        gate.main(["--schemas-root", str(tmp_path)])


def test_build_wheel_reports_locked_dist_dir(monkeypatch, tmp_path) -> None:
    import pytest

    gate = _load_gate_module()
    schemas_root = tmp_path / "schemas"
    dist_dir = schemas_root / "dist"
    dist_dir.mkdir(parents=True)

    def raise_permission_error(_: Path) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(gate.shutil, "rmtree", raise_permission_error)

    with pytest.raises(RuntimeError, match="could not remove existing dist directory"):
        gate.build_wheel(schemas_root, dist_dir)
