# Security policy

**Repository:** `loquitur-schemas`, the schema package of the Loquitur protocol, in preview.

No independent cryptographic review of this protocol or its reference verifiers has been done yet.

## Supported versions

| Version | Security fixes |
| --- | --- |
| 0.1.x | on the default branch only |

This is a pre-1.0 preview with no security-supported release line. Fixes land on the default
branch and ship in the next release; no fix is backported.

## Scope

In scope, for this repository:

- the bundled schemas, the reason-code catalog and the registered vocabularies, where the
  package's copy differs from the protocol's or a schema admits a document the specification
  refuses;
- the validator, the canonicalization and digest functions, and the builders of the
  registry-entry signing message and the trust-registry root-signature message;
- the command-line tools, including a crash or hang on document content;
- the package build, the wheel and the sdist, including anything they ship that they should
  not;
- documentation wording that could cause unsafe integration or unsupported trust assumptions;
- disclosure of private evidence, credentials or private URLs through this repository.

Reported elsewhere:

- the rules themselves, including a gap or contradiction in the specification: `loquitur-protocol`;
- a verdict or report of a verifier: `loquitur-verify-py` or `loquitur-verify-ts`.

When in doubt, report here, and the maintainer takes the report to the repository it belongs
to. This repository does not by itself establish legal ownership, valuation correctness,
regulatory compliance, chain finality or the operation of any registry, and a report that it
does not is a correct reading of the documentation, not a finding.

## Verifying a release

Releases are built by `.github/workflows/release.yml`, which attaches the sdist, the wheel,
`SHA256SUMS` and a CycloneDX SBOM to each release it creates. It also attests every one of these
files; the attestations are not release files but are kept in the repository's attestation
store, where `gh attestation verify` reads them.
[`docs/maintainers/releasing.md`](docs/maintainers/releasing.md) says how to check the files and
their attestations.

## Do not disclose sensitive material

Do not include real issuer evidence, private bundles, private keys, credentials, tokens,
personal data or confidential third-party material in public issues, pull requests, discussions
or unencrypted reports.

## Reporting channel

**Use GitHub's private vulnerability reporting on this repository**: open the *Security*
tab and choose *Report a vulnerability*. The report is visible only to the maintainer, it
carries no address that can be scraped or spoofed, and it produces an advisory record with
a fixed identifier both sides can cite later. It is the primary channel and needs nothing
set up on your side.

If private reporting is unavailable to you, write to **security@loquitur.dev**. Keep the
details of the vulnerability out of the first message if you prefer: the maintainer replies
and agrees a private channel for them. Do not describe a vulnerability in a public issue.

## What to expect

- Acknowledgement within 5 working days.
- An assessment, including whether the maintainer considers it in scope, within 10 working
  days.
- Coordinated disclosure: the maintainer agrees a publication date with you first, and
  credits you unless you ask not to be credited.
- The maintainer aims to publish a fix and an advisory within 90 days of the day the report is
  received, and may agree a different date with you.

## Advisories and identifiers

A confirmed vulnerability is published as a GitHub security advisory on this repository,
which gives it a `GHSA-` identifier. For a vulnerability in a released version, the maintainer
also requests a CVE identifier through that advisory. The advisory names the affected and the
fixed versions, and the CHANGELOG entry of the fixing release lists it under "Security".
