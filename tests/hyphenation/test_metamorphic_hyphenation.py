"""Presentation must not change the answer (T1, metamorphic).

A hyphenated word is one thing to correct. How the document happens to be
laid out around it — which page the break falls on, whether an empty page
sits in between, which mark from the repertoire renders the break — is
presentation, not meaning. The engine's decisions must be invariant to it.

These are metamorphic properties: rather than asserting a specific output,
each builds two documents that differ only in presentation and asserts the
engine reaches the same *logical* conclusion. That is the family that finds
what example-based tests cannot, because it does not require anyone to have
guessed the failing case in advance — the chunking-invariance test
(``fcd7804``) was the first, and this file is the rest of the set the plan
asks for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lidenbrock import CorrectionPipeline
from lidenbrock.core.schemas import HyphenRole, RetryPolicy
from lidenbrock.formats.alto.parser import build_document_manifest

from tests._pipeline_harness import DictProvider

_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Description><MeasurementUnit>pixel</MeasurementUnit>
    <OCRProcessing ID="OCR_1"><ocrProcessingStep/></OCRProcessing><Processing/>
  </Description>
  <Layout><Page ID="{pid}" WIDTH="800" HEIGHT="600">
    <PrintSpace HPOS="0" VPOS="0" WIDTH="800" HEIGHT="600">
      <TextBlock ID="TB{pid}" HPOS="0" VPOS="0" WIDTH="800" HEIGHT="200">
{lines}
      </TextBlock>
    </PrintSpace>
  </Page></Layout>
</alto>
"""
_LINE = (
    '        <TextLine ID="{lid}" HPOS="0" VPOS="{v}" WIDTH="800" HEIGHT="20">\n'
    '          <String ID="S{lid}" CONTENT="{c}" HPOS="0" VPOS="{v}"'
    ' WIDTH="700" HEIGHT="20"/>\n        </TextLine>'
)


class _Null:
    def on_event(self, *a, **k) -> None:
        pass


def _page(tmp_path: Path, name: str, pid: str, lines: list[tuple[str, str]]) -> Path:
    body = "\n".join(
        _LINE.format(lid=lid, v=30 * i, c=text) for i, (lid, text) in enumerate(lines)
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(_ALTO.format(pid=pid, lines=body), encoding="utf-8")
    return path


def _run(files: list[Path]):
    doc = build_document_manifest([(f, f.name) for f in files])
    corrections = {
        lm.line_id: lm.ocr_text.replace("0", "o")
        for page in doc.pages
        for lm in page.lines
    }
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(corrections),
        api_key="k",
        model="m",
        observer=_Null(),
        retry_policy=RetryPolicy.deterministic(),
    )
    result = pipeline.run_sync(
        document_manifest=doc, source_files={f.name: f for f in files}
    )
    return doc, {(o.page_id, o.line_id): o for o in result.report.lines}


def _roles(doc) -> dict[str, HyphenRole]:
    return {lm.line_id: lm.hyphen_role for page in doc.pages for lm in page.lines}


def _partners(doc) -> dict[str, str | None]:
    return {
        lm.line_id: lm.hyphen_pair_line_id for page in doc.pages for lm in page.lines
    }


# ---------------------------------------------------------------------------
# An empty page between the halves of a broken word
# ---------------------------------------------------------------------------


def test_an_empty_page_does_not_break_the_pair_across_it(tmp_path: Path) -> None:
    """Inserting a page with no lines is pure presentation.

    ``link_cross_page_hyphens`` walks ADJACENT pages and skips a page with
    no lines, so a word broken from page 1 onto page 3 is never linked when
    page 2 happens to be empty — the pair is silently lost and both halves
    are corrected as unrelated lines. An empty page carries no text and can
    therefore change nothing about a word that spans it.
    """
    # Same line ids in both documents, so the two runs compare directly.
    tail = ("P1L1", "le budget administra-")
    head = ("P3L1", "tif du conseil")

    without = [
        _page(tmp_path / "a", "p1.xml", "PAGE1", [tail]),
        _page(tmp_path / "a", "p2.xml", "PAGE2", [head]),
    ]
    with_empty = [
        _page(tmp_path / "b", "p1.xml", "PAGE1", [tail]),
        _page(tmp_path / "b", "p2.xml", "PAGE2", []),
        _page(tmp_path / "b", "p3.xml", "PAGE3", [head]),
    ]

    doc_a, _ = _run(without)
    doc_b, _ = _run(with_empty)

    # The ROLE survives either way — the parser reads it off the trailing
    # dash without looking at another page. What the empty page destroyed
    # was the LINK, leaving an orphan PART1: a line that announces a
    # continuation to the model and has no partner to reconcile with.
    assert _roles(doc_a)["P1L1"] is HyphenRole.PART1, "precondition: the pair links"
    assert _partners(doc_a)["P1L1"] == "P3L1", "precondition: the partner resolves"

    assert _roles(doc_b)["P1L1"] is HyphenRole.PART1
    assert _partners(doc_b)["P1L1"] == "P3L1", (
        "an empty page between the halves lost the link: the tail is an "
        "orphan PART1 and the two fragments are corrected as unrelated lines"
    )


