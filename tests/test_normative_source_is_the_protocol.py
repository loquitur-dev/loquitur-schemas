"""This package ships mirrors. loquitur-protocol owns the bytes.

The JSON Schemas and the reason-code catalog under ``src/loquitur/schemas/data/`` read
like the source of truth: they are what the code loads and what the wheel ships. They
are not the source. The specification repository carries the same bytes under
``docs/specification/``, declares that ownership in
``docs/specification/NORMATIVE_ARTIFACTS.json``, and this package's copies must follow it.

The direction matters more than the equality. An implementation that owns the schema it
implements cannot be checked against anything: whatever it does becomes correct by
definition. The specification's claim is that an outside developer can write a conforming
verifier from its published artifacts and nothing else, which is only true if the
artifacts are the specification's, not this package's.

These tests skip when loquitur-protocol is not checked out beside this repository,
because a contributor working here alone should not be blocked. They fail instead when
``LOQUITUR_REQUIRE_SIBLINGS`` is set, which the ``siblings`` job of CI does when every
sibling it reads is publicly readable.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = PACKAGE_ROOT.parent
PROTOCOL = WORKSPACE / "loquitur-protocol"
MANIFEST = PROTOCOL / "docs/specification/NORMATIVE_ARTIFACTS.json"
REQUIRE_SIBLINGS_ENV = "LOQUITUR_REQUIRE_SIBLINGS"
THIS_REPOSITORY = "loquitur-schemas"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _manifest() -> dict:
    if not MANIFEST.is_file():
        message = f"loquitur-protocol is not checked out at {PROTOCOL}, or carries no normative manifest"
        if _truthy(REQUIRE_SIBLINGS_ENV):
            pytest.fail(message)
        pytest.skip(message)
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _mirrored_here(manifest: dict) -> list[tuple[str, str, str]]:
    """Return (source_path, local_path, expected_sha256) for every artifact mirrored here."""
    pairs: list[tuple[str, str, str]] = []
    for artifact in manifest.get("artifacts", []):
        for mirror in artifact.get("mirrors", []):
            if mirror.get("repository") == THIS_REPOSITORY:
                pairs.append((artifact["path"], mirror["path"], artifact["sha256"]))
    return pairs


def test_the_protocol_declares_itself_the_owner() -> None:
    manifest = _manifest()
    assert manifest.get("owner") == "loquitur-protocol", (
        "the normative manifest does not name loquitur-protocol as owner; "
        "this package must not become the source of the schemas it implements"
    )


def test_every_mirror_this_package_ships_matches_the_protocol() -> None:
    manifest = _manifest()
    pairs = _mirrored_here(manifest)
    # Refuse to pass on nothing: if the manifest stops naming this package, the comparison
    # below becomes vacuous and would report success having checked nothing.
    assert pairs, "the normative manifest declares no mirror in this repository; nothing would be compared"

    wrong: list[str] = []
    for source_path, local_path, expected in pairs:
        local = PACKAGE_ROOT / local_path
        if not local.is_file():
            wrong.append(f"{local_path} is declared as a mirror of {source_path} but does not exist here")
            continue
        actual = hashlib.sha256(local.read_bytes()).hexdigest()
        if actual != expected:
            wrong.append(
                f"{local_path} is {actual[:16]}... but {source_path} is {expected[:16]}...; "
                "update this mirror from the protocol, not the protocol from this mirror"
            )
    assert not wrong, f"{len(wrong)} mirror(s) diverge from the specification:\n  " + "\n  ".join(wrong)


def test_the_shipped_wheel_data_is_the_mirrored_data() -> None:
    """The comparison above is worthless if the wheel ships different bytes.

    The mirrors live under ``src/``, and package-data globs decide what reaches a
    user. This asserts the mirrored files are inside the directory the build ships, so a
    packaging change that quietly stopped including one would be visible here rather than
    on PyPI.
    """
    manifest = _manifest()
    data_root = PACKAGE_ROOT / "src/loquitur/schemas/data"
    for _source_path, local_path, _expected in _mirrored_here(manifest):
        local = PACKAGE_ROOT / local_path
        if not local.is_file():
            continue
        assert data_root in local.parents, (
            f"{local_path} is a mirrored normative artifact but sits outside the packaged data directory"
        )
