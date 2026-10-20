# Contributing to loquitur-schemas

`loquitur-schemas` is the schema package of the Loquitur protocol: the JSON Schemas, the
reason-code catalog, the registered vocabularies and the functions that read them. It is in
preview.

## Before a pull request

External contributions start with an issue. A pull request is welcome under the Developer
Certificate of Origin when it is tied to an issue the maintainer has accepted. A change to a
schema, the catalog or a registered vocabulary is a change to the protocol: it goes through the
change-proposal register of `loquitur-protocol`, `docs/change-proposals.md`, and lands there
before the copy here follows it.

Keep a contribution small and limited to this repository's surface. It states:

1. what part of the package changes;
2. whether any public claim changes;
3. what public/private boundary risk was considered;
4. what checks were run;
5. what remains unverified.

## Boundary rules

Do not add:

- private evidence bundles;
- real issuer material or confidential third-party material;
- credentials, tokens, headers, cookies, API keys or private URLs;
- claims of production readiness, compliance, audit, legal truth, chain finality or valuation
  correctness;
- service runtime behavior, website content, or the routes or internals of an unpublished
  repository.

## Running the checks

[`docs/maintainers/testing.md`](docs/maintainers/testing.md) gives the commands, the sibling
checkouts some tests compare against, and the environment variables the suite reads.

## Maintainer documents

These documents are for whoever maintains or changes the repository. They are not shipped in
the package.

- [`docs/maintainers/testing.md`](docs/maintainers/testing.md): how to run the checks.
- [`docs/maintainers/TEST_OWNERSHIP.md`](docs/maintainers/TEST_OWNERSHIP.md): what the tests
  cover and what they leave to other repositories.
- [`docs/maintainers/DOCS_OWNERSHIP.md`](docs/maintainers/DOCS_OWNERSHIP.md): what this
  repository documents.
- [`docs/maintainers/REPOSITORY_LAYOUT.md`](docs/maintainers/REPOSITORY_LAYOUT.md): what each
  path holds.
- [`docs/maintainers/public-private-boundary.md`](docs/maintainers/public-private-boundary.md):
  what may and may not be in the repository.
- [`docs/maintainers/releasing.md`](docs/maintainers/releasing.md): the tag rules, the release
  workflow and how a release is verified.

## Developer Certificate of Origin

Contributions are made under the Developer Certificate of Origin 1.1
(https://developercertificate.org/). Every commit, the maintainer's own included, carries a
sign-off line whose name and address match the commit's author, and CI checks every commit of
a push or pull request for it. `git commit -s` adds the line:

```
Signed-off-by: Your Name <your.email@example.com>
```

The sign-off certifies that the contributor wrote the change or otherwise has the right to
submit it under the project's licenses. There is no separate contributor agreement.

## License

The repository is licensed under either of the Apache License, Version 2.0
(`LICENSE-APACHE`) or the MIT license (`LICENSE-MIT`), at your option. `NOTICE` names the
copyright holder.

Unless you explicitly state otherwise, any contribution intentionally submitted for inclusion
in this repository, as defined in the Apache License, Version 2.0, is dual licensed as above,
without any additional terms or conditions. The Developer Certificate of Origin sign-off above
certifies your right to submit it under these licenses.
