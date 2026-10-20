#!/usr/bin/env python3
"""The checks before a release of loquitur-schemas, and the build of its files.

.github/workflows/release.yml runs it, and it runs the same way on a maintainer's machine for
a dry run. It publishes nothing: it reads the tree, builds into a directory and writes a
checksum file there.

    python tools/release_build.py version
    python tools/release_build.py preflight [--tag vX.Y.Z]
    python tools/release_build.py build --outdir DIR
    python tools/release_build.py sums DIR

`version` prints the package version. `preflight` checks that the package version is the
`__version__` of the package, that it has a section in CHANGELOG.md and, given a tag, that the
tag is `v` followed by that version. `build` builds the sdist and the wheel from a clean tree
and holds the wheel to `src/`. `sums` writes `SHA256SUMS` over every file in the directory, in
the format `sha256sum -c` reads.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_wheel_gate import REPRODUCIBLE_EPOCH, assert_wheel_matches_source, purge_build_tree  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIST_NAME = "loquitur_schemas"
SUMS_NAME = "SHA256SUMS"
# The module whose `__version__` the CLIs print, beside pyproject.toml's version.
PACKAGE_INIT = Path("src") / "loquitur" / "schemas" / "__init__.py"
# vX.Y.Z and nothing else: no prefix, no suffix, no leading zero.
TAG_PATTERN = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def package_version(root: Path = ROOT) -> str:
    """Return the version pyproject.toml declares."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not isinstance(version, str):
        raise TypeError("pyproject.toml declares no static version")
    return version


def module_version(root: Path = ROOT) -> str | None:
    """Return the `__version__` string PACKAGE_INIT assigns, or None when it assigns none.

    The module is parsed, not imported, so the tree under check is read and not whatever copy
    of the package an import would find.
    """
    path = root / PACKAGE_INIT
    if not path.is_file():
        return None
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (
            isinstance(node, ast.Assign)
            and [target.id for target in node.targets if isinstance(target, ast.Name)] == ["__version__"]
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return None


def changelog_section(version: str, root: Path = ROOT) -> str:
    """Return the body of the CHANGELOG section for `version`, or "" when there is none.

    The heading is exactly `## [X.Y.Z]`, or `## [X.Y.Z] - YYYY-MM-DD` with an ASCII hyphen, the
    dated form a published copy carries. Any other heading names no section.
    """
    heading = re.compile(rf"## \[{re.escape(version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?", re.ASCII)
    lines = (root / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if heading.fullmatch(line):
            body: list[str] = []
            for following in lines[index + 1 :]:
                if following.startswith("## "):
                    break
                body.append(following)
            return "\n".join(body).strip()
    return ""


def preflight(tag: str | None, root: Path = ROOT) -> list[str]:
    """Return what stops a release of this tree under `tag`; empty when nothing does."""
    problems: list[str] = []
    version = package_version(root)
    if not TAG_PATTERN.fullmatch(f"v{version}"):
        problems.append(f"pyproject.toml version {version!r} is not X.Y.Z")
    declared = module_version(root)
    if declared != version:
        problems.append(
            f"{PACKAGE_INIT.as_posix()} __version__ {declared!r} is not the pyproject.toml version {version!r}"
        )
    if not changelog_section(version, root):
        problems.append(f"CHANGELOG.md has no non-empty section headed '## [{version}]'")
    if tag is not None:
        if not TAG_PATTERN.fullmatch(tag):
            problems.append(f"tag {tag!r} is not vX.Y.Z")
        elif tag != f"v{version}":
            problems.append(f"tag {tag!r} does not name the package version {version!r}")
    return problems


def build(outdir: Path, root: Path = ROOT) -> list[Path]:
    """Build the sdist and the wheel into an empty `outdir`, from a clean tree.

    An `outdir` that exists and holds anything is refused, never emptied: a mistyped path, the
    repository root or a parent directory would otherwise be deleted. The build tree is purged
    first, as tools/local_wheel_gate.py does, so that nothing a previous build left in build/ or
    src/*.egg-info reaches a release file. The wheel is then held to src/ member for member.

    The build runs with the epoch and hash seed `local_wheel_gate.py --check-reproducible`
    builds with, so the wheel built here, in the release workflow or on a maintainer's machine,
    is the one that check rebuilds.
    """
    version = package_version(root)
    if outdir.exists() and (not outdir.is_dir() or any(outdir.iterdir())):
        raise RuntimeError(f"{outdir} is not an empty directory")
    outdir.mkdir(parents=True, exist_ok=True)
    purge_build_tree(root)
    subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(outdir)],
        cwd=root,
        env={**os.environ, "SOURCE_DATE_EPOCH": REPRODUCIBLE_EPOCH, "PYTHONHASHSEED": "0"},
        check=True,
    )
    built = sorted(path.name for path in outdir.iterdir())
    expected = sorted([f"{DIST_NAME}-{version}.tar.gz", f"{DIST_NAME}-{version}-py3-none-any.whl"])
    if built != expected:
        raise RuntimeError(f"expected {expected} in {outdir}, found {built}")
    wheel = outdir / f"{DIST_NAME}-{version}-py3-none-any.whl"
    assert_wheel_matches_source(wheel, root)
    return [outdir / name for name in expected]


def write_sums(directory: Path) -> Path:
    """Write SHA256SUMS over every file in `directory`, sorted by name.

    One line per file, `<hex digest>  <name>`, which is what `sha256sum -c SHA256SUMS` reads
    in that directory. A subdirectory is refused rather than skipped: a release file the sums
    do not cover would pass a check that never saw it.
    """
    entries = sorted(path for path in directory.iterdir() if path.name != SUMS_NAME)
    if not entries:
        raise RuntimeError(f"{directory} holds no file to sum")
    lines = []
    for path in entries:
        if not path.is_file():
            raise RuntimeError(f"{path} is not a regular file")
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    sums = directory / SUMS_NAME
    sums.write_text("".join(lines), encoding="utf-8", newline="\n")
    return sums


def main(argv: list[str] | None = None) -> int:
    # `__doc__` is None under -OO, which strips docstrings.
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="print the package version")
    check = commands.add_parser("preflight", help="check the versions, the CHANGELOG section and the tag")
    check.add_argument("--tag", default=None, help="the release tag, vX.Y.Z")
    make = commands.add_parser("build", help="build the sdist and the wheel from a clean tree")
    make.add_argument("--outdir", type=Path, required=True)
    sums = commands.add_parser("sums", help="write SHA256SUMS over every file in a directory")
    sums.add_argument("directory", type=Path)
    args = parser.parse_args(argv)

    if args.command == "version":
        print(package_version())
    elif args.command == "preflight":
        problems = preflight(args.tag)
        for problem in problems:
            print(f"release preflight: {problem}", file=sys.stderr)
        if problems:
            return 1
        print(f"release_preflight_ok version={package_version()} tag={args.tag or '-'}")
    elif args.command == "build":
        for path in build(args.outdir.resolve()):
            print(f"built {path.name}")
    else:
        print(f"wrote {write_sums(args.directory.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
