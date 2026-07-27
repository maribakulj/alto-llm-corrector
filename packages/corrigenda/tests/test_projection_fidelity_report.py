"""A run must REPORT the whitespace it could not carry (L0/L1).

The defect: a producer returns ``"M.\\xa0Dupont"``, the ALTO rewriter's slow
path tokenises on ``\\s`` — which in Python covers U+00A0 and U+202F — and
re-emits the gap as a plain ``<SP>``. The no-break space is gone from the
delivered file. The projection invariant compared the two through
``" ".join(text.split())``, so it saw no difference; nothing raised, nothing
counted, and the run reported a clean correction.

These tests pin the artefact end to end: the level reaches the per-line
projection stage AND the run-level tally, so a host can find the affected
lines without diffing bytes itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from corrigenda import CorrectionPipeline
from corrigenda.core.editing import EditScript, ReplaceLine
from corrigenda.core.fidelity import ProjectionFidelity
from corrigenda.core.protocols import ProducerMetadata
from corrigenda.formats.alto.parser import build_document_manifest

_SAMPLE = Path(__file__).parent.parent.parent.parent / "examples" / "sample.xml"


class _Null:
    def on_event(self, *a, **k):
        pass


class _RespaceFirstLine:
    """Rewrites the first multi-word line's FIRST gap, and nothing else.

    A hand-built producer rather than a rules substitution: the point is a
    specific whitespace character at a specific gap, which a regex rule
    cannot express without matching every other gap too. Keeping the words
    identical also keeps the acceptance guards out of the way — a wholesale
    replacement would be refused before it could ever reach the rewriter,
    and the test would pass for the wrong reason.
    """

    wants_geometry = False
    wants_image = False

    def __init__(self, gap: str) -> None:
        self._gap = gap
        self.target: str | None = None

    async def produce(self, payload, *, options):
        ops = []
        for line in payload.lines:
            if self.target is None and " " in line.ocr_text:
                self.target = line.line_id
            text = line.ocr_text
            if line.line_id == self.target:
                text = text.replace(" ", self._gap, 1)
            # Every line of the chunk gets an op: a producer that answers
            # only about the lines it changed fails full-coverage
            # validation and the whole chunk falls back to OCR.
            ops.append(ReplaceLine(line_id=line.line_id, text=text))
        return EditScript(ops=tuple(ops)), None


async def _run(gap: str):
    producer = _RespaceFirstLine(gap)
    pipeline = CorrectionPipeline(
        producer=producer,
        observer=_Null(),
        producer_metadata=ProducerMetadata(name="test", implementation="v1"),
    )
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )
    return result, producer.target


def _outcome(report, line_id: str):
    return next(ln for ln in report.lines if ln.line_id == line_id)


@pytest.mark.asyncio
async def test_a_crushed_nbsp_is_reported_not_swallowed() -> None:
    """The line still says the same words — and the report now says it does
    not say them the same way."""
    result, target = await _run("\xa0")

    outcome = _outcome(result.report, target)
    assert outcome.projection is not None
    assert outcome.projection.fidelity is ProjectionFidelity.NORMALIZED

    # The bytes really did lose it — a report of a real loss, not a
    # pessimistic label.
    assert "\xa0" in outcome.decision.final_text
    assert "\xa0" not in outcome.projection.extracted_text


@pytest.mark.asyncio
async def test_a_crushed_narrow_nbsp_is_reported() -> None:
    """U+202F — French typography before % ; ! ? : — same fate, same report."""
    result, target = await _run("\u202f")

    outcome = _outcome(result.report, target)
    assert outcome.projection.fidelity is ProjectionFidelity.NORMALIZED
    assert "\u202f" in outcome.decision.final_text
    assert "\u202f" not in outcome.projection.extracted_text


@pytest.mark.asyncio
async def test_the_run_tallies_its_normalized_lines() -> None:
    """One host-visible number: how many lines did not survive intact."""
    result, target = await _run("\xa0")

    counts = result.report.projection_fidelity
    assert counts is not None
    assert counts.get(ProjectionFidelity.NORMALIZED.value) == 1
    # Every other line was untouched, so nothing else degraded.
    assert sum(counts.values()) == result.report.total_lines
    assert counts.get(ProjectionFidelity.EXACT.value, 0) >= 1


@pytest.mark.asyncio
async def test_an_ordinary_correction_stays_exact() -> None:
    """The scale must not cry wolf: a plain text change loses nothing."""
    result, target = await _run(" ")

    outcome = _outcome(result.report, target)
    assert outcome.projection.fidelity is ProjectionFidelity.EXACT

    counts = result.report.projection_fidelity
    assert counts.get(ProjectionFidelity.NORMALIZED.value, 0) == 0


@pytest.mark.asyncio
async def test_a_collapsed_run_of_spaces_is_not_reported_as_a_substitution() -> None:
    """``<SP>`` is one element: a doubled space cannot round-trip, and that
    is the format's price, not a corrupted character."""
    result, target = await _run("  ")

    outcome = _outcome(result.report, target)
    assert outcome.projection.fidelity is ProjectionFidelity.TOKEN_EQUIVALENT
    counts = result.report.projection_fidelity
    assert counts.get(ProjectionFidelity.NORMALIZED.value, 0) == 0


@pytest.mark.asyncio
async def test_the_tally_survives_the_json_round_trip() -> None:
    """report.json is the artefact a host reads; the level must be there."""
    result, target = await _run("\xa0")
    payload = result.report.model_dump(mode="json")

    assert payload["projection_fidelity"]["normalized"] == 1
    line = next(ln for ln in payload["lines"] if ln["line_id"] == target)
    assert line["projection"]["fidelity"] == "normalized"
