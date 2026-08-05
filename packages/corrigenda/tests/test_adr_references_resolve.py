"""An ADR the code cites must exist, and the index must list it.

`ADR-012` was cited seventeen times across `core` and both format packages
while `docs/adr/` stopped at 011, and the index stopped at 008 while
009-011 existed on disk. Neither is a typo anyone would catch by reading:
a citation reads as authoritative precisely because it looks resolvable,
and an index reads as complete precisely because it is an index.

Two rules:

  1. Every ``ADR-NNN`` a source comment cites has a file.
  2. Every file in ``docs/adr/`` is linked from the index, and every
     link in the index resolves.

The repository rule this enforces (CONTRIBUTING.md, `docs/adr/README.md`):
code comments state the invariant, ADRs hold the genealogy. That trade is
only honest while the genealogy is actually there to be read.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent.parent.parent
SRC = REPO / "packages" / "corrigenda" / "src" / "corrigenda"
ADR_DIR = REPO / "docs" / "adr"

_CITATION = re.compile(r"ADR-(\d{3})")
_INDEX_LINK = re.compile(r"\[(\d{3})\]\((\d{3}-[a-z0-9-]+\.md)\)")


def _adr_files() -> dict[str, Path]:
    return {p.name[:3]: p for p in ADR_DIR.glob("[0-9][0-9][0-9]-*.md")}


def test_every_cited_adr_exists() -> None:
    have = _adr_files()
    missing: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        for number in set(_CITATION.findall(path.read_text(encoding="utf-8"))):
            if number not in have:
                missing.setdefault(number, []).append(
                    str(path.relative_to(SRC.parent.parent))
                )
    assert not missing, (
        f"the code cites ADRs with no file: {missing}. A citation is a "
        "promise that the reasoning is written down somewhere — write the "
        "ADR, or stop citing it."
    )


def test_the_index_lists_every_adr() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    linked = {n for n, _ in _INDEX_LINK.findall(index)}
    on_disk = set(_adr_files())
    assert on_disk - linked == set(), (
        f"ADR(s) {sorted(on_disk - linked)} exist but are absent from "
        "docs/adr/README.md — an index that stops early reads as a complete "
        "one."
    )


def test_every_index_link_resolves() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    broken = [
        filename
        for _, filename in _INDEX_LINK.findall(index)
        if not (ADR_DIR / filename).exists()
    ]
    assert not broken, f"docs/adr/README.md links to missing file(s): {broken}"
