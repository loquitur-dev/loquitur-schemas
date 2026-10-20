# Governance

This repository is maintained by one person, the copyright holder `NOTICE` names; "the
maintainer" in its documents is that person, not a team.

The governance of the protocol is defined in `GOVERNANCE.md` of `loquitur-protocol`: how the
specification changes, the change-proposal register and the compatibility classes. This
repository follows it. A change to a schema, the reason-code catalog or a registered
vocabulary is made in `loquitur-protocol` first, and the copy here follows it in the same
release.

For the rest of this repository, the maintainer reviews every change that affects the public
API, the schemas, the generated declarations, the release artifacts, the security posture or a
public claim, and rejects a change that:

- moves code or documents of another repository into this one;
- exposes private evidence or material of an unpublished repository;
- claims production use, an audit, compliance, chain finality or valuation correctness;
- changes public behavior without tests and documentation.

How to contribute is in `CONTRIBUTING.md`.
