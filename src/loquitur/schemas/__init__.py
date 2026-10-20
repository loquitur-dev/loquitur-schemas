"""JSON Schemas, reason-code catalog and registered vocabularies of the Loquitur protocol.

The package also carries the validator for those schemas, the canonicalization and digest
functions of a registry entry, and the builders of the registry-entry signing message.
"""

# This package has no Merkle-tree or transparency-log module, and the absence is
# deliberate. `loquitur-protocol`, which owns the normative bytes, defines no tree-head
# format, no `log_id`, no checkpoints and no inclusion or consistency proofs, and a package
# that implements the protocol does not define them in its place: whatever a released
# module fixed, every artifact built against it would then hold the protocol to.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .canonical import (
    RegistryCanonicalizationError,
    canonical_json_bytes,
    canonicalize_registry_entry,
    registry_entry_hash,
    sha256_uri,
)
from .cryptographic_capabilities import (
    CRYPTOGRAPHIC_CAPABILITY_PROFILE,
    RESERVED_UNSUPPORTED_ALGORITHMS,
    SUPPORTED_SIGNATURE_ALGORITHMS,
    SUPPORTED_SIGNATURE_PAIRS,
    SUPPORTED_TRUST_KEY_TYPES,
    signature_algorithm_supported,
    signature_pair_supported,
    trust_key_type_supported,
)
from .errors import LoquiturSchemasError
from .inventory import (
    CANONICAL_SCHEMA_URI_BASE,
    PUBLIC_CANONICAL_SCHEMA_NAMES,
    PUBLIC_REGISTRY_SCHEMA_NAMES,
    PUBLIC_SCHEMA_IDS,
    PUBLIC_SCHEMA_NAMES,
    PUBLIC_SCHEMA_NAMES_BY_ID,
    SchemaNotFoundError,
    canonical_schema_uri,
    list_schema_names,
    load_schema_json,
    load_schema_text,
    schema_data_root,
    schema_name_for_uri,
)
from .reason_codes_catalog import (
    CATALOG_AUDIENCES,
    CATALOG_VERSION,
    CATALOG_VOCABULARY,
    CatalogEntry,
    ComplianceNarrative,
    ExecutiveNarrative,
    ReasonCodesCatalog,
    ReasonCodesCatalogError,
    TechnicalNarrative,
    catalog_data_path,
    load_reason_codes_catalog,
)
from .registered_vocabularies import (
    REGISTERED_VOCABULARY_KINDS,
    RegisteredVocabularyError,
    load_registered_vocabulary,
    value_status,
)
from .registry_signing import (
    SIGNATURE_ALGORITHM,
    SIGNING_DOMAIN_PREFIX,
    SIGNING_ENVELOPE_DOMAIN,
    SIGNING_ENVELOPE_SCHEMA,
    SIGNING_PAYLOAD_EXCLUDED_FIELDS,
    SIGNING_PAYLOAD_ID,
    SIGNING_PAYLOAD_SCHEMA,
    SIGNING_PAYLOAD_VERSION,
    RegistrySigningError,
    canonicalize_registry_entry_signing_payload,
    registry_entry_signing_envelope,
    registry_entry_signing_payload,
    registry_entry_signing_payload_hash,
)
from .trust_root import (
    TrustRootError,
    trust_registry_signing_bytes,
    trust_registry_signing_envelope,
    trust_registry_signing_payload,
)
from .validator import (
    OBJECT_TYPE_TO_SCHEMA_NAME,
    SchemaValidationUsageError,
    ValidationErrorDetail,
    ValidationResult,
    calendar_instant_errors,
    input_strictness_violation,
    is_calendar_instant,
    load_json_document,
    resolve_schema_name,
    schema_name_for_object_type,
    validate_by_object_type,
    validate_file,
    validate_instance,
)
from .verdict_grounds import (
    SEVERITY_ORDER,
    SEVERITY_TO_STATUS,
    max_severity,
    status_for_codes,
    verdict_grounds_errors,
)
from .verification_vocabulary import (
    REGISTRY_VERDICTS,
    STATUS_TO_REGISTRY_VERDICT,
    VERIFICATION_STATUSES,
    VERIFICATION_VOCABULARY_PROFILE,
    registry_verdict_supported,
    verification_status_supported,
)

if TYPE_CHECKING:
    from .compatibility import (
        BASELINE_FILENAME,
        BREAKING,
        REVIEW_REQUIRED,
        CompatibilityFinding,
        CompatibilityReport,
        SchemaCompatibilityError,
        check_schema_compatibility,
        compatibility_baseline_root,
        load_bundled_compatibility_baseline,
        load_schema_map_from_root,
        snapshot_public_canonical_contracts,
    )
    from .typescript import (
        GENERATED_DECLARATION_FILENAME,
        GENERATED_DECLARATION_MANIFEST_FILENAME,
        GENERATOR_ID,
        TypeScriptGenerationError,
        generate_typescript_declaration_manifest,
        generate_typescript_declarations,
        load_typescript_declaration_manifest,
        load_typescript_declarations,
        typescript_data_root,
        write_typescript_declarations,
    )

