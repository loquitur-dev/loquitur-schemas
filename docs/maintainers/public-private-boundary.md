# Public/private boundary

`loquitur-schemas` contains public protocol schema contracts and schema tooling only.

Allowed:

- the public canonical object schemas;
- the public registry commitment schema;
- the trust registry schema;
- the public reason-code catalog and the registered vocabularies;
- validation and compatibility helpers;
- public fixtures for the package's own tests.

Forbidden:

- raw private bundle data;
- canonical input payloads;
- valuation or NAV amounts;
- cap rate, NOI, IRR, LTV, vacancy or other workflow-sensitive financial fields;
- document names or document hashes not part of the public schema contract;
- storage, download or evidence URLs;
- internal request contexts;
- private signing keys, without exception and with no carve-out for a test location: a key
  written into a tree can be read out of that tree, so no location in it quarantines anything.
  Test keys are generated in memory for each run and never written, so the rule needs no
  exception;
- routes, framework details or implementation internals of an unpublished repository.

The package may validate or describe public commitment objects. It does not imply legal
ownership, valuation correctness, regulatory compliance, chain finality, audit certification,
production registry status or oracle identity.