def test_an_empty_page_does_not_change_the_other_decisions(tmp_path: Path) -> None:
    """The decisions for lines that exist must be identical either way."""
    lines1 = [("P1L1", "le c0nseil municipal"), ("P1L2", "a v0te le budget")]
    lines2 = [("P2L1", "pr0chain sans debat")]

    _, out_a = _run(
        [
            _page(tmp_path / "a", "p1.xml", "PAGE1", lines1),
            _page(tmp_path / "a", "p2.xml", "PAGE2", lines2),
        ]
    )
    _, out_b = _run(
        [
            _page(tmp_path / "b", "p1.xml", "PAGE1", lines1),
            _page(tmp_path / "b", "pE.xml", "PAGEE", []),
            _page(tmp_path / "b", "p2.xml", "PAGE2", lines2),
        ]
    )

    for page_id, line_id in [("PAGE1", "P1L1"), ("PAGE1", "P1L2"), ("PAGE2", "P2L1")]:
        a, b = out_a[(page_id, line_id)], out_b[(page_id, line_id)]
        assert a.decision.final_text == b.decision.final_text, line_id
        assert a.decision.status == b.decision.status, line_id


# ---------------------------------------------------------------------------
# The same break, inside a page or across one
# ---------------------------------------------------------------------------


def test_a_break_reaches_the_same_text_whether_it_crosses_a_page(
    tmp_path: Path,
) -> None:
    """``administra-`` / ``tif`` is one word either way.

    The intra-page case is the reference: whatever the engine decides there
    is what it must decide when the same two lines are split over two files.
    This is what L3 broke — the head kept raw OCR across the seam while its
    intra-page twin was corrected.
    """
    tail = ("L1", "le budget administra-")
    head = ("L2", "tif du c0nseil")

    _, intra = _run([_page(tmp_path / "a", "one.xml", "PAGE1", [tail, head])])
    _, cross = _run(
        [
            _page(tmp_path / "b", "p1.xml", "PAGE1", [tail]),
            _page(tmp_path / "b", "p2.xml", "PAGE2", [head]),
        ]
    )

    for line_id in ("L1", "L2"):
        a = intra[("PAGE1", line_id)]
        b = cross[("PAGE1" if line_id == "L1" else "PAGE2", line_id)]
        assert a.decision.final_text == b.decision.final_text, (
            f"{line_id}: intra-page decided {a.decision.final_text!r} but the "
            f"same break across a page decided {b.decision.final_text!r}"
        )
        assert a.decision.status == b.decision.status, line_id


# ---------------------------------------------------------------------------
# Equivalent break marks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mark", ["-", "¬", "⸗"])
def test_any_repertoire_mark_pairs_the_same_way(tmp_path: Path, mark: str) -> None:
    """Which mark renders the break is typography, not structure.

    A Fraktur ``⸗`` and an ASCII ``-`` say the same thing about the word;
    24 of the 94 break marks in the BnL corpus (in the bench repository since 2026-08-16) are ``⸗``, and one of
    them being invisible to pairing was a real defect (fixed in 542c783).
    """
    files = [
        _page(
            tmp_path / f"mark{ord(mark):04x}",
            "one.xml",
            "PAGE1",
            [("L1", f"le budget administra{mark}"), ("L2", "tif du c0nseil")],
        )
    ]
    doc, out = _run(files)

    roles = _roles(doc)
    assert roles["L1"] is HyphenRole.PART1, f"{mark!r} did not pair"
    assert roles["L2"] is HyphenRole.PART2
    # The mark itself survives to the decision, verbatim.
    assert out[("PAGE1", "L1")].decision.final_text.endswith(mark)
