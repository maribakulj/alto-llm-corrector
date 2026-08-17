"""Plan V4.2 phase 3 — invariants over the EXTERNAL Gallica corpus.

The unit and property suites share a blind spot: the same person wrote
the code and the generators, so both encode the same assumptions. This
suite runs the real pipeline over ALTO files produced by a REAL OCR
pipeline (Gallica/BnF) on documents never opened during development —
see external_corpus/manifest.json for the pinned set.

The corpus comes in two tiers:

- **fetched** — downloaded at CI time by ``external_corpus/fetch.py``
  (a dedicated NON-BLOCKING job — network flakiness must not gate
  merges while the corpus job builds its track record). Locally:

      python tests/external_corpus/fetch.py && pytest -m external_corpus

- **pinned** — real Gallica pages committed under
  ``external_corpus/pinned/`` (see its README for provenance rules).
  These run in the DEFAULT test suite, offline, and BLOCK merges: no
  ``external_corpus`` marker, no self-skip.

When neither tier has files, the tests self-skip and the default
``pytest`` run is unaffected.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.schemas import HyphenRole, LineStatus
from saknussemm.errors import CorrectionError
from saknussemm.formats.alto.parser import build_document_manifest

from tests._pipeline_harness import DictProvider, RecordingObserver
from saknussemm.core.pipeline import CorrectionPipeline

from tests._paths import TESTS

_CACHE = Path(
    os.environ.get(
        "SAKNUSSEMM_EXTERNAL_CORPUS_DIR",
        TESTS / "external_corpus" / ".cache",
    )
)
_PINNED_DIR = TESTS / "external_corpus" / "pinned"
_FETCHED = sorted(_CACHE.glob("*.alto.xml")) if _CACHE.is_dir() else []
_PINNED = sorted(_PINNED_DIR.glob("*.alto.xml")) if _PINNED_DIR.is_dir() else []


def _corpus_params() -> list:
    """Pinned files run everywhere (blocking); fetched files only under
    ``-m external_corpus``. An empty corpus yields one skipped param so
    collection never errors."""
    params = [pytest.param(p, id=f"pinned-{p.name}") for p in _PINNED] + [
        pytest.param(p, id=p.name, marks=pytest.mark.external_corpus) for p in _FETCHED
    ]
    if not params:
        params = [
            pytest.param(
                None,
                id="corpus-absent",
                marks=pytest.mark.skip(
                    reason="no pinned corpus committed and external corpus "
                    "not fetched (run tests/external_corpus/fetch.py)"
                ),
            )
        ]
    return params


@pytest.mark.parametrize("xml_path", _corpus_params(), ids=None)
def test_parses_or_fails_classified(xml_path: Path) -> None:
    """§8.4 at the front door, on real-world OCR output.

    The assertion counts ``TextLine`` elements in the FILE and compares that
    to the manifest, which is the only form of this check that says
    anything. It used to read::

        assert doc.total_lines == sum(len(p.lines) for p in doc.pages)

    and ``DocumentManifest.total_lines`` is a ``computed_field`` whose body
    is literally that expression — the same computation on both sides, true
    of an empty manifest too. Measured 2026-08-17: a parser dropping the
    last ``TextLine`` of every ``TextBlock`` took the pinned page from 1144
    lines to 997, and **all 18 tests in this file passed** while the rest of
    the suite fell to 142 failures. This tier exists to be the antidote to
    "the same person wrote the code and the generators", and it was
    contributing nothing to detection.

    Counted with lxml directly rather than through this library's parser:
    lxml is not the code under test, and the whole value of the check is that
    the two counts come from different places.

    Margins are excluded because the parser excludes them, deliberately and
    by documented design — running heads and folio numbers are not body
    text. Measured on the pinned pages, that is exactly what the difference
    was: ``'NATURELLE. 9'`` under ``TopMargin``, ``'2'`` under
    ``BottomMargin``, ``'LE TEMPS. 1" Janvier 1890.'`` under ``TopMargin``.
    A first version of this assertion counted every ``TextLine`` and failed
    on all three pages — asserting a property the library does not have, and
    should not.
    """
    from lxml import etree as _etree

    tree = _etree.parse(str(xml_path))
    in_file = sum(
        1
        for element in tree.iter()
        if element.tag.rsplit("}", 1)[-1] == "TextLine"
        and not any(
            ancestor.tag.rsplit("}", 1)[-1].endswith("Margin")
            for ancestor in element.iterancestors()
        )
    )
    try:
        doc = build_document_manifest([(xml_path, xml_path.name)])
    except CorrectionError:
        return  # classified — acceptable for a hostile real-world file
    assert doc.total_lines == in_file, (
        f"{xml_path.name} carries {in_file} non-margin TextLine element(s) "
        f"and the manifest reports {doc.total_lines}. A page that parses must "
        "parse WHOLLY: a line the parser silently drops is text this library "
        "would never correct and never mention."
    )
    in_file_ids = {
        element.get("ID")
        for element in tree.iter()
        if element.tag.rsplit("}", 1)[-1] == "TextLine"
    }
    invented = {line.line_id for page in doc.pages for line in page.lines} - in_file_ids
    assert not invented, (
        f"{xml_path.name}: the manifest names {sorted(invented)[:5]}, which no "
        "TextLine in the file carries. The other direction of the same check: "
        "a parse must not add lines either."
    )


@pytest.mark.parametrize("xml_path", _corpus_params(), ids=None)
def test_identity_run_preserves_invariants(xml_path: Path) -> None:
    """Identity pipeline run over a real file: input manifest untouched
    (ADR-011), every line terminally decided, no mixed hyphen pairs."""
    try:
        doc = build_document_manifest([(xml_path, xml_path.name)])
    except CorrectionError:
        pytest.skip("file rejected at parse (classified) — nothing to run")
    if doc.total_lines == 0:
        pytest.skip("no text lines on this page")

    def snapshot() -> dict[LineRef, tuple]:
        return {
            line_ref(lm): (
                lm.coords.hpos,
                lm.coords.vpos,
                lm.coords.width,
                lm.coords.height,
                lm.status,
                lm.corrected_text,
            )
            for page in doc.pages
            for lm in page.lines
        }

    snapshot_before = snapshot()

    pipeline = CorrectionPipeline.for_provider(
        DictProvider({}),  # identity: every line echoed unchanged
        api_key="k",
        model="m",
        observer=RecordingObserver(),
    )
    result = pipeline.run_sync(
        document_manifest=doc,
        source_files={xml_path.name: xml_path},
    )

    # ADR-011 slice E — the input manifest is never mutated: geometry AND
    # correction state are identical after the run.
    assert snapshot() == snapshot_before

    # Every line reached a terminal decision — read off the run's
    # DecisionSet (ADR-011), not the input manifest.
    decisions = result.decisions.by_ref
    assert set(decisions) == set(snapshot_before)
    for decision in decisions.values():
        assert decision.status in (
            LineStatus.CORRECTED,
            LineStatus.FALLBACK,
        ), f"{decision.ref}: non-terminal status {decision.status}"

    # No mixed hyphen pair: PART1 and PART2 are decided together (ADR-010
    # unit atomicity — a member never falls back without its partner).
    for page in doc.pages:
        for lm in page.lines:
            if lm.hyphen_role != HyphenRole.PART1 or not lm.hyphen_pair_line_id:
                continue
            partner_ref = LineRef(
                page_id=lm.hyphen_pair_page_id or lm.page_id,
                line_id=lm.hyphen_pair_line_id,
            )
            if partner_ref in decisions:
                assert (
                    decisions[line_ref(lm)].status == decisions[partner_ref].status
                ), f"mixed pair {line_ref(lm)}/{partner_ref}"

    assert result.report.total_lines == doc.total_lines
