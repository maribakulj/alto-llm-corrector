"""No corpus reaches the distributed package (Gate 0).

The two corpora are cleanly licensed — the BnL ground truth is CC0 by the
BnL's own statement, the Gallica page is a public-domain document — but the
BnF's conditions of use cover the digital *reproduction* and distinguish
non-commercial reuse from commercial reuse of it. A test fixture is the
first; a wheel on PyPI is a redistribution channel whose downstream use
nobody controls.

That is fine today for a reason worth pinning rather than rediscovering:
the corpora live at the REPOSITORY root, outside ``packages/corrigenda/``
entirely, and the sdist declares an explicit four-entry allowlist. Both
facts are load-bearing and both are one careless edit away from being
false — a ``sdist.include`` widened to ``".."``, a corpus moved under the
package "so the tests can find it".

**And asserting the declaration was not enough.** This file used to check
only that ``sdist.include`` still held its four entries, which it did —
while the built sdist carried ``tests/corpus_gt/README.md`` and
``tests/external_corpus/pinned/README.md`` as well. Hatchling matches those
entries as PATTERNS, so an unanchored ``README.md`` matches every README at
any depth. No corpus DATA ever shipped (the XML matched nothing, and the
licensing conclusion above never wavered), but "explicit four-entry
allowlist" described an intention, not an artefact — the exact gap this
repository keeps finding, in the one test written to close it.

So the entries are anchored (``/README.md``), and the checks below read the
BUILT distributions. Building is a few seconds; a packaging claim that
nothing verifies is worth more than the seconds.
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from tests._paths import PKG

_PACKAGE_ROOT = PKG
_REPO_ROOT = _PACKAGE_ROOT.parent.parent

#: Everything the sdist is allowed to carry. Widening this list is a
#: licensing decision, not a packaging convenience.
_ALLOWED_SDIST_ENTRIES = {
    "/src/corrigenda",
    "/README.md",
    "/CHANGELOG.md",
    "/LICENSE",
}

#: Files hatchling adds to every sdist regardless of the allowlist. Listed
#: so the artefact check compares like with like instead of failing on
#: metadata nobody chose to ship.
_SDIST_BUILD_METADATA = {"PKG-INFO", "pyproject.toml", ".gitignore"}


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
        # `..` escapes the package directory and could reach the corpora.
        # A LEADING SLASH does the opposite: in hatchling's pattern syntax it
        # anchors the entry to the project root instead of letting it match at
        # any depth. This assertion used to forbid both, and forbidding the
        # anchor is precisely what left `README.md` matching two corpus
        # READMEs inside `tests/`.
        assert ".." not in entry, (
            f"{entry!r} escapes the package directory; an sdist entry must "
            "stay inside it or it can reach the repository's corpora."
        )
        assert entry.startswith("/"), (
            f"{entry!r} is not anchored. Unanchored entries are patterns "
            "matched at any depth — prefix it with '/' so it names the file "
            "at the project root and nothing else."
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


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Build the real sdist and wheel once, and hand back their paths.

    Skipped rather than failed when `build` is absent: a contributor
    without the release tooling should not see a red suite, but CI (which
    installs it) must run this.
    """
    pytest.importorskip("build", reason="pip install build to run packaging checks")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(out), str(_PACKAGE_ROOT)],
        check=True,
        capture_output=True,
    )
    return {
        "sdist": next(out.glob("*.tar.gz")),
        "wheel": next(out.glob("*.whl")),
    }


def _sdist_entries(path: Path) -> set[str]:
    """Paths inside the sdist, relative to its single root directory."""
    with tarfile.open(path) as tar:
        return {n.split("/", 1)[1] for n in tar.getnames() if "/" in n}


def test_the_built_sdist_carries_only_what_the_allowlist_names(
    built: dict[str, Path],
) -> None:
    entries = _sdist_entries(built["sdist"])
    allowed_roots = {e.lstrip("/").split("/", 1)[0] for e in _ALLOWED_SDIST_ENTRIES}
    unexpected = sorted(
        e
        for e in entries
        if e not in _SDIST_BUILD_METADATA and e.split("/", 1)[0] not in allowed_roots
    )
    assert not unexpected, (
        f"the built sdist carries {unexpected}, which the allowlist does not "
        "name. hatchling matches include entries as patterns — anchor them "
        "with a leading slash, or widen the allowlist deliberately (that is a "
        "licensing decision)."
    )


def test_no_built_artefact_carries_corpus_payload(built: dict[str, Path]) -> None:
    """A corpus is recognisable by its weight and its extension. Neither
    distribution may carry a transcription file or a page scan."""
    payloads = {".xml", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    with zipfile.ZipFile(built["wheel"]) as zf:
        wheel_names = zf.namelist()
    offenders = {
        "sdist": sorted(
            n
            for n in _sdist_entries(built["sdist"])
            if Path(n).suffix.lower() in payloads
        ),
        "wheel": sorted(n for n in wheel_names if Path(n).suffix.lower() in payloads),
    }
    assert not any(offenders.values()), (
        f"a distribution carries transcription or scan payload: {offenders}. "
        "The corpora are fixtures, not redistributable package content — see "
        "this module's docstring for why that distinction is licensing, not "
        "tidiness."
    )
