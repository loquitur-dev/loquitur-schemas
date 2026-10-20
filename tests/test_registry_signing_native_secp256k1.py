"""The ECDSA reference in ``registry_signing`` runs on the native ``cryptography`` backend."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "loquitur" / "schemas" / "registry_signing.py"
PYPROJECT = ROOT / "pyproject.toml"


# Wheels below this floor statically link an OpenSSL affected by GHSA-537c-gmf6-5ccf.
# Asserted as a minimum rather than an exact literal: pinning the literal here would
# make every legitimate security upgrade fail the suite, which is precisely the
# brittleness that discourages patching.
MINIMUM_SECURE_CRYPTOGRAPHY = (48, 0, 1)


def test_runtime_dependency_declares_native_crypto_backend() -> None:
    payload = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dependencies = payload["project"]["dependencies"]

    declared = [item for item in dependencies if item.replace(" ", "").startswith("cryptography")]
    assert declared, "cryptography must remain a declared runtime dependency"

    floors = re.findall(r">=\s*(\d+(?:\.\d+)*)", declared[0])
    assert floors, f"cryptography dependency must declare a minimum version: {declared[0]!r}"
    floor = tuple(int(part) for part in floors[0].split("."))
    floor += (0,) * (3 - len(floor))
    assert floor >= MINIMUM_SECURE_CRYPTOGRAPHY, (
        f"cryptography floor {floor} is below the security floor "
        f"{MINIMUM_SECURE_CRYPTOGRAPHY} (GHSA-537c-gmf6-5ccf): an integrator installing this "
        "package would receive a statically linked OpenSSL with a known vulnerability"
    )


def test_registry_signing_source_uses_native_ec_backend_not_pure_python_curve_math() -> None:
    source = SRC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}

    forbidden_functions = {
        "_point_add",
        "_scalar_mult",
        "_rfc6979_generate_k",
        "_bits2int",
        "_bits2octets",
        "_int2octets",
        "_parse_uncompressed_public_key",
    }
    forbidden_constants = {"SECP256K1_P", "SECP256K1_GX", "SECP256K1_GY", "SECP256K1_G"}

    assert not (function_names & forbidden_functions)
    for constant in forbidden_constants:
        assert f"{constant} =" not in source
    assert "cryptography.hazmat.primitives.asymmetric" in source
    assert "ec.SECP256K1()" in source
