# Changelog

All notable changes to `loquitur-schemas` are documented in this file.
The format follows Keep a Changelog conventions; the project targets
semantic versioning once the public API stabilizes.

## [0.1.0] - 2026-10-20

First release of the `loquitur-schemas` package, a preview: it is not for use with real assets,
and its names and behavior can change in any 0.x release, as README.md states.

### Added
- The public JSON Schema contracts of the protocol objects `verification_summary`,
  `verification_receipt`, `change_summary`, `lineage_summary` and `coverage_summary`, and the
  registry commitment schemas `registry_entry` and `trust_registry`.
- Deterministic registry canonicalization helpers, the registry-entry signing message
  (Signing Envelope v2), and the message a root key signs over a trust registry. The protocol
  defines no earlier signing payload. Signing tools are not part of this release: no function
  takes a private key or produces a signature.
- The public reason-code catalog, and TypeScript declaration generation for the schema
  surface.
- The registered vocabularies of asset types, workflows and anchoring methods, with
  `load_registered_vocabulary` to read them and `value_status` to classify a value as known,
  unknown or invalid.
- `LoquiturSchemasError`, a base of every exception the package defines; each keeps its
  built-in base.
- The command `loquitur-schema-validate`, also run as `python -m loquitur.schemas`, and the
  modules `python -m loquitur.schemas.typescript` (declaration generator) and
  `python -m loquitur.schemas.compatibility` (a compatibility gate for CI).
