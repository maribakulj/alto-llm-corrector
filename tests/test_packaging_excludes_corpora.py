"""No corpus reaches the distributed package (Gate 0).

The two corpora are cleanly licensed — the BnL ground truth is CC0 by the
BnL's own statement, the Gallica page is a public-domain document — but the
BnF's conditions of use cover the digital *reproduction* and distinguish
non-commercial reuse from commercial reuse of it. A test fixture is the
first; a wheel on PyPI is a redistribution channel whose downstream use
nobody controls.

It used to rest on two facts. The corpora lived at the repository root,
OUTSIDE the package directory — so no corpus could be under the
distribution root at all — and the sdist declared an explicit four-entry
allowlist.

**Both halves of the first fact are gone, in opposite directions.**
Flattening the tree made the package root the repository root; then the
campaign corpora left for the bench, taking 43 MB with them. So there is
no longer a `corpus/` here to keep out.

What remains committed is `tests/external_corpus/pinned/` — 1.89 MB of
real Gallica ALTO, put there deliberately so that pages produced by a real
OCR pipeline, on documents never opened during development, gate every
merge. It is a fixture, not a campaign corpus, and it is INSIDE the
distribution root like everything else now.

So the allowlist is not redundant: it is the only thing between those
pages and a published artefact. And asserting the declaration was never
enough — this file used to check only that `sdist.include` still held its
four entries, which it did, while the built sdist carried two READMEs from
under `tests/` as well. Hatchling matches the entries as PATTERNS, so an
unanchored `README.md` matches every README at any depth.

The entries are anchored now, and the checks below read the BUILT
distributions. Building takes a few seconds; a packaging claim that
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

from tests._paths import PKG, SRC

_PACKAGE_ROOT = PKG
_REPO_ROOT = _PACKAGE_ROOT  # flat tree: the package IS the repository

#: Everything the sdist is allowed to carry. Widening this list is a
#: licensing decision, not a packaging convenience.
_ALLOWED_SDIST_ENTRIES = {
    "/src/saknussemm",
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
    assert wheel["packages"] == ["src/saknussemm"]


def test_no_campaign_corpus_lives_here_any_more() -> None:
    """The 43 MB left on 2026-08-16, and nothing should bring them back.

    Campaign corpora — pages with their scans, measured against a model —
    belong where the measuring happens. Here they were 43 MB of weight in
    a repository whose only job is to be publishable, and after the tree
    was flattened they sat inside the distribution root, held out of the
    artefact by an allowlist and nothing else.

    This asserts the absence rather than a layout, because absence is the
    only form of this guarantee that a future refactor cannot quietly
    invert.
    """
    assert not (_REPO_ROOT / "corpus").exists(), (
        "corpus/ is back. Campaign corpora live in the bench repository; "
        "if a fixture is what you need, it goes in tests/ and it is small."
    )
    assert not (_REPO_ROOT / "measurements").exists(), (
        "measurements/ is back. A run's output is a record of a campaign, "
        "and campaigns are archived where they are run."
    )


def test_the_pinned_pages_are_the_one_committed_corpus_and_stay_out_of_the_artefact() -> (
    None
):
    """What IS committed, why, and what keeps it out of a release.

    ``tests/external_corpus/pinned/`` holds real Gallica ALTO on purpose:
    it is the only tier that gates a merge offline. It is also the only
    corpus data left in this repository, so it is the only thing the
    allowlist still has to hold back — which the built-artefact tests
    below actually verify, rather than trusting the declaration.
    """
    pinned = _REPO_ROOT / "tests" / "external_corpus" / "pinned"
    pages = sorted(pinned.glob("*.alto.xml"))
    assert pages, (
        "the pinned tier is empty again. It is what makes an external page "
        "block a merge; without it the external corpus gates nothing."
    )
    readme = (pinned / "README.md").read_text(encoding="utf-8")
    for page in pages:
        assert page.name in readme, (
            f"{page.name} is pinned but not recorded in the README — "
            "provenance and sha256 are the point of pinning it."
        )


def test_the_package_tree_carries_no_scan_payload() -> None:
    """A corpus is recognisable by its weight: page scans. The shipped tree
    holds none, and the largest thing in it should be a bundled XSD."""
    payload = [
        p
        for p in (_PACKAGE_ROOT / "src").rglob("*")
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    ]
    assert payload == [], f"image payload inside the package: {payload}"


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


def test_the_wheel_actually_ships_the_bundled_schemas(built: dict[str, Path]) -> None:
    """Les XSD sont une fonctionnalité, pas un résidu — et rien ne le tenait.

    ``formats/validation.py`` résout ses schémas depuis
    ``src/saknussemm/formats/xsd/``. ``test_xsd_validation.py`` s'exécute
    depuis l'ARBRE SOURCE, donc il passerait à l'identique sur un wheel qui
    ne les embarquerait pas — et la validation hors-ligne échouerait chez
    tout consommateur installé, sur une erreur de fichier manquant.

    Mesuré : 7 schémas, 380 Ko décompressés, 32 % du contenu du wheel pour
    363 Ko compressés au total. C'est le prix assumé de la validation
    hors-ligne dans l'installation de base, et `docs/format-support.md` le
    dit maintenant plutôt que de le laisser deviner.
    """
    with zipfile.ZipFile(built["wheel"]) as zf:
        shipped = {Path(n).name for n in zf.namelist() if n.endswith(".xsd")}
    declared = {p.name for p in (SRC / "formats" / "xsd").glob("*.xsd")}
    assert declared, "l'arbre source ne porte plus aucun schéma"
    assert shipped == declared, (
        f"le wheel embarque {sorted(shipped)} alors que la source déclare "
        f"{sorted(declared)}. `formats.validation` résout ses schémas depuis "
        f"le paquet installé : un schéma absent du wheel est une "
        f"fonctionnalité cassée qu'aucun test lancé depuis l'arbre source ne "
        f"peut voir."
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
