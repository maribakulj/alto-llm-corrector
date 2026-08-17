"""A page with no lines, and a middle page — neither of which the suite built.

Measured on 2026-08-17 by instrumenting ``derive_hyphen_groups`` for a whole
suite run — 1604 tests, every call recorded:

    ============  =========  ================================================
    structure     reached
    ============  =========  ================================================
    chain >= 4    **476**    up to 12 members — not a coverage gap at all
    empty page    **0**      never, anywhere
    >= 3 pages    **0**      ``max pages = 2`` across the entire suite
    ============  =========  ================================================

Two pages is the *minimal* multi-page case, and it has no **middle**: "the
correction landed on the right page" and "the correction landed on the last
page" are the same statement there. And a page with no lines is not a
contrivance — a blank verso or a plate page is ordinary in a digitised volume,
and the library had never seen one.

The three-page hyphen chain from the same measurement lives in
``tests/hyphenation/test_a_chain_may_span_three_pages.py``, because its
subject is the hyphen unit and the net in that directory correctly said so.

**Nothing here was broken.** Both structures were measured working before this
file was written, so these are regression guards, not fixes — worth saying
plainly, because a test file that reads like a bug report and contains no bug
teaches the next reader the wrong thing.
"""

from __future__ import annotations

import re

import pytest

from saknussemm import CorrectionResult
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.schemas import DocumentManifest
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._alto_pages import document, empty_page, page, written
from tests._pipeline_harness import RecordingObserver

#: ``e`` is in `beta`; `alpha` and `gamma` have none — so which word changes,
#: and therefore which page it changed on, is itself observable.
_RULE = SubstitutionRule("e", "3")


def _run(payload: bytes) -> tuple[DocumentManifest, CorrectionResult]:
    path = written(payload)
    manifest = build_document_manifest([(path, path.name)])
    result = CorrectionPipeline(
        producer=RulesProducer([_RULE]),
        observer=RecordingObserver(),
    ).run_sync(document_manifest=manifest, source_files={"s.xml": path})
    return manifest, result


def _content_by_page(delivered: str) -> dict[str, list[str]]:
    return {
        page_id: re.findall(r'CONTENT="([^"]*)"', body)
        for page_id, body in re.findall(
            r'<Page ID="([^"]*)"(.*?)(?=<Page ID=|</Layout>)', delivered, re.S
        )
    }


def test_a_correction_on_the_middle_page_stays_on_the_middle_page() -> None:
    """The distinction a two-page document cannot make.

    Checked on the delivered bytes rather than on the report, because the
    report is built from the decisions and would agree with itself — the same
    reason the projection invariant cannot see cross-file contamination.

    The per-page assertion is the load-bearing one, and the reading-order
    check claims less than it looks like it claims: reversing
    ``manifest.pages`` and re-running still delivers ``P1, P2, P3``, because
    the rewriter edits the source tree in place and the file's own page order
    survives whatever the manifest says. So that line guards a future
    rewriter that rebuilds the tree, and nothing about today's. Measured,
    rather than assumed, because an assertion that cannot fail is worse than
    none: it reads as protection.
    """
    _, result = _run(
        document([page("P1", ["alpha"]), page("P2", ["beta"]), page("P3", ["gamma"])])
    )
    delivered = result.corrected_files["s.xml"].decode()

    assert re.findall(r'<Page ID="([^"]*)"', delivered) == ["P1", "P2", "P3"], (
        "the delivered pages are not in the source file's order. Today that is "
        "inherited from the tree the rewriter edits in place rather than "
        "enforced, so reaching this means the rewriter started rebuilding."
    )
    assert _content_by_page(delivered) == {
        "P1": ["alpha"],
        "P2": ["b3ta"],
        "P3": ["gamma"],
    }, (
        f"the corrected word is not where it belongs: "
        f"{_content_by_page(delivered)}. Only `beta` contains an `e`, and "
        "`beta` is on the middle page — which is the assertion a two-page "
        "fixture cannot make."
    )


def test_an_empty_page_between_two_populated_ones_survives_the_run() -> None:
    """A blank verso must neither vanish nor shift its neighbours.

    The risk a page with zero lines carries is off-by-one: a run that indexed
    pages by their position among *non-empty* pages would deliver page 3's
    corrections onto page 2 and report every line EXACT, because the
    projection invariant compares the artefact to the decisions the artefact
    was built from.
    """
    manifest, result = _run(
        document(
            [page("P1", ["alpha", "beta"]), empty_page("P2"), page("P3", ["gamma"])]
        )
    )
    assert [len(p.lines) for p in manifest.pages] == [2, 0, 1], (
        f"the fixture no longer has an empty page in the middle: "
        f"{[len(p.lines) for p in manifest.pages]}"
    )
    delivered = result.corrected_files["s.xml"].decode()

    assert re.findall(r'<Page ID="([^"]*)"', delivered) == ["P1", "P2", "P3"], (
        "the empty page was dropped from the delivered file. A page carries "
        "geometry and identity whether or not it carries text, and a consumer "
        "aligning images to pages by position would silently misalign."
    )
    assert _content_by_page(delivered) == {
        "P1": ["alpha", "b3ta"],
        "P2": [],
        "P3": ["gamma"],
    }
    assert [(line.page_id, line.line_id) for line in result.report.lines] == [
        ("P1", "P1_L0"),
        ("P1", "P1_L1"),
        ("P3", "P3_L0"),
    ], (
        f"the report's line references are "
        f"{[(ln.page_id, ln.line_id) for ln in result.report.lines]}. An empty "
        "page contributes no line and must not contribute a phantom one."
    )


@pytest.mark.parametrize(
    "pages",
    [[empty_page("P1")], [empty_page("P1"), empty_page("P2")]],
    ids=["one empty page", "two empty pages"],
)
def test_a_document_with_no_lines_at_all_delivers_a_file(pages: list[str]) -> None:
    """The degenerate end of the same case: nothing to correct.

    A run over a document with zero lines must produce the file, not a crash
    and not an absence. ``total_lines == 0`` is the honest report, and a
    caller batching a volume needs the pages back so its own numbering holds.
    """
    manifest, result = _run(document(pages))
    assert sum(len(p.lines) for p in manifest.pages) == 0

    assert "s.xml" in result.corrected_files, (
        "a document with no lines produced no output file. There is nothing to "
        "correct, which is not the same as nothing to deliver."
    )
    assert result.report.total_lines == 0
    assert result.report.lines == []
    delivered = result.corrected_files["s.xml"].decode()
    assert re.findall(r'<Page ID="([^"]*)"', delivered) == [
        f"P{i + 1}" for i in range(len(pages))
    ]
