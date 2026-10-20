# Testing

Run these checks from the `loquitur-schemas` repository root.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build
```

The wheel checks:

```bash
python tools/local_wheel_gate.py
python tools/local_wheel_gate.py --check-reproducible
```

`tools/local_wheel_gate.py` builds a wheel, requires it to match `src/`, installs it into a
temporary virtual environment and runs the installed command line against public fixtures. It
writes no `dist/` directory unless `--dist-dir` names one. With `--check-reproducible` it builds
the wheel twice instead, with `SOURCE_DATE_EPOCH` fixed to 1700000000, requires the two to be
byte-identical and prints `wheel_reproducible_ok sha256=...`. No reproducibility claim is made
for the sdist. The build backend is pinned exactly in `pyproject.toml` (`setuptools==84.0.0`),
and the byte identity holds for that backend: a new setuptools release does not move the
wheel's bytes.

Passing these checks says that the package behaves as its tests describe. It says nothing
about valuation correctness, compliance, chain finality or the operation of any registry, and
it is not an audit. The maintainer's own testing, carried out with the help of AI tools, is
internal verification and not an audit.

The workflows run on a pinned runner image (ubuntu-24.04), not on the moving ubuntu-latest label, so that the CI does not change when GitHub moves the label; the pin is moved deliberately, with a run on the new image.

CI also runs the linter and the type checker, each at a pinned version:

```bash
python -m pip install ruff==0.15.12 mypy==2.4.0
ruff check src tests
ruff format --check src tests
mypy
```

## Sibling repositories

The repository runs on its own. Some tests also compare it with the sibling repositories,
checked out beside it under their own names:

```text
<workspace>/
  loquitur-protocol/
  loquitur-schemas/
  loquitur-verify-py/
  loquitur-verify-ts/
```

A test that reads a sibling skips when the sibling is absent, and fails instead when
`LOQUITUR_REQUIRE_SIBLINGS=1` is set. No test depends on a sibling through a shared layout
that this page does not name.

Environment variables the suite reads:

| Variable | Effect |
| --- | --- |
| `LOQUITUR_REQUIRE_SIBLINGS=1` | The tests that compare this repository with `loquitur-protocol`, `loquitur-verify-py` and `loquitur-verify-ts`, checked out beside it, fail instead of skipping when a sibling is absent. |
| `LOQUITUR_REQUIRE_TSC=1` | The test that compiles the shipped TypeScript declarations fails instead of skipping when no `tsc` is on `PATH`. CI installs TypeScript 5.9.3. |

[`TEST_OWNERSHIP.md`](TEST_OWNERSHIP.md) says which surfaces these tests cover.
