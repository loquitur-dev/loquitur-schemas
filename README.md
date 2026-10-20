# loquitur-schemas

The repository name carries no suffix because it is the Python reference package of the protocol
data and primitives: `loquitur-schemas` is the implementation, and the normative schemas are in
`loquitur-protocol`.

`loquitur-schemas` is the Python package that carries the JSON Schemas of the Loquitur
protocol: the formal descriptions of the public records the protocol defines, such as a
verification receipt, a registry entry and a trust registry. A program uses it to check that a
document has the shape the protocol requires, to compute the digests the protocol defines for a
registry entry, and to build the exact bytes a signer signs. It checks form, not truth: a
document that validates is well formed, which says nothing about whether what it states is
correct.

> **Status: preview, version 0.1.0 (Alpha).** The package is not production-ready, not for use
> with real assets, and not a stable public API commitment: names and behavior can change in
> any 0.x release. It is not yet published to a package index and installs from a checkout of
> this repository. No independent cryptographic review of this protocol or its reference
> verifiers has been done yet. The protocol's [preview limitations][preview-limitations] list
> what this preview does not provide.

## Start here

- **You rely on a verdict, or review the risk of relying on one.** This package checks the form
  of documents and decides no verdict. The protocol's [`threat-model.md`][threat-model] states
  what a verdict asserts (section 2) and the assumptions, residual risks and tasks that stay
  with a relying party (sections 8 to 10).
- **You integrate the package.** Read "Install", "Validate a JSON document" and "Use from
  Python" below.
- **You review its security.** Read [`SECURITY.md`][security], the threat model,
  [`cryptographic-capabilities.md`][cryptographic-capabilities] and
  [`conformance-testing.md`][conformance-testing].

## What it does not include

Loquitur governs the evidence behind a valuation; it does not compute valuations. The package
has:

- no service, route or runtime of any implementation, and no OpenAPI artifact;
- no valuation computation, KYC or AML, custody, oracle or data transport, or tokenization;
- no function that takes a private key, makes a signature or calls a key-management service:
  it builds the exact bytes a signer signs, and signing is left to a separate tool;
- no Merkle-tree or transparency-log module: the specification defines no tree-head format,
  log identifier, checkpoint or inclusion proof, and nothing here commits the protocol to
  shipping them.

## Install

<!-- lq-include: installation -->
The package installs from a checkout of the `loquitur-schemas` repository. It needs Python 3.11
or later. From the directory that contains the checkout:

```bash
python -m pip install ./loquitur-schemas
```

That is all the package needs. It has no optional install for normal use, and importing it
pulls in no web framework, no test runner and no schema-validation library.

To check the install:

```bash
loquitur-schema-validate --version
```

It prints `loquitur-schemas 0.1.0`.
<!-- lq-include-end: installation -->

`python -m loquitur.schemas` runs the same command. The package installs this one command; the
generator and the compatibility gate below run as modules.

The examples below that name `tests/fixtures/...` read files of the checkout, which the wheel
and the sdist do not contain.

## List bundled schemas

<!-- lq-include: list-bundled-schemas -->
```bash
loquitur-schema-validate list
```

The output names the seven bundled schemas:

- `verification_summary.schema.json`, `verification_receipt.schema.json`,
  `change_summary.schema.json`, `lineage_summary.schema.json` and
  `coverage_summary.schema.json`, the canonical protocol objects;
- `registry_entry.schema.json` and `trust_registry.schema.json`, the registry commitment
  objects.

The registry entry schema is minimal on purpose. It describes a public commitment, not a
disclosure of evidence: it holds no raw evidence, canonical inputs, asset addresses,
valuation or NAV amounts, financial metrics, tenant or investor data, or other
business-sensitive fields.
<!-- lq-include-end: list-bundled-schemas -->

## Validate a JSON document

<!-- lq-include: validate-a-json-document -->
The examples validate the fixtures in the repository's `tests/fixtures/`, so run them from the
checkout:

```bash
cd loquitur-schemas
```

Validate by schema filename:

```bash
loquitur-schema-validate validate verification_summary.schema.json tests/fixtures/verification_summary.valid.json
loquitur-schema-validate validate registry_entry.schema.json tests/fixtures/registry_entry.valid.json
loquitur-schema-validate validate trust_registry.schema.json tests/fixtures/trust_registry.valid.json
```

Validate by `object_type` alias:

```bash
loquitur-schema-validate validate verification_summary tests/fixtures/verification_summary.valid.json
loquitur-schema-validate validate registry_entry tests/fixtures/registry_entry.valid.json
loquitur-schema-validate validate trust_registry tests/fixtures/trust_registry.valid.json
```

Machine-readable output:

```bash
loquitur-schema-validate validate registry_entry tests/fixtures/registry_entry.valid.json --json
```

Exit codes:

- `0`: the document validates against the selected bundled schema;
- `1`: the document is valid JSON but violates the schema, or holds an instant that names no
  calendar second, such as `2026-02-30T00:00:00Z`;
