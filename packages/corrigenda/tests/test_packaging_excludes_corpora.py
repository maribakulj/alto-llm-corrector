"""No corpus reaches the distributed package (Gate 0).

The two corpora are cleanly licensed — the BnL ground truth is CC0 by the
BnL's own statement, the Gallica page is a public-domain document — but the
BnF's conditions of use cover the digital *reproduction* and distinguish
non-commercial reuse from commercial reuse of it. A test fixture is the
first; a wheel on PyPI is a redistribution channel whose downstream use
nobody controls.

That is fine today for a reason worth pinning rather than rediscovering:
the corpora live at the REPOSITORY root, outside ``packages/corrigenda/``
entirely, and the sdist declares an explicit four-entry allowlist. Neither
artefact can pick them up. Both facts are load-bearing and both are one
careless edit away from being false — a ``sdist.include`` widened to
``".."``, a corpus moved under the package "so the tests can find it".

So: assert the allowlist stays an allowlist, and assert the package tree
holds no image or corpus payload.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).parent.parent
_REPO_ROOT = _PACKAGE_ROOT.parent.parent

#: Everything the sdist is allowed to carry. Widening this list is a
#: licensing decision, not a packaging convenience.
_ALLOWED_SDIST_ENTRIES = {
    "src/corrigenda",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
}


def _pyproject() -> dict:
    with (_PACKAGE_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_the_sdist_include_list_is_still_an_allowlist() -> None:
    include = _pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert set(include) == _ALLOWED_SDIST_ENTRIES, (
        "the sdist include list moved. It is the thing that keeps corpora out "
        "of a published artefact — widening it is a licensing decision. If "
        "deliberate, update this test in the same commit and say why."
    )
    for entry in include:
        assert not entry.startswith(("/", "..")), (
            f"{entry!r} escapes the package directory; an sdist entry must "
            "stay inside it or it can reach the repository's corpora."
        )


def test_the_wheel_ships_the_package_and_nothing_else() -> None:
    wheel = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["src/corrigenda"]


def test_the_corpora_live_outside_the_package() -> None:
    """If a corpus were moved under the package it would ship in the wheel,
    allowlist or not."""
    corpus_root = _REPO_ROOT / "corpus"
    assert corpus_root.is_dir(), "fixture check: the corpora are expected here"
    assert _PACKAGE_ROOT not in corpus_root.parents
    assert not (_PACKAGE_ROOT / "corpus").exists()


def test_the_package_tree_carries_no_scan_payload() -> None:
    """A corpus is recognisable by its weight: page scans. The shipped tree
    holds none, and the largest thing in it should be a bundled XSD."""
    payload = [
        p
        for p in (_PACKAGE_ROOT / "src").rglob("*")
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    ]
    assert payload == [], f"image payload inside the package: {payload}"


def test_every_corpus_documents_its_licence() -> None:
    """Gate 0's other half: a corpus with no stated licence is a corpus
    nobody can redistribute, including us."""
    for readme in sorted((_REPO_ROOT / "corpus").glob("*/README.md")):
        text = readme.read_text(encoding="utf-8")
        assert "À VÉRIFIER" not in text, (
            f"{readme.parent.name}: licence still marked unverified. Settle it "
            "and record the statement, or drop the corpus."
        )
        assert "licence" in text.lower(), (
            f"{readme.parent.name}: no licence section at all."
        )
