# Releasing

A release of `loquitur-schemas` is a signed, annotated tag `vX.Y.Z` and a GitHub release for it
that carries these files:

| File | What it is |
| --- | --- |
| `loquitur_schemas-X.Y.Z.tar.gz` | The sdist. |
| `loquitur_schemas-X.Y.Z-py3-none-any.whl` | The wheel. |
| `loquitur_schemas-X.Y.Z.cdx.json` | A CycloneDX SBOM of the wheel installed with its dependencies. |
| `SHA256SUMS` | The SHA-256 digest of each file above, in the format `sha256sum -c` reads. |

Each of the four has a GitHub artifact attestation of where it was built, and the sdist and the
wheel have an attestation that binds the SBOM to them.

The package is not yet published to a package index. Nothing in this repository uploads it to
one: see [Publishing to PyPI later](#publishing-to-pypi-later).

## Tag rules

- A release tag is `vX.Y.Z` and nothing else: no prefix, no suffix, no leading zero.
  `.github/workflows/release.yml` runs only for a tag of that form.
- It is annotated and signed with the maintainer's key:
  `git tag -s vX.Y.Z -m "loquitur-schemas X.Y.Z"`. The workflow refuses a lightweight tag and a
  tag whose signature GitHub does not verify, so the signing key must be registered as a signing
  key on the maintainer's GitHub account.
- It names a commit on the default branch.
- It names the version in `pyproject.toml`, which is also the package's `__version__`, and
  `CHANGELOG.md` has a section headed exactly `## [X.Y.Z]` or `## [X.Y.Z] - YYYY-MM-DD`.
- It is never moved and never deleted. A release that turns out wrong is followed by a new
  version, not by a tag pointing somewhere else.

## Settings the maintainer makes on GitHub

The workflow cannot set these, and this file does not show that they are set. They are the
maintainer's own settings:

- **Immutable releases**, in the repository settings: once a release is published, its tag
  and its files can no longer be changed or removed. A draft stays editable until it is
  published.
- **A tag ruleset** on `refs/tags/v*`: only the maintainer may create a matching tag, and
  updating or deleting one is blocked.
- **Two-factor authentication with a security key or passkey** (FIDO) on the maintainer's
  account.
- **No long-lived tokens.** The workflow uses only the `GITHUB_TOKEN` of its own run and the
  short-lived OIDC token the attestations need; it reads no repository secret. No personal
  access token is created for releasing.

## What the workflow does

`.github/workflows/release.yml` runs when a tag `vX.Y.Z` is pushed. Every action it uses is
pinned by commit SHA, the workflow grants no permission at the top level, and each job asks
only for what it needs.

1. **verify** (`contents: read`) runs `python tools/release_build.py preflight --tag vX.Y.Z`,
   which checks that the tag names the version in `pyproject.toml`, that the package's
   `__version__` is that version and that `CHANGELOG.md` has a section for it, and hands the
   version to the later jobs. It then asks the GitHub API whether the tag is annotated, whether
   it names the commit being built and whether its signature is verified, and checks that the
   commit is on the default branch. Every later job waits for it, so a bad tag stops the run
   here.
2. **ci** (`contents: read`) runs every job of `.github/workflows/ci.yml` on the tagged commit:
   the test suite on each supported Python, the sibling checks, the boundary check, the wheel
   gate, the sign-off check and the scan of the built files for key material. The sibling
   checks read loquitur-protocol, loquitur-verify-py and loquitur-verify-ts at the head of
   their default branches, not at a matching tag, so a release run depends on their state at
   the time it runs. A sibling check that fails on a tag is fixed in the sibling and the run is
   re-run; the tag is not moved.
3. **build** (`contents: read`) runs `python tools/release_build.py build`, which removes
   `build/` and `src/*.egg-info`, builds the sdist and the wheel with `python -m build`
   (build 1.6.1, setuptools 84.0.0) and holds the wheel to `src/` member for member, as
   `tools/local_wheel_gate.py` does. The same step records the SHA-256 of the sdist and of the
   wheel as step outputs, before any later step runs. The build runs with the epoch and hash
   seed `tools/local_wheel_gate.py` fixes for its reproducibility check, and the job checks that
   `tools/local_wheel_gate.py --check-reproducible` rebuilds the wheel to the same bytes. It
   installs the wheel into an empty environment, with the dependencies pip resolves for it, and
   writes the SBOM of that environment with `cyclonedx-py environment` (cyclonedx-bom 7.5.0).
   It writes `SHA256SUMS` and keeps the four files as the run artifact `release-files`. This job
   runs code from the package index (the build tools, the SBOM tool and their dependencies), so
   it holds no token that can sign an attestation or write to the repository.
4. **attest** (`id-token: write`, `attestations: write`) is the only job that can sign. It
   checks out nothing and installs nothing: it downloads `release-files`, checks that it holds
   exactly the four release files of the version, that `SHA256SUMS` lists the other three and
   that they match it (`sha256sum --strict -c`), and that the sdist and the wheel have the
   digests the build step recorded, so a file rewritten by code that ran after the build is
   refused even when `SHA256SUMS` was written over it. The SBOM is written by that later code,
   so only `SHA256SUMS` holds it. The job then uses `actions/attest` twice: a provenance
   attestation of every file, and an SBOM attestation that binds the SBOM to the sdist and the
   wheel.
5. **release** (`contents: write`) checks the files against `SHA256SUMS` and runs
   `gh release create vX.Y.Z --draft --verify-tag` with the files attached.

The release stays a draft. Reading it and publishing it is the maintainer's act.

### Dry run

Run the workflow by hand (*Actions*, *release*, *Run workflow*) on a branch. Jobs 1 to 4 run,
without the tag checks, and the files stay a run artifact; no release is created. A run by hand
on a tag is refused in the first step: a tag is released by pushing it.

In a public repository a dry run attests its files too: the attestations record a build of that
ref, not of a release tag, and GitHub keeps them, as does the public Sigstore transparency log.
The verification commands below require the release tag as the source ref, so an attestation
from a dry run, which runs on a branch, does not pass them.

GitHub offers artifact attestations on public repositories, and on private ones only with
GitHub Enterprise Cloud. In a private repository a dry run therefore skips the two attestation
steps and leaves a notice saying so; the build, the SBOM and the `SHA256SUMS` check still run. A
tag push never skips them, so a tag pushed while the repository is private fails at the attest
job and no release is created.

The same build runs locally:

```bash
python -m pip install build==1.6.1
python tools/release_build.py preflight --tag vX.Y.Z
python tools/release_build.py build --outdir release-files
python tools/release_build.py sums release-files
```

`release-files/` is in `.gitignore`, so the files it holds stay out of every commit. The build
refuses an output directory that holds anything, rather than emptying it: remove
`release-files/` before building again.

## Cutting a release

1. Set the version in `pyproject.toml` and the same version as `__version__` in
   `src/loquitur/schemas/__init__.py`, move the entries for it into a `## [X.Y.Z]` section of
   `CHANGELOG.md`, and land that on the default branch with CI green.
2. Tag that commit and push the tag:
   `git tag -s vX.Y.Z -m "loquitur-schemas X.Y.Z"`, `git push origin vX.Y.Z`.
3. When the workflow has finished, read the draft release, check its files as below, and
   publish it.

## Verifying a release

```bash
gh release download vX.Y.Z --repo loquitur-dev/loquitur-schemas --dir loquitur-schemas-X.Y.Z
cd loquitur-schemas-X.Y.Z
sha256sum --strict -c SHA256SUMS

repo=loquitur-dev/loquitur-schemas
pin="--repo $repo --signer-workflow $repo/.github/workflows/release.yml --source-ref refs/tags/vX.Y.Z --deny-self-hosted-runners"
for file in loquitur_schemas-X.Y.Z-py3-none-any.whl loquitur_schemas-X.Y.Z.tar.gz \
    loquitur_schemas-X.Y.Z.cdx.json SHA256SUMS; do
  gh attestation verify "$file" $pin
done
for file in loquitur_schemas-X.Y.Z-py3-none-any.whl loquitur_schemas-X.Y.Z.tar.gz; do
  gh attestation verify "$file" $pin --predicate-type https://cyclonedx.org/bom
done
```

`sha256sum --strict -c` checks that the files are the ones `SHA256SUMS` lists. Each
`gh attestation verify` line passes only for an attestation whose subject is the file's SHA-256
digest and that was signed by `.github/workflows/release.yml` of this repository, in a run for
the tag `vX.Y.Z`, on a GitHub-hosted runner. An attestation from a dry run of a branch, or from
another workflow of the repository, does not pass. The first loop checks the provenance of all
four files; the second checks that an SBOM attestation from that same workflow and tag names the
sdist and the wheel. `git verify-tag vX.Y.Z` checks the tag's signature in a clone, given the
maintainer's public key.

## What is not claimed

- An attestation says where and from what a file was built: this repository, this workflow,
  this commit. It says nothing about whether the file is correct, safe or fit for a purpose.
- No reproducible-build claim is made beyond what the workflow shows: a second build of the
  wheel on the same runner gives the same bytes. Nothing is claimed for a build on another
  machine, and nothing for the sdist.
- The SBOM lists the dependency versions pip resolved when the release was built. An
  installation made later may resolve others within the ranges in `pyproject.toml`.
- A green release workflow says that the checks in `ci.yml` passed on the tagged commit. It is
  not an audit. The maintainer's own testing, carried out with the help of AI tools, is
  internal verification and not an audit.

## Publishing to PyPI later

Uploading to PyPI is not enabled, and no job in the workflow does it. A release is a draft
until the maintainer publishes it, and a version uploaded to PyPI can never be replaced: an
upload job would turn a tag push into a publication that cannot be undone.

When the maintainer decides to publish to PyPI, the route is trusted publishing, with no API
token:

1. On PyPI, add a trusted publisher for the project: owner `loquitur-dev`, repository
   `loquitur-schemas`, workflow `release.yml`, environment `pypi`.
2. In the repository, create the environment `pypi` with the maintainer as required reviewer,
   so each upload waits for an approval.
3. Add a job that needs `release`, runs in the environment `pypi` with only `id-token: write`,
   downloads the `release-files` artifact, checks it against `SHA256SUMS`, and uploads the sdist
   and the wheel with `pypa/gh-action-pypi-publish` pinned by commit SHA. That action also
   uploads PEP 740 attestations to PyPI.
4. Update the tests in `tests/test_release_workflow.py`, which today refuse any upload step.
