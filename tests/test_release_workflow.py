"""The release workflow keeps the release rules, and the release tool does what it says.

.github/workflows/release.yml runs only for a pushed vX.Y.Z tag or by hand, pins every action by
commit, grants each job only the permissions it needs, creates the GitHub release as a draft
and publishes to no package index. These tests read the workflows as GitHub reads them, parsed
as YAML, so a change that breaks a rule fails here before it reaches a tag, and a change of
layout alone does not.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"
CI = WORKFLOWS / "ci.yml"

sys.path.insert(0, str(ROOT / "tools"))

import release_build  # noqa: E402

# The tag comment after a pin is not part of the parsed document, so it is read from the text.
USES = re.compile(r"^\s*(?:- )?uses: (?P<ref>\S+)(?:\s+#\s*(?P<tag>\S+))?\s*$")
PINNED = re.compile(r"(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@(?P<sha>[0-9a-f]{40})")
PRIVATE_SKIP = "github.event_name == 'push' || !github.event.repository.private"
ATTESTING = "actions/attest@"

# The dry-run notice of the attest job, the same step in the four repositories: the last step of
# the job, after both attestations, under the opposite of their condition.
DRY_RUN_NOTICE = {
    "name": "Say that this dry run attested nothing",
    "if": "github.event_name != 'push' && github.event.repository.private",
    "run": 'echo "::notice::private repository, so this dry run built, summed and described the files and attested none"',
}

# The two reads of GitHub's API in the tag check. Each answer is kept in a variable, so that a
# failed call stops the run with its own error, and only then split at the tabs: bash checks the
# status of a command substitution and not that of a process substitution, so
# `read < <(gh api ...)` would take a failed call for an empty answer.
API_READ = re.compile(r"""^ *if ! (\w+)="\$\(gh api "([^"]+)" --jq '\[([^\]]+)\] \| @tsv'\)"; then$""", re.M)
API_READS = [
    ("ref", "repos/$GITHUB_REPOSITORY/git/ref/tags/$TAG", ".object.type, .object.sha"),
    (
        "tag",
        "repos/$GITHUB_REPOSITORY/git/tags/$tag_sha",
        ".object.type, .object.sha, .verification.verified, .verification.reason",
    ),
]
SPLITS = [
    "IFS=$'\\t' read -r ref_type tag_sha <<< \"$ref\"",
    "IFS=$'\\t' read -r target_type target_sha verified reason <<< \"$tag\"",
]

# `gh` and `git` as GitHub and the clone answer them: gh from STUB_REF and STUB_TAG (`fail` fails
# as gh does on a 404), git's default-branch question from STUB_ON_BRANCH.
TAG_STUBS = """
gh() {
  case "$2" in */git/ref/tags/*) answer="$STUB_REF" ;; *) answer="$STUB_TAG" ;; esac
  if [ "$answer" = fail ]; then echo "gh: Not Found (HTTP 404)" >&2; return 1; fi
  printf '%s\\n' "$answer"
}
git() { [ "$1" = merge-base ] && [ "$STUB_ON_BRANCH" = yes ]; }
"""
TAGGED = "c" * 40
RELEASABLE_TAG = {
    "TAG": "v0.1.0",
    "DEFAULT_BRANCH": "main",
    "GITHUB_REPOSITORY": "owner/repo",
    "GITHUB_SHA": TAGGED,
    "STUB_REF": "tag\t" + "a" * 40,
    "STUB_TAG": f"commit\t{TAGGED}\ttrue\tvalid",
    "STUB_ON_BRANCH": "yes",
}
TAG_REFUSALS = {
    "the ref cannot be read": ({"STUB_REF": "fail"}, "no answer for the ref of tag v0.1.0"),
    "a lightweight tag": ({"STUB_REF": f"commit\t{TAGGED}"}, "tag v0.1.0 is lightweight"),
    "a ref with no tag object": ({"STUB_REF": "\t"}, "names no tag object"),
    "the tag object cannot be read": ({"STUB_TAG": "fail"}, "no answer for the tag object"),
    "a tag of another commit": ({"STUB_TAG": f"commit\t{'d' * 40}\ttrue\tvalid"}, "not the commit this run builds"),
    "a tag of a tag": ({"STUB_TAG": f"tag\t{TAGGED}\ttrue\tvalid"}, "not the commit this run builds"),
    "an unverified signature": (
        {"STUB_TAG": f"commit\t{TAGGED}\tfalse\tunsigned"},
        "no signature GitHub verifies (unsigned)",
    ),
    "a commit off the default branch": ({"STUB_ON_BRANCH": "no"}, "not on main"),
}


