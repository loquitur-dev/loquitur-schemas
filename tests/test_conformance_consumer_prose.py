"""The corpus this repository says it consumes, held to the corpus it pins.

``CONFORMANCE_CONSUMER.json`` pins the corpus by id, artifact name, byte count and digest.
``README.md`` names the same corpus in prose, under "Relation to the specification", and
that sentence is what a reader meets first. The two answer the same question, which corpus
this package is measured against, and must give the same answer.

The pin moves whenever the corpus changes, and prose no test reads does not move with it.
This binds one to the other: every corpus this README names is the corpus this repository
pins.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_readme_names_the_corpus_this_repository_pins() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    pin = json.loads((ROOT / "CONFORMANCE_CONSUMER.json").read_text(encoding="utf-8"))

    named = set(re.findall(r"`(loquitur-conformance-[A-Za-z0-9._-]+)`", readme))
    assert named, "README.md names no corpus; it must name the one this repository consumes"
    assert named == {pin["corpus_id"]}, (
        f"README.md names {sorted(named)}; CONFORMANCE_CONSUMER.json pins {pin['corpus_id']!r}"
    )
