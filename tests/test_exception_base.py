"""Every exception the package defines derives from ``LoquiturSchemasError`` and keeps its old base."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import loquitur.schemas as package
from loquitur.schemas import LoquiturSchemasError

# Each public exception with the built-in base it has always had.
EXPECTED_BASES: dict[str, type[BaseException]] = {
    "RegistryCanonicalizationError": ValueError,
    "SchemaCompatibilityError": ValueError,
    "SchemaNotFoundError": FileNotFoundError,
    "ReasonCodesCatalogError": Exception,
    "RegisteredVocabularyError": ValueError,
    "RegistrySigningError": ValueError,
    "TypeScriptGenerationError": ValueError,
    "SchemaValidationUsageError": ValueError,
}


def _defined_exceptions() -> dict[str, type[BaseException]]:
    found: dict[str, type[BaseException]] = {}
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"loquitur.schemas.{info.name}")
        for name, value in vars(module).items():
            if (
                isinstance(value, type)
                and issubclass(value, BaseException)
                and value.__module__ == module.__name__
                and not name.startswith("_")
            ):
                found[name] = value
    return found


def test_the_base_is_exported() -> None:
    assert "LoquiturSchemasError" in package.__all__
    assert issubclass(LoquiturSchemasError, Exception)


def test_every_exception_the_package_defines_derives_from_the_base() -> None:
    found = _defined_exceptions()
    assert set(EXPECTED_BASES) | {"LoquiturSchemasError", "TrustRootError"} == set(found)
    for name, cls in found.items():
        assert issubclass(cls, LoquiturSchemasError), name


@pytest.mark.parametrize(("name", "builtin"), sorted(EXPECTED_BASES.items()))
def test_each_public_exception_keeps_its_builtin_base(name: str, builtin: type[BaseException]) -> None:
    cls = getattr(package, name)
    assert issubclass(cls, builtin)
    assert issubclass(cls, LoquiturSchemasError)


def test_the_trust_root_error_keeps_its_base() -> None:
    from loquitur.schemas.trust_root import TrustRootError

    assert issubclass(TrustRootError, ValueError)
    assert issubclass(TrustRootError, LoquiturSchemasError)


def test_a_raised_package_error_is_caught_by_the_base() -> None:
    with pytest.raises(LoquiturSchemasError):
        package.load_schema_json("no_such_schema.schema.json")
