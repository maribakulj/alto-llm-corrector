"""ADR-010 slice 2 — a fallback covers the WHOLE unit, across pages.

``reconcile_hyphen_pair``'s contract says a mixed OCR+corrected pair
can never survive, and the duplicate-revert pass preserves that
atomicity — but the CHUNK FALLBACK path did not: chunks are page-scoped,
a cross-page pair lives in two chunks, and when one side's chunk fell
back while the other side's chunk succeeded, the pair ended half OCR /
half corrected. The joined word across the seam was then rewritten on
one line and kept verbatim on the other — silent corruption of the one
thing the hyphen machinery exists to protect.

Reproduced (pre-fix): page 1's chunk rejected by the producer →
PART1 = fallback with its OCR fragment; page 2's chunk succeeds →
PART2 = corrected. Both directions must hold: the fallback may happen
before OR after the partner's chunk was corrected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._pipeline_harness import apply_decisions

from lidenbrock.core.protocols import ProducerMetadata
from lidenbrock import CorrectionPipeline, ValidationError
from lidenbrock.core.editing import EditScript, ReplaceLine
from lidenbrock.core.schemas import HyphenRole, LineStatus, RetryPolicy
from lidenbrock.formats.alto.parser import build_document_manifest

_XPAGE_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"><Layout>
<Page ID="P1" WIDTH="1000" HEIGHT="1000">
<PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextLine ID="L0" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20">
<String ID="S0" CONTENT="debut" HPOS="10" VPOS="10" WIDTH="80" HEIGHT="20"/>
</TextLine>
<TextLine ID="L1" HPOS="10" VPOS="40" WIDTH="900" HEIGHT="20">
<String ID="S1" CONTENT="prati" HPOS="10" VPOS="40" WIDTH="80" HEIGHT="20" \
SUBS_TYPE="HypPart1" SUBS_CONTENT="pratiques"/>
<HYP CONTENT="-"/>
</TextLine>
</TextBlock></PrintSpace></Page>
<Page ID="P2" WIDTH="1000" HEIGHT="1000">
<PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextBlock ID="B2" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextLine ID="L2" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20">
<String ID="S2" CONTENT="ques" HPOS="10" VPOS="10" WIDTH="60" HEIGHT="20" \
SUBS_TYPE="HypPart2" SUBS_CONTENT="pratiques"/>
<String ID="S3" CONTENT="ensuite" HPOS="80" VPOS="10" WIDTH="80" HEIGHT="20"/>
</TextLine>
<TextLine ID="L3" HPOS="10" VPOS="40" WIDTH="900" HEIGHT="20">
<String ID="S4" CONTENT="fin" HPOS="10" VPOS="40" WIDTH="40" HEIGHT="20"/>
</TextLine>
</TextBlock></PrintSpace></Page>
</Layout></alto>"""


class _Null:
    def on_event(self, *a, **k):
        pass

    def write_corrected(self, *, source_stem, xml_bytes):
        pass

    def write_trace(self, *, traces_payload):
        pass


class _FailsPages:
    """Rejects every payload containing a line of the given pages;
    corrects everything else deterministically."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = False

    def __init__(self, failing_line_ids: set[str]) -> None:
        self._failing = failing_line_ids

    async def produce(self, payload, *, options):
        ids = {ln.line_id for ln in payload.lines}
        if ids & self._failing:
            raise ValidationError("chunk rejected on purpose")
        ops = [
            ReplaceLine(line_id=ln.line_id, text=ln.ocr_text.replace("e", "3"))
            for ln in payload.lines
        ]
        return EditScript(ops=ops), None


def _assert_pair_consistent(doc) -> None:
    lines = {lm.line_id: lm for page in doc.pages for lm in page.lines}
    part1, part2 = lines["L1"], lines["L2"]
    assert part1.hyphen_role is HyphenRole.PART1
    assert part2.hyphen_role is HyphenRole.PART2
    assert LineStatus.PENDING not in {lm.status for lm in lines.values()}
    corrected = {lid: lm.status is LineStatus.CORRECTED for lid, lm in lines.items()}
    assert corrected["L1"] == corrected["L2"], (
        f"mixed cross-page pair: L1={part1.status.value}/{part1.corrected_text!r} "
        f"vs L2={part2.status.value}/{part2.corrected_text!r} — the joined "
        "word was rewritten on one line and kept verbatim on the other"
    )
    if not corrected["L1"]:
        assert part1.corrected_text == part1.ocr_text
        assert part2.corrected_text == part2.ocr_text


async def _run(tmp_path: Path, failing: set[str]):
    src = tmp_path / "xpage.xml"
    src.write_text(_XPAGE_ALTO, encoding="utf-8")
    doc = build_document_manifest([(src, src.name)])
    pipeline = CorrectionPipeline(
        producer=_FailsPages(failing),
        observer=_Null(),
        retry_policy=RetryPolicy(transient_backoff_base=0.0, output_backoff_base=0.0),
        producer_metadata=ProducerMetadata(name="x", implementation="m"),
    )
    result = await pipeline.run(document_manifest=doc, source_files={src.name: src})
    return apply_decisions(doc, result)


@pytest.mark.asyncio
async def test_part1_side_fallback_pulls_the_cross_page_partner(tmp_path) -> None:
    """Page 1's chunk falls back BEFORE page 2 is processed: the partner
    correction landing later must not leave the pair mixed."""
    doc = await _run(tmp_path, failing={"L0", "L1"})
    _assert_pair_consistent(doc)


@pytest.mark.asyncio
async def test_part2_side_fallback_pulls_the_cross_page_partner(tmp_path) -> None:
    """Page 2's chunk falls back AFTER page 1's side was already
    reconciled: the earlier correction must be pulled back too."""
    doc = await _run(tmp_path, failing={"L2", "L3"})
    _assert_pair_consistent(doc)


@pytest.mark.asyncio
async def test_no_chunk_failure_still_reverts_an_incoherent_pair(tmp_path) -> None:
    """Nothing fails here, and the pair still goes back to OCR — correctly.

    The harness substitutes ``e``→``3``, so ``prati-`` + ``qu3s`` joins to
    ``pratiqu3s`` while the source ``SUBS_CONTENT`` says ``pratiques``. An
    explicit pair whose boundary join no longer matches its SUBS_CONTENT is
    rejected, both sides revert, and — the part that used to be missing — the
    STATUS says so. This test previously asserted CORRECTED on both, which
    held only because a reverted pair was mislabelled: the two lines kept
    their OCR text while reporting as corrected, so the revert reached no
    counter (the same silent shape as the cross-page freeze, L3).
    """
    doc = await _run(tmp_path, failing=set())
    lines = {lm.line_id: lm for page in doc.pages for lm in page.lines}
    _assert_pair_consistent(doc)
    assert lines["L1"].status is LineStatus.FALLBACK
    assert lines["L2"].status is LineStatus.FALLBACK
    assert lines["L1"].corrected_text == lines["L1"].ocr_text
    assert lines["L2"].corrected_text == lines["L2"].ocr_text
    # A line outside the pair is unaffected: this is pair-scoped, not a
    # blanket revert.
    assert lines["L0"].status is LineStatus.CORRECTED
    assert lines["L0"].corrected_text == "d3but"
