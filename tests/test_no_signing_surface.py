"""The package takes no private key and produces no signature.

Signing tools are not part of 0.1.0 (README.md). The package builds the bytes a signer
signs; making a signature, holding a key or calling a key-management service is left to a
separate tool. This guard keeps a signing function from coming back into the package source
or its exported names unnoticed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import loquitur.schemas as package

SOURCE = Path(__file__).resolve().parents[1] / "src" / "loquitur" / "schemas"

# What only a signer does with `cryptography`: make or load a private key, or sign.
PRIVATE_KEY_CALLS = {"generate_private_key", "derive_private_key", "load_pem_private_key", "load_der_private_key"}


def _python_files() -> list[Path]:
    files = sorted(SOURCE.rglob("*.py"))
    assert files, f"no package source under {SOURCE}; the guard would pass over nothing"
    return files


def test_no_package_module_makes_a_private_key_or_signs() -> None:
    found: list[str] = []
    for path in _python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if name in PRIVATE_KEY_CALLS or name == "sign":
                    found.append(f"{path.relative_to(SOURCE)}:{node.lineno} calls {name}")
    assert found == []


def test_no_exported_name_offers_signing_or_a_private_key() -> None:
    exported = list(package.__all__)
    assert "canonicalize_registry_entry_signing_payload" in exported, "the exported list is not the one expected"
    offending = [
        name
        for name in exported
        if name.lower().startswith("sign_") or "private" in name.lower() or "signer" in name.lower()
    ]
    assert offending == []
    for removed in ("sign_registry_entry_with_demo_key", "DemoSecp256k1Key", "secp256k1_public_key_from_private_key"):
        assert not hasattr(package, removed), removed


def test_the_external_signer_module_is_not_shipped() -> None:
    assert not (SOURCE / "external_signer.py").exists()
