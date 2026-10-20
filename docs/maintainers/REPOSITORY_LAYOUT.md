# Repository layout

This repository holds the `loquitur-schemas` package and the files that check it. It holds no
server implementation, no TypeScript SDK and no verifier.

| Path | Purpose |
| --- | --- |
| `src/loquitur/schemas/` | Package source: the schema inventory, the validator, the canonicalization and digest functions, the registry-entry and trust-registry signing messages, the reason-code catalog loader, the registered-vocabulary loader and the TypeScript declaration generator. |
| `src/loquitur/schemas/data/` | The bundled JSON Schemas, the reason-code catalog and the registered vocabularies, byte for byte the files of `loquitur-protocol`. |
| `src/loquitur/schemas/types/` | The generated TypeScript declarations and their manifest. |
| `src/loquitur/schemas/compatibility_baselines/` | The baseline the compatibility check compares the schemas with. |
| `tests/` | The test suite and its fixtures. Neither is shipped in the wheel or the sdist. |
| `tools/local_wheel_gate.py` | Builds the wheel, holds it to `src/`, installs it in a clean environment and runs the installed command line. |
| `tools/release_build.py` | The release checks and build: the tag and CHANGELOG check, the sdist and wheel built from a clean tree, and `SHA256SUMS`. [`releasing.md`](releasing.md) describes its use. |
| `.github/workflows/ci.yml` | The checks of every push and pull request, also run by the release workflow. |
| `.github/workflows/release.yml` | The release workflow: for a pushed `vX.Y.Z` tag, it builds and attests the release files and creates a draft GitHub release. |
| `tools/check_public_boundary.py`, `tools/public_boundary.json` | The public-boundary check over every tracked file, and the data it reads. The checker is byte-identical across the published repositories; the JSON beside it differs per repository. |
| `pyproject.toml`, `MANIFEST.in` | Package metadata and the sdist contents. |
| `CONFORMANCE_CONSUMER.json`, `RELEASE_SET_POINTER.json` | The conformance-corpus pin and the release-set pointer. Both are governance files of `loquitur-protocol`: they are not shipped in the distribution, and the protocol's checks hold them, so a change is made there and in every copy together. |
| `docs/maintainers/` | This folder: documents for the person who maintains or changes the repository. |

## Twin modules

Six modules of this package have a counterpart in `loquitur-verify` (`loquitur.verify`):

| `loquitur.schemas` | `loquitur.verify` | What both hold |
| --- | --- | --- |
| `canonical` | `canonical` | RFC 8785 canonical bytes and the SHA-256 digest of a registry entry. |
| `signing_envelope` | `signing_envelope` | The registry-entry signing envelope v2 and its domain prefix. |
| `verdict_grounds` | `verdict_grounds` | The verdict-grounds rules VG-1 to VG-7 (the verifier applies VG-1 to VG-4 to a registry entry too). |
| `cryptographic_capabilities` | `cryptographic_capabilities` | The closed set of signature algorithms and key types. |
| `registered_vocabularies` | `registered_vocabularies` | The registered vocabularies of asset types, workflows and anchoring methods. |
| `trust_root` | `trust_root` | The constants of the trust-registry root signature message; the verifier also checks the signature, this package only builds the message. |

The duplication is deliberate. `loquitur-verify` must not import `loquitur-schemas` at run time:
a third party re-verifies a verdict with an implementation that shares no code with the one that
produced the document, and a verifier that borrowed these modules would inherit their defects.
The conformance corpus keeps the twins in step, running the same cases through both and holding
each to the rules the case declares. A change to a twin is therefore made in both repositories
together.

## Namespace

Never add `loquitur/__init__.py`: `loquitur` is a PEP 420 namespace shared with
`loquitur-verify` and future distributions, and only `loquitur/schemas/` belongs to this one.
A `loquitur/__init__.py` in any wheel would make the namespace a regular package owned by
whichever distribution installed last. `tests/test_namespace_package.py` holds the source tree
and a built wheel to the rule.

## Boundary

The package is a protocol-schema surface. It contains no server routes, no models of an
unpublished repository, no third-party material, no private bundle contents, no valuation
workflow logic, no secrets and no private signing keys.

The registry entry schema is minimal and public. It is a commitment surface, not an evidence
disclosure object.