- `64`: a usage or setup error, such as an unknown option or subcommand, a missing argument,
  no subcommand, a missing or unreadable file, invalid JSON, an unknown schema or an
  unsupported object type. The message is on stderr.

`--help` and `--version` exit `0`.
<!-- lq-include-end: validate-a-json-document -->

## Use from Python

Everything the commands do is importable from `loquitur.schemas`, which is typed (`py.typed`).
Run from the checkout, this validates a registry entry and computes its two digests:

```python
import json
from pathlib import Path

from loquitur.schemas import (
    registry_entry_hash,
    registry_entry_signing_payload_hash,
    validate_instance,
)

entry = json.loads(Path("tests/fixtures/registry_entry.valid.json").read_text(encoding="utf-8"))

result = validate_instance("registry_entry", entry)
assert result.ok
for error in result.errors:  # empty when the entry is valid
    print(error.path, error.code, error.message)

print(registry_entry_hash(entry))  # SHA-256 URI of the entry's RFC 8785 bytes, as given
print(registry_entry_signing_payload_hash(entry))  # SHA-256 URI of the exact bytes a signer signs
```

`validate_instance` takes a schema filename or an `object_type`, as the command does, and
returns a `ValidationResult`.

`canonicalize_registry_entry_signing_payload(entry)` returns the signing-message bytes
themselves, `registry_entry_signing_payload_v2`: a fixed binary domain prefix followed by the
RFC 8785 canonical encoding of a closed signing envelope (`signing-envelope-v2.md` in the
specification). The protocol defines no earlier signing payload, so a signature object without
`payload_id` and `payload_version` breaks the registry entry's contract.

### The trust-registry root signature

A trust registry is authenticated by a signature of a root key distributed out of band
(`trust-root.md` in the specification). The message that signature covers is built like the
registry-entry one, from a trust registry given as a mapping, and nothing here signs or
verifies:

- `trust_registry_signing_payload(trust_registry)` returns every member except `signature`;
- `trust_registry_signing_envelope(trust_registry)` returns the closed, domain-separated
  envelope around that payload;
- `trust_registry_signing_bytes(trust_registry)` returns the exact bytes a root key signs: a
  fixed binary domain prefix followed by the RFC 8785 encoding of the envelope.

They are exported from `loquitur.schemas` and defined in `loquitur.schemas.trust_root`, which
also defines `TrustRootError`, raised for a trust registry that is not an object.

### Reading and checking input

The helpers a producer needs before it validates or signs a document are exported too; the
package API is still provisional before 1.0.

- `load_json_document(path)` reads a JSON file under the protocol's input strictness and raises
  `SchemaValidationUsageError` for a file that is missing, unreadable or not strict JSON.
- `input_strictness_violation(value)` returns the strictness rule an in-memory JSON value
  breaks, or `None`.
- `is_calendar_instant(value)` tells whether a value is `YYYY-MM-DDTHH:MM:SSZ` naming a real
  UTC second.
- `calendar_instant_errors(schema_or_object_type, instance)` returns an error for every string
  the schema holds to the instant pattern that names no real second.

## Generate TypeScript declarations

```bash
python -m loquitur.schemas.typescript
python -m loquitur.schemas.typescript --output loquitur-protocol.d.ts
```

Without `--output`, or with `--output -`, the declarations go to stdout. The command exits `0`
when the declarations are written and `64` on a usage error or an output path it cannot write.
The repository keeps a reference copy at `src/loquitur/schemas/types/loquitur-protocol.d.ts`,
and the tests hold it to the generator. The declarations describe the schemas; they are not a
TypeScript SDK.

## Check schema compatibility

```bash
python -m loquitur.schemas.compatibility
python -m loquitur.schemas.compatibility --json
```

The command compares the bundled schemas, or those under `--current-schema-root`, with the
bundled `public_canonical_v0_1_0` baseline, for use as a CI gate when a schema changes. It
exits `0` when nothing breaks compatibility, `1` when a change does, and `64` on a usage error
or a file it cannot read. `--allow-breaking` turns a breaking change into exit `0` only together
with `--changelog` naming a non-empty changelog file.

## Reason-code catalog

The package bundles the reason-code catalog: every code of the `loquitur.reason_codes.v1`
vocabulary with its narrative templates for technical, compliance and executive readers. A
verifier composes its narrative from these templates alone, so the wording it prints can be
reproduced from the catalog and the verification report.

## Exceptions

Every exception this package defines derives from `loquitur.schemas.LoquiturSchemasError`, so
`except LoquiturSchemasError` catches them all and nothing raised by a library underneath. Each
keeps the built-in base it had before, `ValueError` for most and `FileNotFoundError` for
`SchemaNotFoundError`, so a handler written for that base keeps working.

## Validator scope

The validator covers the JSON Schema keywords the bundled schemas use. It is not a
general-purpose Draft 2020-12 implementation. The root keyword `example` of each schema is not
a Draft 2020-12 keyword: the protocol declares it a non-validating annotation, and the validator
ignores it.

