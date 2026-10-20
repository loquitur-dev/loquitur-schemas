# Test ownership

This repository tests its own surface only.

## What its tests cover

- validation against the bundled schemas;
- the `registry_entry` and `trust_registry` schemas;
- the reason-code catalog and the registered vocabularies;
- the package build and the wheel gate;
- the public/private boundary of the tracked files and the fixtures.

## What they do not cover

- the runtime of any service;
- the verifiers, which `loquitur-verify-py` and `loquitur-verify-ts` test;
- OpenAPI contracts and SDK clients.

## Tests that read a sibling repository

Some tests compare this repository with `loquitur-protocol`, `loquitur-verify-py` and
`loquitur-verify-ts` checked out beside it; [`testing.md`](testing.md) gives the layout. Such a
test keeps the public/private boundary of the repository it reads and adds no claim about
production use, audits, legal truth, valuation correctness, compliance or chain finality.

How to run the checks is in [`testing.md`](testing.md).
