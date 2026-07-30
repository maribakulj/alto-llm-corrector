"""Significant whitespace must survive the rewrite, and what cannot must be
reported (L0/L1).

The defect: the ALTO rewriter's slow path tokenised on ``\\s``, which in Python
covers U+00A0 and U+202F, and re-emitted every gap as a plain ``<SP>``. ``<SP>``
carries no content, so a no-break space came back as an ordinary one — the
delivered file no longer said what the run decided. The projection invariant
compared the two through ``" ".join(text.split())`` and saw no difference, so
nothing raised, nothing counted, and the run reported a clean correction.

Both halves are pinned here. A no-break space is by definition a place one does
NOT break, so it belongs inside its ``String``'s CONTENT and now stays there
(``exact``). Whitespace that genuinely has no ALTO representation — a tab, a
doubled space, an edge space — still cannot survive, and the run now says which
of the two happened instead of saying nothing.
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

NBSP = " "
NNBSP = " "  # French typography before % ; ! ? :


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


class TestNoBreakSpacesSurvive:
    """L1 — they are not separators, so they never become an ``<SP>``."""

    @pytest.mark.asyncio
    async def test_a_no_break_space_reaches_the_artefact_intact(self) -> None:
        result, target = await _run(NBSP)

        outcome = _outcome(result.report, target)
        assert NBSP in outcome.decision.final_text
        assert NBSP in outcome.projection.extracted_text
        assert outcome.projection.fidelity is ProjectionFidelity.EXACT

    @pytest.mark.asyncio
    async def test_a_narrow_no_break_space_reaches_the_artefact_intact(self) -> None:
        # U+202F is the space French typography puts before % ; ! ? : — the
        # most frequent significant space in the corpus this library targets.
        result, target = await _run(NNBSP)

        outcome = _outcome(result.report, target)
        assert NNBSP in outcome.projection.extracted_text
        assert outcome.projection.fidelity is ProjectionFidelity.EXACT

    @pytest.mark.asyncio
    async def test_the_run_reports_no_normalized_line(self) -> None:
        result, _ = await _run(NBSP)

        counts = result.report.projection_fidelity
        assert counts is not None
        assert counts.get(ProjectionFidelity.NORMALIZED.value, 0) == 0
        assert sum(counts.values()) == result.report.total_lines


class TestWhatTheFormatStillCosts:
    """Not everything can survive, and the run must say which is which."""

    @pytest.mark.asyncio
    async def test_a_tab_is_reported_as_a_substitution(self) -> None:
        # A tab IS a break opportunity, so it legitimately becomes an <SP>
        # and comes back as an ordinary space. A real loss — hence reported,
        # where before it was compared away.
        result, target = await _run("\t")

        outcome = _outcome(result.report, target)
        assert "\t" in outcome.decision.final_text
        assert "\t" not in outcome.projection.extracted_text
        assert outcome.projection.fidelity is ProjectionFidelity.NORMALIZED

    @pytest.mark.asyncio
    async def test_a_collapsed_run_of_spaces_is_not_called_a_substitution(self) -> None:
        # <SP> is one element: a doubled space cannot round-trip, and that is
        # the format's price, not a corrupted character.
        result, target = await _run("  ")

        outcome = _outcome(result.report, target)
        assert outcome.projection.fidelity is ProjectionFidelity.TOKEN_EQUIVALENT

    @pytest.mark.asyncio
    async def test_an_ordinary_correction_stays_exact(self) -> None:
        """The scale must not cry wolf: a plain text change loses nothing."""
        result, target = await _run(" ")

        outcome = _outcome(result.report, target)
        assert outcome.projection.fidelity is ProjectionFidelity.EXACT
        counts = result.report.projection_fidelity
        assert counts.get(ProjectionFidelity.NORMALIZED.value, 0) == 0


@pytest.mark.asyncio
async def test_the_level_survives_the_json_round_trip() -> None:
    """report.json is the artefact a host reads; the level must be in it."""
    result, target = await _run("\t")
    payload = result.report.model_dump(mode="json")

    assert payload["projection_fidelity"]["normalized"] == 1
    line = next(ln for ln in payload["lines"] if ln["line_id"] == target)
    assert line["projection"]["fidelity"] == "normalized"


# ---------------------------------------------------------------------------
# L8 — a substitution on a character that is not whitespace
# ---------------------------------------------------------------------------


_BNF = Path(__file__).parent.parent.parent.parent / "examples" / "X0000002.xml"


class _Echo:
    """Returns every line unchanged.

    The fidelity question here is about the FILE's spelling, not about a
    correction — an echo keeps every line on the UNTOUCHED path, which is
    where the overclaim was most obviously wrong: the rewriter did not so
    much as look at those elements and the run still called the grade
    ``exact``.
    """

    wants_geometry = False
    wants_image = False

    async def produce(self, payload, *, options):
        return (
            EditScript(
                ops=tuple(
                    ReplaceLine(line_id=line.line_id, text=line.ocr_text)
                    for line in payload.lines
                )
            ),
            None,
        )


@pytest.mark.asyncio
async def test_the_bnf_fixture_stops_claiming_exact_on_its_soft_hyphens() -> None:
    """End-to-end, on the document that made this false.

    115 of ``X0000002.xml``'s 566 lines carry their break mark as U+00AD
    inside ``<HYP>``. The reconstruction reads it back as ``-`` (deliberate,
    and 115 lines depend on it to pair at all), the rewrite re-emits the
    source element untouched, and the run graded every one of them ``exact``
    — "the artefact says the decision character for character", of a file
    whose characters say something else. Nothing was lost then and nothing
    is lost now: what changed is that the report says which of the two
    happened.
    """
    doc = build_document_manifest([(_BNF, _BNF.name)])
    pipeline = CorrectionPipeline(
        producer=_Echo(),
        observer=_Null(),
        producer_metadata=ProducerMetadata(name="test", implementation="v1"),
    )
    result = await pipeline.run(document_manifest=doc, source_files={_BNF.name: _BNF})

    counts = result.report.projection_fidelity or {}
    assert counts.get(ProjectionFidelity.SOURCE_SPELLING.value) == 115
    assert counts.get(ProjectionFidelity.EXACT.value) == 451
    # No line is worse than that: the collapse costs the file nothing.
    assert counts.get(ProjectionFidelity.NORMALIZED.value, 0) == 0

    # And it is the soft-hyphen lines specifically, not 115 arbitrary ones.
    spelled = {
        ln.line_id
        for ln in result.report.lines
        if ln.projection
        and ln.projection.fidelity is ProjectionFidelity.SOURCE_SPELLING
    }
    assert len(spelled) == 115
    from lxml import etree

    root = etree.parse(str(_BNF)).getroot()
    ns = root.tag.split("}")[0][1:]
    soft = {
        tl.get("ID")
        for tl in root.iter(f"{{{ns}}}TextLine")
        if any(h.get("CONTENT") == "­" for h in tl.iter(f"{{{ns}}}HYP"))
    }
    assert spelled == soft
