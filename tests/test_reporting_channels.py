"""CODE_OF_CONDUCT.md and SECURITY.md name the same two reporting channels, in the same order.

The code of conduct sends a conduct report through the two channels SECURITY.md documents and
calls them "the first" and "the second". These tests hold the two texts to that: each section
names GitHub's private vulnerability reporting first and security@loquitur.dev second.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PRIVATE_REPORTING = "**Use GitHub's private vulnerability reporting on this repository**"
ADDRESS = "**security@loquitur.dev**"

SECTIONS = {
    "CODE_OF_CONDUCT.md": "## 5. Reporting conduct issues",
    "SECURITY.md": "## Reporting channel",
}


def _section(name: str, heading: str) -> str:
    text = (ROOT / name).read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines.count(heading) == 1, f"{name}: no single section {heading!r}"
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    # Running text: a phrase may break across the wrapped lines.
    return " ".join(" ".join(lines[start:end]).split())


@pytest.mark.parametrize("name", sorted(SECTIONS))
def test_the_section_names_private_reporting_first_and_the_address_second(name: str) -> None:
    section = _section(name, SECTIONS[name])
    assert section.count(PRIVATE_REPORTING) == 1, f"{name}: private reporting is not named once"
    assert section.count(ADDRESS) == 1, f"{name}: the address is not named once"
    assert section.index(PRIVATE_REPORTING) < section.index(ADDRESS), f"{name}: the channels are in the other order"


def test_the_code_of_conduct_numbers_the_channels_as_security_md_orders_them() -> None:
    section = _section("CODE_OF_CONDUCT.md", SECTIONS["CODE_OF_CONDUCT.md"])
    first = section.index("the first of the two private channels `SECURITY.md` documents")
    second = section.index("the second channel `SECURITY.md` documents")
    assert section.index(PRIVATE_REPORTING) < first < section.index(ADDRESS) < second
