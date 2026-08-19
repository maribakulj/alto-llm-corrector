"""What a correction on a hyphenated word costs, and where to read it.

A word broken across two lines is corrected as a UNIT: the reconciler
validates both fragments against `SUBS_CONTENT` and, when the join does not
match, reverts **both** sides to OCR. That is the right call — a mixed pair
would rewrite the joined word on one line and keep it verbatim on the other,
which is the one thing the hyphen machinery exists to prevent — but it means
a single bad fragment costs the correction of two lines.

Nothing said so. On the 24 592-line Gallica run of 2026-08-18 it was the
**second cause of refusal**, 2 271 lines, and it concentrates exactly where
correction is wanted: 12–28% of lines on the degraded pages against 7–11% on
the clean ones. A user reading only the corrected-line count would conclude
the producer was weak.

These tests are what make the README's claim checkable rather than assertable:
the number is derivable today, from `result.fallback_reasons`, without
parsing a message — and both members of a fallen pair are in it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saknussemm import CorrectionPipeline
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.core.schemas import LineStatus, RetryPolicy
from saknussemm.formats.alto.parser import build_document_manifest

from tests.hyphenation.test_unit_fallback_atomicity import _XPAGE_ALTO, _Null


class _BreaksTheJoin:
    """Corrects the PART2 fragment into something that no longer joins.

    ``prati`` + ``ques`` is ``pratiques``, which is what ``SUBS_CONTENT``
    says. Rewriting the tail as ``tiques`` makes the join ``pratitiques``,
    the reconciler refuses the pair, and BOTH lines revert — the shape this
    module is about. Every other line is corrected, so a count that also
    caught unrelated failures would be visible.
    """

    wants_geometry = False
    wants_image = False
    requires_full_coverage = False

    async def produce(self, payload, *, options):
        ops = []
        for line in payload.lines:
            text = "tiques ensuite" if line.line_id == "L2" else line.ocr_text
            ops.append(ReplaceLine(line_id=line.line_id, text=text))
        return EditScript(ops=ops), None


async def _run(tmp_path: Path):
    src = tmp_path / "xpage.xml"
    src.write_text(_XPAGE_ALTO, encoding="utf-8")
    doc = build_document_manifest([(src, src.name)])
    pipeline = CorrectionPipeline(
        producer=_BreaksTheJoin(),
        observer=_Null(),
        retry_policy=RetryPolicy(transient_backoff_base=0.0, output_backoff_base=0.0),
        producer_metadata=ProducerMetadata(name="x", implementation="m"),
    )
    return await pipeline.run(document_manifest=doc, source_files={src.name: src})


@pytest.mark.asyncio
async def test_the_cost_is_readable_without_parsing_a_message(tmp_path) -> None:
    """`result.fallback_reasons` is the whole API for this.

    If the reason ever stops travelling onto the decision, or its prefix
    changes, this fails — and the README stops being true at the same moment.
    """
    result = await _run(tmp_path)
    assert "hyphen_pair_fallback" in result.fallback_reasons, result.fallback_reasons


@pytest.mark.asyncio
async def test_both_members_of_the_pair_are_counted(tmp_path) -> None:
    """The count is in LINES, and a fallen pair contributes two of them.

    Reading it as pairs would halve the published cost. Asserted because the
    README states the unit, and a unit nobody checks drifts.
    """
    result = await _run(tmp_path)
    assert result.fallback_reasons["hyphen_pair_fallback"] == 2, (
        f"a fallen pair must contribute BOTH its lines: {result.fallback_reasons}"
    )
    fallen = {
        d.ref.line_id
        for d in result.decisions.decisions
        if d.status is LineStatus.FALLBACK
    }
    assert fallen == {"L1", "L2"}, fallen


@pytest.mark.asyncio
async def test_a_line_that_fell_for_its_own_reason_keeps_it(tmp_path) -> None:
    """The counter measures COLLATERAL, which is what makes it worth reading.

    `_refresh_pair_traces` writes its reason only where none is set, so a
    line already refused on its own merits is not relabelled as a hyphen
    casualty. Without that, the published cost would absorb every other
    cause and mean nothing.
    """
    result = await _run(tmp_path)
    reasons = {
        d.ref.line_id: d.fallback_reason
        for d in result.decisions.decisions
        if d.status is LineStatus.FALLBACK
    }
    assert all(r and r.startswith("hyphen_pair") for r in reasons.values()), reasons
    # L0 and L3 carry no break mark and were corrected: the count is not
    # simply "everything that fell".
    assert sum(result.fallback_reasons.values()) == 2, result.fallback_reasons