def _load(path: Path = RELEASE) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path.name} is not a mapping"
    return document


def _triggers(document: dict[str, Any]) -> Any:
    # YAML 1.1 reads the bare key `on` as the boolean true.
    return document["on"] if "on" in document else document[True]


def _jobs(path: Path = RELEASE) -> dict[str, dict[str, Any]]:
    jobs = _load(path)["jobs"]
    assert jobs, f"{path.name} declares no job, so these tests would check nothing"
    return jobs


def _needs(job: dict[str, Any]) -> set[str]:
    needs = job.get("needs", [])
    return {needs} if isinstance(needs, str) else set(needs)


def _code(value: Any) -> str:
    """Everything a job or a document says, comments left out, as one lowercase text."""
    return yaml.safe_dump(value, width=1 << 16).lower()


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(step["run"] for step in job.get("steps", []) if "run" in step)


def test_runs_only_for_a_version_tag_or_by_hand() -> None:
    assert _triggers(_load()) == {"push": {"tags": ["v[0-9]+.[0-9]+.[0-9]+"]}, "workflow_dispatch": None}


def test_every_action_is_pinned_by_commit_and_the_same_commit_everywhere() -> None:
    pins: dict[str, set[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        jobs = _jobs(path)
        uses = [step["uses"] for job in jobs.values() for step in job.get("steps", []) if "uses" in step]
        called = [job["uses"] for job in jobs.values() if "uses" in job]
        assert all(ref == "./.github/workflows/ci.yml" for ref in called), called
        tags = {
            match.group("ref"): match.group("tag")
            for line in path.read_text(encoding="utf-8").splitlines()
            if (match := USES.match(line))
        }
        for ref in uses:
            pinned = PINNED.fullmatch(ref)
            assert pinned, f"{path.name}: {ref} is not pinned by a 40-hex commit SHA"
            tag = tags.get(ref)
            assert tag and re.fullmatch(r"v\d+(\.\d+)*", tag), f"{path.name}: {ref} carries no tag comment"
            pins.setdefault(pinned.group("action"), set()).add(f"{pinned.group('sha')} {tag}")
    assert "actions/attest" in pins, "release.yml attests nothing"
    drift = {action: sorted(found) for action, found in pins.items() if len(found) > 1}
    assert not drift, f"one action pinned to different commits: {drift}"


def test_each_job_declares_least_privilege_permissions() -> None:
    document = _load()
    assert document["permissions"] == {}, "the workflow-level permissions are not empty"
    text = RELEASE.read_text(encoding="utf-8")
    assert "write-all" not in text and "read-all" not in text
    granted = {name: job.get("permissions") for name, job in _jobs().items()}
    assert granted == {
        "ci": {"contents": "read"},
        "verify": {"contents": "read"},
        "build": {"contents": "read"},
        "attest": {"id-token": "write", "attestations": "write"},
        "release": {"contents": "write"},
    }


@pytest.mark.parametrize(
    "needle",
    [
        "gh-action-pypi-publish",
        "twine",
        "pypi.org",
        "npm publish",
        "npmjs",
        "gh release edit",
        "gh release upload",
        "--draft=false",
        "secrets.",
    ],
)
def test_no_step_publishes_to_a_package_index_or_publishes_the_release(needle: str) -> None:
    assert needle not in _code(_load()), f"release.yml contains {needle!r}"


def test_the_release_is_created_as_a_draft_for_a_pushed_tag_only() -> None:
    jobs = _jobs()
    creates = [
        (name, line.strip()) for name, job in jobs.items() for line in _runs(job).splitlines() if "gh release" in line
    ]
    assert creates == [("release", 'gh release create "$TAG" release-files/* \\')]
    release = _runs(jobs["release"])
    assert "--draft \\" in release
    assert "--verify-tag \\" in release
    assert jobs["release"]["if"] == "github.event_name == 'push'"


def test_the_tag_is_checked_first_and_the_ci_runs_before_the_build() -> None:
    jobs = _jobs()
    assert _needs(jobs["ci"]) == {"verify"}
    assert jobs["ci"]["uses"] == "./.github/workflows/ci.yml"
    assert "workflow_call" in _triggers(_load(CI))
    assert _needs(jobs["build"]) == {"ci", "verify"}
    assert _needs(jobs["attest"]) == {"verify", "build"}
    assert _needs(jobs["release"]) == {"attest"}
    assert "if" not in jobs["ci"], "a dry run must not skip the CI"


def test_the_tag_check_reads_the_api_and_compares_the_commit_being_released() -> None:
    verify = _runs(_jobs()["verify"])
    for needle in (
        'if [ "$target_type" != "commit" ] || [ "$target_sha" != "$GITHUB_SHA" ]; then',
        'if [ "$verified" != "true" ]; then',
        'if ! git merge-base --is-ancestor "$GITHUB_SHA" "refs/remotes/origin/$DEFAULT_BRANCH"; then',
        'python tools/release_build.py preflight --tag "$TAG"',
    ):
        assert needle in verify, needle
    steps = _jobs()["verify"]["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0, "the default-branch check needs the branches"
    check = next(step for step in steps if "merge-base" in step.get("run", ""))
    assert check["env"]["DEFAULT_BRANCH"] == "${{ github.event.repository.default_branch }}"


def test_a_dry_run_on_a_tag_is_refused_before_anything_else() -> None:
    """A dry run runs on a branch; a tag is released by pushing it."""
    first = _jobs()["verify"]["steps"][0]
    assert first["if"] == "github.event_name != 'push' && github.ref_type == 'tag'"
    assert first["run"].startswith('echo "::error::')
    assert first["run"].rstrip().endswith("exit 1")


def test_the_version_is_read_once_by_verify() -> None:
    jobs = _jobs()
    assert jobs["verify"]["outputs"] == {"version": "${{ steps.preflight.outputs.version }}"}
    text = _code(_load())
    assert text.count("release_build.py version") == 1
    # The build job outputs only the digests of what it built, never a version of its own.
    assert "steps.build.outputs.version" not in text and "needs.build.outputs.version" not in text
    for name in ("build", "attest"):
        assert "${{ needs.verify.outputs.version }}" in _code(jobs[name]), name


def test_every_release_file_is_attested() -> None:
    jobs = _jobs()
    build = _code(jobs["build"])
    assert "cyclonedx-bom==7.5.0" in build
    assert "python tools/release_build.py sums release-files" in build
    assert "name: release-files" in build
    # Both attestations are actions/attest; the inputs choose the mode. With `sbom-path` it
    # attests the SBOM, and with only a subject it attests the provenance.
    attest = [step for step in jobs["attest"]["steps"] if step.get("uses", "").startswith(ATTESTING)]
    [sbom] = [step for step in attest if "sbom-path" in step["with"]]
    [provenance] = [step for step in attest if "sbom-path" not in step["with"]]
    assert provenance["with"] == {"subject-path": "release-files/*"}
    assert sbom["with"]["sbom-path"] == "release-files/loquitur_schemas-${{ needs.verify.outputs.version }}.cdx.json"
    assert sbom["with"]["subject-path"].split() == ["release-files/*.whl", "release-files/*.tar.gz"]
    assert "sha256sum --strict -c SHA256SUMS" in _runs(jobs["attest"])
    attesting = [
        name
        for name, job in jobs.items()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith(ATTESTING)
    ]
    assert attesting == ["attest", "attest"], "an attestation step runs outside the attest job"


def test_the_signing_job_runs_no_code_of_the_repository_or_the_package_index() -> None:
    """The attest job holds the OIDC token, so it runs only shell builtins, coreutils and the pinned actions."""
    attest = _jobs()["attest"]
    used = [step["uses"].split("@")[0] for step in attest["steps"] if "uses" in step]
    assert used == ["actions/download-artifact", "actions/attest", "actions/attest"]
    code = _code(attest)
    for needle in (
        "checkout",
        "setup-",
        "pip install",
        "-m pip",
        "python",
        "npm",
        "npx",
        "release_build",
        "curl",
        "wget",
    ):
        assert needle not in code, f"the attest job runs {needle!r}"


def test_a_dry_run_in_a_private_repository_skips_attesting() -> None:
    for step in _attest_steps():
        if step.get("uses", "").startswith(ATTESTING):
            assert step.get("if") == PRIVATE_SKIP, f"no private-repository skip on {step['uses']}"


def _tag_check() -> dict[str, Any]:
    [tag] = [step for step in _jobs()["verify"]["steps"] if "git/ref/tags/$TAG" in step.get("run", "")]
    return tag


def _attest_steps() -> list[dict[str, Any]]:
    return _jobs()["attest"]["steps"]


def test_the_tag_check_keeps_each_api_answer_before_it_reads_it() -> None:
    run = _tag_check()["run"]
    assert API_READ.findall(run) == API_READS
    code = [line for line in run.splitlines() if not line.lstrip().startswith("#")]
    assert sum(line.count("gh api") for line in code) == 2 and not [line for line in code if "< <(" in line]
    for split in SPLITS:
        assert split in run, split


def _not_posix(found: str | None) -> bool:
    """Whether ``found`` is no POSIX program: absent, or on Windows one of System32 or WindowsApps.

    There ``bash`` is the WSL launcher, which runs in another file system, and ``find`` and
    ``sort`` are Windows commands that take other arguments.
    """
    return found is None or (sys.platform == "win32" and Path(found).parent.name.lower() in {"windowsapps", "system32"})


def _run_bash(
    text: str, script: Path, cwd: Path, env: dict[str, str], tools: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """``text`` written to ``script`` and run in ``cwd`` as the runner runs a bash step, with ``env``.

    The ``tools`` the script runs are the ones beside bash, which on Windows are not the first of
    those names on the PATH: the directory of bash's own tools goes first, which for Git for
    Windows is its usr/bin and not the bin its bash may be found in. Without a POSIX bash, or
    without one of ``tools`` there, the test skips.
    """
    bash = shutil.which("bash")
    if _not_posix(bash):
        pytest.skip("no POSIX bash on this host to run the workflow's steps with")
    assert bash is not None
    beside = Path(bash).parent
    if sys.platform == "win32" and (beside.parent / "usr" / "bin").is_dir():
        beside = beside.parent / "usr" / "bin"
    path = str(beside) + os.pathsep + os.environ.get("PATH", "")
    missing = [tool for tool in tools if _not_posix(shutil.which(tool, path=path))]
    if missing:
        pytest.skip(f"no POSIX {', '.join(missing)} beside bash on this host to run the workflow's steps with")
    script.write_text(text, encoding="utf-8", newline="\n")
    return subprocess.run(
        [bash, "--noprofile", "--norc", "-eo", "pipefail", script.as_posix()],
        cwd=cwd,
        env={**os.environ, "PATH": path, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def _run_tag_check(env: dict[str, str], where: Path) -> subprocess.CompletedProcess[str]:
    return _run_bash(TAG_STUBS + _tag_check()["run"], where / "tag-check.sh", where, env)


def test_the_tag_check_passes_a_releasable_tag(tmp_path: Path) -> None:
    run = _run_tag_check(RELEASABLE_TAG, tmp_path)
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert "::error::" not in run.stdout and "annotated, signed and verified" in run.stdout


@pytest.mark.parametrize("case", sorted(TAG_REFUSALS))
def test_the_tag_check_ends_every_refusal_with_its_own_error(case: str, tmp_path: Path) -> None:
    change, refusal = TAG_REFUSALS[case]
    run = _run_tag_check({**RELEASABLE_TAG, **change}, tmp_path)
    assert run.returncode == 1, (case, run.stdout, run.stderr)
    assert run.stdout.startswith("::error::") and refusal in run.stdout, (case, run.stdout)


def test_a_dry_run_that_attests_nothing_says_so_in_its_last_step() -> None:
    steps = _attest_steps()
    guard = "github.event_name == 'push' || !github.event.repository.private"
    assert [step.get("if") for step in steps[-3:-1]] == [guard, guard]
    assert all(step["uses"].startswith(ATTESTING) for step in steps[-3:-1])
    assert steps[-1] == DRY_RUN_NOTICE


def test_preflight_accepts_the_tag_of_the_package_version() -> None:
    version = release_build.package_version()
    assert release_build.preflight(None) == []
    assert release_build.preflight(f"v{version}") == []
    assert release_build.changelog_section(version)


@pytest.mark.parametrize("tag", ["v9.9.9", "0.1.0", "v0.1", "v0.1.0-rc1", "v00.1.0", "V0.1.0", "v0.1.0 "])
def test_preflight_refuses_another_tag(tag: str) -> None:
    assert release_build.preflight(tag)


def _versioned(tmp_path: Path, version: str = "9.9.9", module: str = "9.9.9") -> Path:
    """A tree whose pyproject.toml declares `version` and whose package `__version__` is `module`."""
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    init = tmp_path / release_build.PACKAGE_INIT
    init.parent.mkdir(parents=True, exist_ok=True)
    init.write_text(f'"""The package."""\n\n__version__ = "{module}"\n', encoding="utf-8")
    return tmp_path


def _tree(tmp_path: Path, heading: str) -> Path:
    """A tree of version 9.9.9 whose CHANGELOG opens with `heading` over one entry."""
    _versioned(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        f"# changelog\n\n{heading}\n\n- something\n\n## [9.9.8]\n\n- older\n", encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize("heading", ["## [9.9.9]", "## [9.9.9] - 2026-10-05"])
def test_preflight_accepts_the_plain_and_the_dated_heading(tmp_path: Path, heading: str) -> None:
    root = _tree(tmp_path, heading)
    assert release_build.preflight("v9.9.9", root) == []
    assert release_build.changelog_section("9.9.9", root) == "- something"


@pytest.mark.parametrize(
    "heading",
    [
        "## [9.9.9]rc",
        "## [9.9.9] — 2026-10-05",
        "## [9.9.9] - 2026-10-5",
        "## [9.9.9] ",
        "## [9.9.9.1]",
        # A date in other digits than ASCII ones: Arabic-Indic, then full-width.
        "## [9.9.9] - ٢٠٢٦-١٠-١٧",
        "## [9.9.9] - ２０２６-１０-１７",
    ],
)
def test_preflight_refuses_any_other_heading(tmp_path: Path, heading: str) -> None:
    root = _tree(tmp_path, heading)
    assert release_build.changelog_section("9.9.9", root) == ""
    assert release_build.preflight("v9.9.9", root) == ["CHANGELOG.md has no non-empty section headed '## [9.9.9]'"]


@pytest.mark.parametrize("heading", ["## [9.9.9]", "## [9.9.9] - 2026-10-05"])
def test_preflight_refuses_a_changelog_section_with_no_text(tmp_path: Path, heading: str) -> None:
    _versioned(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(f"# changelog\n\n{heading}\n\n\n## [9.9.8]\n\n- older\n", encoding="utf-8")
    assert release_build.preflight("v9.9.9", tmp_path) == ["CHANGELOG.md has no non-empty section headed '## [9.9.9]'"]


def test_preflight_refuses_a_version_without_a_changelog_section(tmp_path: Path) -> None:
    _versioned(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# changelog\n\n## [9.9.8]\n\n- something\n", encoding="utf-8")
    assert release_build.preflight("v9.9.9", tmp_path) == ["CHANGELOG.md has no non-empty section headed '## [9.9.9]'"]


@pytest.mark.parametrize("module", ["9.9.8", "9.9.9.dev0", None], ids=["older", "suffixed", "absent"])
def test_preflight_refuses_a_package_version_other_than_pyproject_s(tmp_path: Path, module: str | None) -> None:
    """The CLIs print `__version__`, so a release whose module says another version is refused."""
    root = _tree(tmp_path, "## [9.9.9]")
    init = root / release_build.PACKAGE_INIT
    if module is None:
        init.write_text('"""The package."""\n', encoding="utf-8")
    else:
        _versioned(root, module=module)
    assert release_build.preflight("v9.9.9", root) == [
        f"src/loquitur/schemas/__init__.py __version__ {module!r} is not the pyproject.toml version '9.9.9'"
    ]


def test_the_tool_runs_without_its_docstring() -> None:
    """Under -OO, which strips docstrings, the tool still builds its parser and runs."""
    run = subprocess.run(
        [sys.executable, "-OO", str(ROOT / "tools" / "release_build.py"), "version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert (run.returncode, run.stdout.strip()) == (0, release_build.package_version()), run.stderr


def test_the_package_version_is_read_from_the_tree() -> None:
    assert release_build.module_version() == release_build.package_version()


def test_sums_cover_every_file_in_sha256sum_format(tmp_path: Path) -> None:
    (tmp_path / "a.whl").write_bytes(b"wheel")
    (tmp_path / "b.tar.gz").write_bytes(b"sdist")
    sums = release_build.write_sums(tmp_path)
    assert (
        sums.read_bytes()
        == (
            f"{hashlib.sha256(b'wheel').hexdigest()}  a.whl\n{hashlib.sha256(b'sdist').hexdigest()}  b.tar.gz\n"
        ).encode()
    )


def test_sha256sum_checks_the_sums_written(tmp_path: Path) -> None:
    """The workflow checks SHA256SUMS with `sha256sum --strict -c`; this runs the same check."""
    sha256sum = shutil.which("sha256sum")
    if sha256sum is None:
        pytest.skip("sha256sum is not on PATH, so the format test above is the only check here")
    (tmp_path / "a.whl").write_bytes(b"wheel")
    (tmp_path / "b.tar.gz").write_bytes(b"sdist")
    release_build.write_sums(tmp_path)

    def check() -> subprocess.CompletedProcess[str]:
        command = [sha256sum, "--strict", "-c", "SHA256SUMS"]
        return subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)

    result = check()
    assert result.returncode == 0, result.stdout + result.stderr
    (tmp_path / "a.whl").write_bytes(b"other")
    assert check().returncode != 0


@pytest.mark.parametrize("occupant", ["file", "directory"])
def test_build_refuses_an_outdir_that_holds_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, occupant: str
) -> None:
    """A mistyped --outdir, the repository root or a parent is refused, and nothing in it is deleted."""
    (tmp_path / "tree").mkdir()
    root = _tree(tmp_path / "tree", "## [9.9.9]")
    outdir = tmp_path / "out"
    if occupant == "file":
        outdir.mkdir()
        (outdir / "keep.txt").write_text("keep", encoding="utf-8")
    else:
        (outdir / "keep").mkdir(parents=True)

    def no_build(*args: object, **kwargs: object) -> None:
        raise AssertionError("the build ran over a directory that holds files")

    monkeypatch.setattr(release_build.subprocess, "run", no_build)
    with pytest.raises(RuntimeError, match="is not an empty directory"):
        release_build.build(outdir, root)
    assert (outdir / ("keep.txt" if occupant == "file" else "keep")).exists()


def test_a_local_dry_run_leaves_no_untracked_file() -> None:
    """The release files the documented dry run writes are ignored, so they never reach a commit."""
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout, so there is no ignore rule to ask about")
    version = release_build.package_version()
    for name in (
        f"loquitur_schemas-{version}.tar.gz",
        f"loquitur_schemas-{version}-py3-none-any.whl",
        f"loquitur_schemas-{version}.cdx.json",
        "SHA256SUMS",
    ):
        path = f"release-files/{name}"
        result = subprocess.run([git, "check-ignore", "-q", "--no-index", path], cwd=ROOT, check=False)
        assert result.returncode == 0, f"{path} is not ignored"


def test_the_security_policy_names_only_release_files_as_attached() -> None:
    """The release carries the files the build job writes; the attestations are not among them."""
    text = " ".join((ROOT / "SECURITY.md").read_text(encoding="utf-8").split())
    attaching = [sentence for sentence in re.split(r"(?<=[.;])\s", text) if "attaches" in sentence]
    assert attaching, "SECURITY.md no longer says what a release carries"
    for sentence in attaching:
        assert "attestation" not in sentence.lower(), sentence


def test_the_build_runs_with_the_gate_s_epoch_and_hash_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`build` fixes the epoch and hash seed the reproducibility gate rebuilds with, wherever it runs."""
    import local_wheel_gate

    class Built(Exception):
        pass

    seen: dict[str, Any] = {}

    def record(*args: object, **kwargs: Any) -> None:
        seen.update(kwargs)
        raise Built

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1")
    monkeypatch.setenv("PYTHONHASHSEED", "random")
    monkeypatch.setattr(release_build.subprocess, "run", record)
    (tmp_path / "tree").mkdir()
    with pytest.raises(Built):
        release_build.build(tmp_path / "out", _tree(tmp_path / "tree", "## [9.9.9]"))
    assert seen["env"]["SOURCE_DATE_EPOCH"] == local_wheel_gate.REPRODUCIBLE_EPOCH
    assert seen["env"]["PYTHONHASHSEED"] == "0"
    assert seen["env"]["PATH"] == os.environ["PATH"]


def test_the_released_wheel_is_the_one_the_reproducibility_gate_rebuilds() -> None:
    """The build job leaves the epoch to the build, and compares its wheel with the gate's."""
    build = _jobs()["build"]
    assert "env" not in build, "the build job sets an environment the build step does not need"
    assert "SOURCE_DATE_EPOCH" not in _runs(build), "a step sets its own epoch"
    runs = [step.get("run", "") for step in build["steps"]]
    built = next(i for i, run in enumerate(runs) if "release_build.py build --outdir release-files" in run)
    compared = next(i for i, run in enumerate(runs) if "local_wheel_gate.py --check-reproducible" in run)
    assert built < compared, "the reproducibility check runs before the wheel it checks is built"
    assert build["steps"][compared]["env"] == {"BUILT": "${{ steps.build.outputs.wheel-sha256 }}"}
    assert 'if [ -z "$printed" ] || [ "$printed" != "$BUILT" ]; then' in runs[compared]


DIGEST_LINES = [
    f'echo "{kind}-sha256=$(sha256sum -- "release-files/{name}" | cut -d \' \' -f 1)" >> "$GITHUB_OUTPUT"'
    for kind, name in (
        ("sdist", "loquitur_schemas-$VERSION.tar.gz"),
        ("wheel", "loquitur_schemas-$VERSION-py3-none-any.whl"),
    )
]


def test_the_build_step_takes_the_digests_before_any_other_code_runs() -> None:
    """The sdist and wheel digests are step outputs of the build step itself, which no later step can change."""
    build = _jobs()["build"]
    assert build["outputs"] == {
        "sdist-sha256": "${{ steps.build.outputs.sdist-sha256 }}",
        "wheel-sha256": "${{ steps.build.outputs.wheel-sha256 }}",
    }
    steps = build["steps"]
    [built] = [i for i, step in enumerate(steps) if "release_build.py build --outdir" in step.get("run", "")]
    assert steps[built]["id"] == "build"
    assert steps[built]["env"] == {"VERSION": "${{ needs.verify.outputs.version }}"}
    lines = [line.strip() for line in steps[built]["run"].splitlines()]
    assert lines[-3:] == ["python tools/release_build.py build --outdir release-files", *DIGEST_LINES]
    assert all("uses" in step for step in steps[:built]), "code of the repository runs before the build step"


ATTEST_HOLD = r"""if ! printf '%s  %s\n' "$SDIST_SHA256" "loquitur_schemas-$VERSION.tar.gz" \
  "$WHEEL_SHA256" "loquitur_schemas-$VERSION-py3-none-any.whl" | sha256sum --strict -c -; then"""


# The programs the attest check runs that are not bash builtins.
ATTEST_TOOLS = ("sort", "find", "cut", "sha256sum")


def _attest_check() -> dict[str, Any]:
    [check] = [step for step in _attest_steps() if "sha256sum --strict -c SHA256SUMS" in step.get("run", "")]
    return check


def test_the_attest_job_holds_the_sdist_and_the_wheel_to_the_build_step_digests() -> None:
    check = _attest_check()
    assert check["env"]["SDIST_SHA256"] == "${{ needs.build.outputs.sdist-sha256 }}"
    assert check["env"]["WHEEL_SHA256"] == "${{ needs.build.outputs.wheel-sha256 }}"
    run = check["run"]
    assert ATTEST_HOLD in run
    assert run.index("sha256sum --strict -c SHA256SUMS") < run.index(ATTEST_HOLD)


@pytest.mark.parametrize("rewritten", [None, "whl", "tar.gz"])
def test_the_attest_check_refuses_a_file_rewritten_after_the_build_step(tmp_path: Path, rewritten: str | None) -> None:
    """A file changed after the build step, with SHA256SUMS written over it, still fails the attest check."""
    files = tmp_path / "release-files"
    files.mkdir()
    names = {
        "whl": "loquitur_schemas-9.9.9-py3-none-any.whl",
        "tar.gz": "loquitur_schemas-9.9.9.tar.gz",
        "cdx.json": "loquitur_schemas-9.9.9.cdx.json",
    }
    for kind, name in names.items():
        (files / name).write_bytes(kind.encode())
    env = {
        "VERSION": "9.9.9",
        "SDIST_SHA256": hashlib.sha256(b"tar.gz").hexdigest(),
        "WHEEL_SHA256": hashlib.sha256(b"whl").hexdigest(),
    }
    if rewritten is not None:
        (files / names[rewritten]).write_bytes(b"rewritten after the build step")
    release_build.write_sums(files)
    # The script lies outside the directory it lists.
    run = _run_bash(_attest_check()["run"], tmp_path / "attest-check.sh", files, env, ATTEST_TOOLS)
    if rewritten is None:
        assert run.returncode == 0, (run.stdout, run.stderr)
    else:
        assert run.returncode == 1, (run.stdout, run.stderr)
        assert "::error::the sdist or the wheel is not the file the build step wrote" in run.stdout


@pytest.mark.parametrize("workflow", [CI, RELEASE], ids=lambda path: path.name)
def test_no_run_script_holds_an_expression(workflow: Path) -> None:
    """An expression in a run script is pasted into the shell before it runs; values reach scripts through env."""
    runs = [
        (name, step.get("name", "unnamed step"), step["run"])
        for name, job in _jobs(workflow).items()
        for step in job.get("steps", [])
        if "run" in step
    ]
    assert runs, f"{workflow.name} runs no script, so this test would check nothing"
    pasted = [f"{name}: {step}" for name, step, run in runs if "${{" in run]
    assert not pasted, f"{workflow.name}: expressions inside run scripts: {pasted}"


def test_the_ci_concurrency_group_cannot_collide_with_a_caller() -> None:
    """Called by release.yml, ci.yml sees the caller's workflow and ref; its prefix and the event keep it apart."""
    assert _load(CI)["concurrency"] == {
        "group": "ci-${{ github.workflow }}-${{ github.ref }}-${{ github.event_name }}",
        "cancel-in-progress": True,
    }


# `git` as GitHub answers the sibling probe: STUB_PROBE holds one `status|message` answer per
# attempt, separated by `;`, the last one repeated, and the file `attempts` counts the calls;
# `sleep` returns at once. Bash builtins only, so no tool beside bash is needed.
PROBE_STUBS = """
git() {
  local count=0 answers line
  if [ -f attempts ]; then read -r count < attempts; fi
  echo $((count + 1)) > attempts
  IFS=';' read -ra answers <<< "$STUB_PROBE"
  line="${answers[count < ${#answers[@]} ? count : ${#answers[@]} - 1]}"
  echo "${line#*|}" >&2
  return "${line%%|*}"
}
sleep() { :; }
"""
PROBE_READABLE = "0|"
PROBE_PRIVATE = "128|fatal: could not read Username for 'https://github.com': terminal prompts disabled"
PROBE_ABSENT = "128|remote: Repository not found.\nfatal: repository 'https://github.com/o/r.git/' not found"
PROBE_UNREACHABLE = {
    "no-name-resolution": "128|fatal: unable to access 'https://github.com/o/r.git/': Could not resolve host: github.com",
    "server-error": "128|fatal: unable to access 'https://github.com/o/r.git/': The requested URL returned error: 503",
    "rate-limited": "128|fatal: unable to access 'https://github.com/o/r.git/': The requested URL returned error: 403",
}


def _probe() -> dict[str, Any]:
    [probe] = [step for step in _jobs(CI)["siblings"]["steps"] if step.get("id") == "probe"]
    return probe


def _probed_siblings() -> list[str]:
    found = re.search(r"^ *for repo in ([a-z -]+); do$", _probe()["run"], re.M)
    assert found, "the probe names no sibling"
    return found[1].split()


def _run_probe(answers: str, ref_type: str, where: Path) -> tuple[subprocess.CompletedProcess[str], str, int]:
    """The probe step, run with git answering ``answers``: the run, its outputs and the attempts made."""
    output = where / "output"
    output.write_text("", encoding="utf-8")
    env = {"OWNER": "owner", "REF_TYPE": ref_type, "STUB_PROBE": answers, "GITHUB_OUTPUT": str(output)}
    run = _run_bash(PROBE_STUBS + _probe()["run"], where / "probe.sh", where, env)
    attempts = where / "attempts"
    count = int(attempts.read_text(encoding="utf-8")) if attempts.is_file() else 0
    return run, output.read_text(encoding="utf-8"), count


def test_the_probe_passes_the_ref_type_through_env() -> None:
    assert _probe()["env"]["REF_TYPE"] == "${{ github.ref_type }}"


@pytest.mark.parametrize("ref_type", ["branch", "tag"])
def test_the_probe_checks_out_every_readable_sibling(ref_type: str, tmp_path: Path) -> None:
    run, output, attempts = _run_probe(PROBE_READABLE, ref_type, tmp_path)
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert f"published={' '.join(_probed_siblings())}" in output.splitlines()
    assert attempts == len(_probed_siblings())


@pytest.mark.parametrize("answer", [PROBE_PRIVATE, PROBE_ABSENT, "2|"], ids=["private", "absent", "no-head"])
@pytest.mark.parametrize("ref_type", ["branch", "tag"])
def test_a_sibling_that_is_not_found_is_skipped_at_once_even_on_a_tag(
    ref_type: str, answer: str, tmp_path: Path
) -> None:
    run, output, attempts = _run_probe(answer, ref_type, tmp_path)
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert "published=" in output.splitlines() and "::" not in run.stdout
    assert attempts == len(_probed_siblings())


@pytest.mark.parametrize("answer", sorted(PROBE_UNREACHABLE.values()), ids=sorted(PROBE_UNREACHABLE))
def test_a_probe_failure_that_is_not_a_not_found_fails_a_run_on_a_tag(answer: str, tmp_path: Path) -> None:
    run, output, attempts = _run_probe(answer, "tag", tmp_path)
    assert run.returncode == 1, (run.stdout, run.stderr)
    assert f"::error::{_probed_siblings()[0]} could not be probed" in run.stdout
    assert attempts == 4 and output == ""


@pytest.mark.parametrize("answer", sorted(PROBE_UNREACHABLE.values()), ids=sorted(PROBE_UNREACHABLE))
def test_a_probe_failure_on_a_branch_warns_and_skips_the_sibling(answer: str, tmp_path: Path) -> None:
    run, output, attempts = _run_probe(answer, "branch", tmp_path)
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert run.stdout.count("::warning::") == len(_probed_siblings())
    assert "published=" in output.splitlines() and attempts == 4 * len(_probed_siblings())


def test_a_transient_probe_failure_is_asked_again(tmp_path: Path) -> None:
    run, output, attempts = _run_probe(PROBE_UNREACHABLE["server-error"] + ";" + PROBE_READABLE, "tag", tmp_path)
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert f"published={' '.join(_probed_siblings())}" in output.splitlines()
    assert attempts == len(_probed_siblings()) + 1
