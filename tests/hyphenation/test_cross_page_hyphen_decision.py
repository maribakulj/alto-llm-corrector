"""A cross-page hyphen pair must not freeze its second member (L3).

The engine's reconciler owned a join from its TAIL: it reconciled iff the
tail was one of the chunk's targets. For an intra-page pair that is fine —
both members are in scope together.

For a CROSS-PAGE pair it was unreachable. The tail (PART1) always sits on
the EARLIER page, which is processed first, while the head (PART2) opens the
next page and has not been corrected yet. `_reconcile_one_pair` read
``corrected_p2 = text_by_id.get(part2.line_id, part2.ocr_text)`` — the head
is not in this chunk, so it fell back to raw OCR — and wrote that as the
head's decision with ``status = CORRECTED``. When the later page ran,
`_apply_line_acceptance` skipped the line (``corrected_text is not None``)
and the correction actually produced for it was discarded.

Net effect: **the first line of every page that continued a hyphenated word
was never corrected**, the model call for it was billed anyway, and because
the status was CORRECTED rather than FALLBACK the loss appeared in no
fallback counter.

Fixed by moving ownership of a cross-page join to the HEAD — the only point
at which both sides exist. The two tests below landed first as
``xfail(strict)``, as the executable statement of the defect; they XPASSed
once ownership moved, and are now ordinary tests guarding the fix.
"""

from __future__ import annotations

from pathlib import Path

from lidenbrock.core.pipeline import CorrectionPipeline
from lidenbrock.core.schemas import HyphenRole
from lidenbrock.formats.alto.parser import build_document_manifest

from tests._pipeline_harness import DictProvider

_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Description><MeasurementUnit>pixel</MeasurementUnit>
    <OCRProcessing ID="OCR_1"><ocrProcessingStep/></OCRProcessing><Processing/>
  </Description>
  <Layout><Page ID="{pid}" WIDTH="800" HEIGHT="600">
    <PrintSpace HPOS="0" VPOS="0" WIDTH="800" HEIGHT="600">
      <TextBlock ID="TB1" HPOS="0" VPOS="0" WIDTH="800" HEIGHT="200">
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


def _two_pages(tmp_path: Path):
    """Page 1 ends mid-word on ``administra-``; page 2 opens on ``tif``.

    Line ids are unique across BOTH files on purpose: identity is
    (page_id, line_id), and the harness provider keys on the bare id, so
    reusing ``L1`` would have page 2's correction shadow page 1's.
    """
    p1 = _ALTO.format(
        pid="PAGE1",
        lines="\n".join(
            [
                _LINE.format(lid="P1L1", v=0, c="le c0nseil municipal"),
                _LINE.format(lid="P1L2", v=30, c="a v0te le budget administra-"),
            ]
        ),
    )
    p2 = _ALTO.format(
        pid="PAGE2",
        lines="\n".join(
            [
                _LINE.format(lid="P2L1", v=0, c="tif p0ur l exercice"),
                _LINE.format(lid="P2L2", v=30, c="pr0chain sans debat"),
            ]
        ),
    )
    f1, f2 = tmp_path / "p1.xml", tmp_path / "p2.xml"
    f1.write_text(p1, encoding="utf-8")
    f2.write_text(p2, encoding="utf-8")
    return f1, f2


def _run(tmp_path: Path):
    f1, f2 = _two_pages(tmp_path)
    doc = build_document_manifest([(f1, "p1.xml"), (f2, "p2.xml")])
    # Every line gets a correction: the OCR wrote '0' where 'o' belongs.
    corrections = {
        lm.line_id: lm.ocr_text.replace("0", "o")
        for page in doc.pages
        for lm in page.lines
    }
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(corrections), api_key="k", model="m", observer=_Null()
    )
    result = pipeline.run_sync(
        document_manifest=doc, source_files={"p1.xml": f1, "p2.xml": f2}
    )
    return doc, {(o.page_id, o.line_id): o for o in result.report.lines}


def test_the_pair_really_is_linked_across_the_page_break(tmp_path):
    """Precondition: without the link, the rest of this file proves nothing."""
    doc, _ = _run(tmp_path)
    lines = {(p.page_id, lm.line_id): lm for p in doc.pages for lm in p.lines}
    tail = lines[("PAGE1", "P1L2")]
    head = lines[("PAGE2", "P2L1")]
    assert tail.hyphen_role == HyphenRole.PART1
    assert tail.hyphen_pair_line_id == "P2L1"
    assert tail.hyphen_pair_page_id == "PAGE2"
    assert head.hyphen_role == HyphenRole.PART2
    assert head.hyphen_pair_line_id == "P1L2"


