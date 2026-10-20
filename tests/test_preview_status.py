from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_package_metadata_is_a_controlled_alpha_preview_not_production() -> None:
    project = _pyproject()["project"]
    assert project["name"] == "loquitur-schemas"
    assert project["version"] == "0.1.0"
    # The description is the PyPI Summary: it must describe the package, not gate it.
    assert "TestPyPI" not in project["description"]
    assert "Loquitur" in project["description"]
    classifiers = set(project["classifiers"])
    assert "Development Status :: 3 - Alpha" in classifiers
    assert "Development Status :: 4 - Beta" not in classifiers


def test_readme_status_is_conservative_and_not_publication_ready() -> None:
    # Read as running text: the status box is a block quote wrapped at 100 columns, and a
    # phrase may break across its lines.
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    text = " ".join(line.removeprefix(">").strip() for line in lines)
    # The substantive non-claims must stay: a package that stops saying
    # "not production-ready" has made a new claim.
    assert "not production-ready" in text
    assert "not for use with real assets" in text
    assert "not a stable public API commitment" in text
    assert "No independent cryptographic review" in text
    assert "publication-ready protocol package" not in text
    assert "pilot" not in text.lower()


def test_python_versions_in_metadata_are_the_ones_ci_runs() -> None:
    """The classifiers and the floor claim exactly the Python versions every CI job tests.

    A classifier is a claim on the project page, so a version CI does not run is a claim
    nothing checks, and a version CI runs without a classifier is support left unsaid.
    """
    project = _pyproject()["project"]
    claimed = sorted(
        (
            match.group(1)
            for classifier in project["classifiers"]
            if (match := re.fullmatch(r"Programming Language :: Python :: (3\.\d+)", classifier))
        ),
        key=lambda version: int(version.split(".")[1]),
    )
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    matrices = {
        name: job["strategy"]["matrix"]["python-version"]
        for name, job in workflow["jobs"].items()
        if "python-version" in job.get("strategy", {}).get("matrix", {})
    }
    assert matrices, "ci.yml declares no Python matrix, so this test would check nothing"
    for name, matrix in matrices.items():
        assert matrix == claimed, f"the CI job {name} runs {matrix}, the classifiers claim {claimed}"
    assert project["requires-python"] == f">={claimed[0]}"
