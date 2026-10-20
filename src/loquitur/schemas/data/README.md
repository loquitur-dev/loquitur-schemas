# Loquitur public schema data

This package data directory bundles the public Loquitur protocol schemas that
`loquitur-schemas 0.1.0` ships.

The canonical URI identity base for bundled public schemas is:

```text
https://schemas.loquitur.dev/v1/
```

Each schema's `$id` is its filename under that base, for example
`https://schemas.loquitur.dev/v1/verification_summary.schema.json`.
These URIs are stable schema identities. They do not imply that production
registry infrastructure, live schema hosting, or a stable public API is available.

Included public schemas:

- `verification_summary.schema.json`
- `verification_receipt.schema.json`
- `change_summary.schema.json`
- `lineage_summary.schema.json`
- `coverage_summary.schema.json`
- `registry_entry.schema.json`
- `trust_registry.schema.json`

The schemas in this directory are public protocol contracts. They are not an implementation's
internal schemas and must not contain raw evidence, canonical inputs, asset addresses, valuation
or NAV amounts, or other confidential business data.

`registered_vocabularies/` holds the registered vocabularies of this release, byte for byte the
files of `loquitur-protocol`: `asset_type.json`, `workflow.json` and `anchoring_method.json`, and
`schema.json`, the schema a registered vocabulary document satisfies. The public schemas above hold
no asset type, workflow or anchoring method; these documents register them
(`verification-vocabularies.md` §5). `loquitur.schemas.load_registered_vocabulary` reads them.