def test_ordinary_lines_on_both_pages_are_corrected(tmp_path):
    """Control: the defect is specific to the cross-page pair member."""
    _, out = _run(tmp_path)
    assert out[("PAGE1", "P1L1")].decision.final_text == "le conseil municipal"
    assert out[("PAGE2", "P2L2")].decision.final_text == "prochain sans debat"


def test_the_tail_of_the_cross_page_pair_is_corrected(tmp_path):
    """The PART1 side lives on the page being processed, so it is fine."""
    _, out = _run(tmp_path)
    assert out[("PAGE1", "P1L2")].decision.final_text == "a vote le budget administra-"


def test_the_head_of_the_cross_page_pair_receives_its_correction(tmp_path):
    """THE defect, now closed: the first line of page 2 used to keep its raw
    OCR text. The head owns the join, so it is corrected like any line."""
    _, out = _run(tmp_path)
    assert out[("PAGE2", "P2L1")].decision.final_text == "tif pour l exercice"


def test_a_frozen_head_is_not_reported_as_corrected(tmp_path):
    """Silence was the aggravating factor: a line that kept its OCR text must
    never be reported as corrected, whatever else is true."""
    _, out = _run(tmp_path)
    o = out[("PAGE2", "P2L1")]
    assert not (
        o.decision.final_text == o.source_text and o.decision.status == "corrected"
    )


def _run_with(tmp_path: Path, corrections: dict[str, str]):
    """Same two pages, but the caller dictates every correction."""
    f1, f2 = _two_pages(tmp_path)
    doc = build_document_manifest([(f1, "p1.xml"), (f2, "p2.xml")])
    full = {
        lm.line_id: corrections.get(lm.line_id, lm.ocr_text)
        for page in doc.pages
        for lm in page.lines
    }
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(full), api_key="k", model="m", observer=_Null()
    )
    result = pipeline.run_sync(
        document_manifest=doc, source_files={"p1.xml": f1, "p2.xml": f2}
    )
    return result, {(o.page_id, o.line_id): o for o in result.report.lines}


# The head's OCR is "tif p0ur l exercice" — four tokens. Answering with five
# grows the physical line, which the PART2 absorption guard refuses: a merged
# line would violate "lines never merge". Chosen deliberately over a wrong
# WORD, because a wrong word of three letters does not move a similarity
# ratio — the guards' semantic blindness is a documented design property
# (docs/PLAN.md, section G), not something to test around.
_ABSORBING_HEAD = {"P2L1": "tif pour l exercice complet"}


def test_an_incoherent_cross_page_pair_takes_BOTH_sides_down(tmp_path):
    """Unit atomicity across the page break.

    A pair may not survive half corrected, so both members keep their OCR —
    including the tail, whose page had already closed WITH a correction.
    That revert is the whole reason ownership had to move to the head: on
    the tail's own page there was nothing to check the join against.
    """
    _, out = _run_with(tmp_path, _ABSORBING_HEAD)

    tail = out[("PAGE1", "P1L2")]
    head = out[("PAGE2", "P2L1")]
    assert tail.decision.final_text == tail.source_text
    assert head.decision.final_text == head.source_text
    assert tail.decision.status == "fallback"
    assert head.decision.status == "fallback"


def test_a_reverted_cross_page_tail_carries_a_reason(tmp_path):
    """A fallback with no reason is a fallback nobody can audit.

    ``derive_decision_set`` reads the reason off the line's TRACE, and the
    tail's trace was finalized a page earlier — so the reconciler has to
    refresh it or the report shows a fallback with a blank motive.
    """
    _, out = _run_with(tmp_path, _ABSORBING_HEAD)

    tail = out[("PAGE1", "P1L2")]
    assert tail.decision.status == "fallback"
    assert tail.decision.reason is not None
    assert tail.decision.reason.code


def test_the_run_counts_the_reverted_tail_as_a_fallback_line(tmp_path):
    """It must reach the aggregate too: "completed with fallbacks" is
    exactly ``fallback_lines > 0``, and a silent revert is the defect this
    whole file exists about."""
    result, _ = _run_with(tmp_path, _ABSORBING_HEAD)
    assert result.fallback_lines >= 2