# `compatibility` and `typescript` are also run as `python -m loquitur.schemas.<name>`.
# Importing them here would leave them in sys.modules before runpy executes them and make
# runpy warn, so their names are resolved on first access (PEP 562) and the public names
# stay the same.
_LAZY_SUBMODULES: dict[str, str] = {
    "BASELINE_FILENAME": "compatibility",
    "BREAKING": "compatibility",
    "REVIEW_REQUIRED": "compatibility",
    "CompatibilityFinding": "compatibility",
    "CompatibilityReport": "compatibility",
    "SchemaCompatibilityError": "compatibility",
    "check_schema_compatibility": "compatibility",
    "compatibility_baseline_root": "compatibility",
    "load_bundled_compatibility_baseline": "compatibility",
    "load_schema_map_from_root": "compatibility",
    "snapshot_public_canonical_contracts": "compatibility",
    "GENERATED_DECLARATION_FILENAME": "typescript",
    "GENERATED_DECLARATION_MANIFEST_FILENAME": "typescript",
    "GENERATOR_ID": "typescript",
    "TypeScriptGenerationError": "typescript",
    "generate_typescript_declaration_manifest": "typescript",
    "generate_typescript_declarations": "typescript",
    "load_typescript_declaration_manifest": "typescript",
    "load_typescript_declarations": "typescript",
    "typescript_data_root": "typescript",
    "write_typescript_declarations": "typescript",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_SUBMODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_SUBMODULES})


__all__ = [
    "calendar_instant_errors",
    "input_strictness_violation",
    "is_calendar_instant",
    "load_json_document",
    "LoquiturSchemasError",
    "RegistrySigningError",
    "SIGNATURE_ALGORITHM",
    "SIGNING_DOMAIN_PREFIX",
    "SIGNING_ENVELOPE_DOMAIN",
    "SIGNING_ENVELOPE_SCHEMA",
    "SIGNING_PAYLOAD_EXCLUDED_FIELDS",
    "SIGNING_PAYLOAD_ID",
    "SIGNING_PAYLOAD_SCHEMA",
    "SIGNING_PAYLOAD_VERSION",
    "registry_entry_signing_payload",
    "canonicalize_registry_entry_signing_payload",
    "registry_entry_signing_envelope",
    "registry_entry_signing_payload_hash",
    "sha256_uri",
    "registry_entry_hash",
    "canonicalize_registry_entry",
    "canonical_json_bytes",
    "RegistryCanonicalizationError",
    "BASELINE_FILENAME",
    "BREAKING",
    "REVIEW_REQUIRED",
    "CompatibilityFinding",
    "CompatibilityReport",
    "SchemaCompatibilityError",
    "compatibility_baseline_root",
    "load_bundled_compatibility_baseline",
    "snapshot_public_canonical_contracts",
    "check_schema_compatibility",
    "load_schema_map_from_root",
    "write_typescript_declarations",
    "generate_typescript_declarations",
    "load_typescript_declarations",
    "typescript_data_root",
    "TypeScriptGenerationError",
    "GENERATED_DECLARATION_FILENAME",
    "CANONICAL_SCHEMA_URI_BASE",
    "PUBLIC_CANONICAL_SCHEMA_NAMES",
    "PUBLIC_REGISTRY_SCHEMA_NAMES",
    "PUBLIC_SCHEMA_IDS",
    "PUBLIC_SCHEMA_NAMES",
    "PUBLIC_SCHEMA_NAMES_BY_ID",
    "SchemaNotFoundError",
    "SchemaValidationUsageError",
    "ValidationErrorDetail",
    "ValidationResult",
    "OBJECT_TYPE_TO_SCHEMA_NAME",
    "canonical_schema_uri",
    "schema_data_root",
    "schema_name_for_uri",
    "list_schema_names",
    "load_schema_text",
    "load_schema_json",
    "schema_name_for_object_type",
    "resolve_schema_name",
    "validate_instance",
    "validate_by_object_type",
    "validate_file",
    # Registered vocabularies
    "REGISTERED_VOCABULARY_KINDS",
    "RegisteredVocabularyError",
    "load_registered_vocabulary",
    "value_status",
    # Reason codes catalog
    "CATALOG_AUDIENCES",
    "CATALOG_VERSION",
    "CATALOG_VOCABULARY",
    "CatalogEntry",
    "ComplianceNarrative",
    "ExecutiveNarrative",
    "ReasonCodesCatalog",
    "ReasonCodesCatalogError",
    "TechnicalNarrative",
    "catalog_data_path",
    "load_reason_codes_catalog",
    "TrustRootError",
    "trust_registry_signing_bytes",
    "trust_registry_signing_envelope",
    "trust_registry_signing_payload",
    "SEVERITY_ORDER",
    "SEVERITY_TO_STATUS",
    "max_severity",
    "status_for_codes",
    "verdict_grounds_errors",
    "CRYPTOGRAPHIC_CAPABILITY_PROFILE",
    "RESERVED_UNSUPPORTED_ALGORITHMS",
    "SUPPORTED_SIGNATURE_ALGORITHMS",
    "SUPPORTED_SIGNATURE_PAIRS",
    "SUPPORTED_TRUST_KEY_TYPES",
    "signature_algorithm_supported",
    "signature_pair_supported",
    "trust_key_type_supported",
    "GENERATED_DECLARATION_MANIFEST_FILENAME",
    "GENERATOR_ID",
    "generate_typescript_declaration_manifest",
    "load_typescript_declaration_manifest",
    "VERIFICATION_VOCABULARY_PROFILE",
    "VERIFICATION_STATUSES",
    "REGISTRY_VERDICTS",
    "STATUS_TO_REGISTRY_VERDICT",
    "verification_status_supported",
    "registry_verdict_supported",
]

__version__ = "0.1.0"
