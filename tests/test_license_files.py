"""The package is licensed under `MIT OR Apache-2.0`, and ships both license texts.

The license expression in `pyproject.toml` is what the package metadata declares, and every
file `license-files` names goes into the wheel and the sdist. A distribution that left out
one of the two texts would declare a license whose terms it does not carry.

LICENSE-APACHE and LICENSE-MIT are the files loquitur-verify-py, loquitur-verify-ts and
loquitur-protocol carry, byte for byte: the digests below are the sha256 of the committed
bytes, the same in every copy, so a change to the text shows up here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from test_preview_status import _pyproject

ROOT = Path(__file__).resolve().parents[1]
APACHE_SHA256 = "b67e145e47c0c9b190b0bc542481e05c5f9d001d78fda0dd5c41fb8b12d4c192"
MIT_SHA256 = "cd1a09a7a2e280075e41892deb81c8b552bd8e817597f9d0e357ba9a5546e83a"
OWNER = "Andrea Venè"


def test_metadata_declares_the_dual_license() -> None:
    project = _pyproject()["project"]
    assert project["license"] == "MIT OR Apache-2.0"
    assert project["license-files"] == ["LICENSE-APACHE", "LICENSE-MIT", "NOTICE"]
    assert not any(classifier.startswith("License ::") for classifier in project["classifiers"])


def test_the_apache_text_is_the_one_the_other_repositories_carry() -> None:
    data = (ROOT / "LICENSE-APACHE").read_bytes()
    assert hashlib.sha256(data).hexdigest() == APACHE_SHA256
    assert f"   Copyright 2026 {OWNER}\n" in data.decode("utf-8")


def test_the_mit_text_is_the_one_the_other_repositories_carry() -> None:
    data = (ROOT / "LICENSE-MIT").read_bytes()
    assert hashlib.sha256(data).hexdigest() == MIT_SHA256
    assert f"\nCopyright (c) 2026 {OWNER}\n" in data.decode("utf-8")


def test_the_root_has_no_single_license_file() -> None:
    assert not (ROOT / "LICENSE").exists()


def test_the_sdist_manifest_includes_both_texts_and_the_notice() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
    for name in ("LICENSE-APACHE", "LICENSE-MIT", "NOTICE"):
        assert f"include {name}" in manifest


def test_notice_and_readme_state_the_same_license() -> None:
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "MIT OR Apache-2.0" in notice
    assert "MIT OR Apache-2.0" in readme
    assert "at your option" in readme