On top of the schemas it applies one rule that JSON Schema cannot express, input strictness rule
8 of the protocol: a string a schema holds to the instant form `YYYY-MM-DDTHH:MM:SSZ` must name
a real UTC second. The instant pattern admits `2026-02-30T00:00:00Z`, `2026-04-29T12:00:60Z` and
`0000-01-01T00:00:00Z`; the validator reports each as a `calendar_instant` error, as the
verifiers refuse such a document at load and the signing-message functions refuse to build a
message over it.

## Verdict vocabularies

Two verdict vocabularies exist, and they are kept apart:

- `verification_receipt.status` and `verification_summary.status` carry the same closed,
  enum-constrained lowercase vocabulary, `pass | warning | review | fail`, and the
  receipt status is not a free string. Producers and consumers must reject any other value.
  Every status maps to a registry verdict, so `STATUS_TO_REGISTRY_VERDICT` is total and a
  consumer never handles a null. There is no fifth value: a verdict cites the reason codes it
  rests on (change proposal LCP-0008 in `docs/change-proposals.md` of `loquitur-protocol`),
  and the cases in which verification cannot run carry reason codes of severity `review`.
- `registry_entry.verdict` carries the uppercase public commitment vocabulary
  `PASS | WARN | REVIEW | FAIL`, enum-constrained by the registry schema.

A verifier maps each receipt status onto its registry verdict before comparing the two. The
mapping is exact and total over the closed set; synonyms such as `ok`, `passed` or `success` are
not statuses and map to nothing. Compare mapped verdicts, never raw strings. The byte-level
rules of the related hash constructions are in `canonicalization-and-hashing.md` of the
specification.

## Version policy

Three version layers are distinct:

- the package version, for example `loquitur-schemas 0.1.0`;
- the object `schema_version`, `v2` for the five canonical schemas and `v1` for the registry
  schemas;
- the JSON Schema `title`, which is human-readable and carries no patch or format version.

## Compatibility

The package is pure Python and depends on `cryptography` and `rfc8785`. It requires Python
3.11 or later. CI runs on Linux with Python 3.11, 3.12, 3.13 and 3.14; the suite also
passes on Windows locally; CI does not run it there, and macOS is not tested.

## Relation to the specification

The specification of the Loquitur protocol lives in `loquitur-protocol`, which owns every
normative artifact this package carries: the seven schemas, the reason-code catalog and the
registered vocabularies here are byte-identical copies of its files, listed in its
`docs/specification/NORMATIVE_ARTIFACTS.json`, and the tests hold each copy to the protocol's.
Where the two differ, the protocol is right. The `$id` of a schema names the schema, not a
copy of it. The package is measured against the conformance corpus
`loquitur-conformance-bdbadee7f6144d08`, which the protocol repository carries as a
digest-pinned archive and which this repository consumes read-only;
[`CONFORMANCE_CONSUMER.json`][conformance-consumer] pins it by name, byte count and SHA-256.
The fixtures under `tests/` test this package and define no protocol expectation. The owner the
artifacts name, `loquitur-protocol-governance`, is a role defined in the protocol's
`GOVERNANCE.md`, not an organization: one person maintains the project. How to run the checks
is in [`docs/maintainers/testing.md`][testing].

## Links

- Specification: [`loquitur-protocol`][protocol], starting at [`introduction.md`][introduction]
- Security policy: [`SECURITY.md`][security]
- Contributing: [`CONTRIBUTING.md`][contributing]
- Changes: [`CHANGELOG.md`][changelog]
- License: `MIT OR Apache-2.0`, as "License" below states

## License

Licensed under either of

- the Apache License, Version 2.0 ([`LICENSE-APACHE`][license-apache]), or
- the MIT license ([`LICENSE-MIT`][license-mit]),

at your option. [`NOTICE`][notice] names the copyright holder.

Unless you explicitly state otherwise, any contribution intentionally submitted for inclusion in
this repository, as defined in the Apache License, Version 2.0, is dual licensed as above, without
any additional terms or conditions, and carries the Developer Certificate of Origin sign-off that
`CONTRIBUTING.md` describes.

[preview-limitations]: https://github.com/loquitur-dev/loquitur-protocol/blob/main/docs/preview-limitations.md
[threat-model]: https://github.com/loquitur-dev/loquitur-protocol/blob/main/docs/specification/threat-model.md
[cryptographic-capabilities]: https://github.com/loquitur-dev/loquitur-protocol/blob/main/docs/specification/cryptographic-capabilities.md
[conformance-testing]: https://github.com/loquitur-dev/loquitur-protocol/blob/main/docs/specification/conformance-testing.md
[introduction]: https://github.com/loquitur-dev/loquitur-protocol/blob/main/docs/specification/introduction.md
[protocol]: https://github.com/loquitur-dev/loquitur-protocol
[security]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/SECURITY.md
[contributing]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/CONTRIBUTING.md
[changelog]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/CHANGELOG.md
[conformance-consumer]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/CONFORMANCE_CONSUMER.json
[testing]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/docs/maintainers/testing.md
[license-apache]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/LICENSE-APACHE
[license-mit]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/LICENSE-MIT
[notice]: https://github.com/loquitur-dev/loquitur-schemas/blob/main/NOTICE
