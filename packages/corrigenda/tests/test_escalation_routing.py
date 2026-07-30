"""Per-line producer selection — the escalation tier (the vision/QE programme, 5b).

A QE scorer + RoutingPolicy send some lines to ESCALATE; when an
``escalation_producer`` is set the pipeline routes exactly those lines to
it and leaves the rest with the primary producer. A hyphen unit is never
skipped, and escalates only as a WHOLE unit (both members to one producer,
so the pair still reconciles); a unit whose links leave the page stays with
the primary producer.

Uses marker producers (primary = identity, escalation = appends "·") so the
final text of a plain line reveals which producer handled it — no images,
no network. For hyphen members the mark lands on the pair's boundary word
and the reconciler legitimately rejects it, so those assertions read
``escalated_lines`` and the producers' observed payloads instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._pipeline_harness import apply_decisions

from corrigenda import CorrectionPipeline
from corrigenda.core.editing import EditScript, ReplaceLine
from corrigenda.core.protocols import ProducerMetadata
from corrigenda.core.quality import RoutingPolicy
from corrigenda.core.schemas import HyphenRole
from corrigenda.errors import ConfigurationError
from corrigenda.formats.alto.parser import build_document_manifest

_SAMPLE = Path(__file__).parent.parent.parent.parent / "examples" / "sample.xml"


class _Null:
    def on_event(self, *a, **k):
        pass


class _Mark:
    """Marker producer: appends a distinctive suffix to every line so the
    final text shows which producer corrected it (empty = identity)."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self, name: str, mark: str) -> None:
        self.metadata = ProducerMetadata(name=name, implementation="m")
        self._mark = mark
        self.produce_calls = 0
        #: Every line_id that appeared in this producer's payloads (chunk
        #: targets AND context lines). Read this rather than the final text
        #: for hyphen members: the mark lands on the pair's boundary word, so
        #: the reconciler legitimately rejects it and the text reverts.
        self.lines_seen: set[str] = set()

    async def produce(self, payload, *, options):
        self.produce_calls += 1
        ops = []
        for ln in payload.lines:
            self.lines_seen.add(ln.line_id)
            ops.append(ReplaceLine(line_id=ln.line_id, text=ln.ocr_text + self._mark))
        return EditScript(ops=ops), None


class _ConstQE:
    """QE scorer that returns a fixed score for every line."""

    def __init__(self, score: float) -> None:
        self._score = score

    def needs_correction(self, text: str) -> float:
        return self._score


class _KeyedQE:
    """Escalates only lines whose OCR text is in ``hot``."""

    def __init__(self, hot: set[str]) -> None:
        self._hot = hot

    def needs_correction(self, text: str) -> float:
        return 0.99 if text in self._hot else 0.5


def _nonhyphen_lines(doc):
    return [
        lm
        for page in doc.pages
        for lm in page.lines
        if lm.hyphen_role is HyphenRole.NONE
    ]


@pytest.mark.asyncio
async def test_all_escalate_routes_every_line_including_hyphen_units():
    """Every line routes ESCALATE — including hyphen units, which move to
    the vision producer as whole units (leaving them behind was the
    hybrid's entire residual error on real press OCR)."""
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    n_lines = sum(len(p.lines) for p in doc.pages)
    assert len(_nonhyphen_lines(doc)) < n_lines, "sample must carry hyphen units"

    text = _Mark("text", "")
    vision = _Mark("vision", "·")
    pipeline = CorrectionPipeline(
        producer=text,
        observer=_Null(),
        qe_scorer=_ConstQE(0.99),
        routing_policy=RoutingPolicy(escalate_at_or_above=0.8),
        escalation_producer=vision,
    )
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )

    assert result.escalated_lines == n_lines  # hyphen members included
    assert result.fallback_chunks == 0
    apply_decisions(doc, result)
    for lm in _nonhyphen_lines(doc):
        assert lm.corrected_text == lm.ocr_text + "·"  # vision handled it
    # Nothing left for the primary producer.
    assert text.produce_calls == 0
    assert vision.produce_calls > 0
    # Provenance records BOTH producer identities.
    prov = result.report.provenance
    assert prov is not None
    assert prov.producer.name == "text"
    assert prov.escalation_producer is not None
    assert prov.escalation_producer.name == "vision"


@pytest.mark.asyncio
async def test_hyphen_unit_escalates_as_a_whole_unit():
    """QE flags ONE member of a pair; both members must reach the vision
    producer, or the pair would be split across producers and could not
    reconcile."""
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    part1 = next(
        lm for p in doc.pages for lm in p.lines if lm.hyphen_role is HyphenRole.PART1
    )
    partner_id = part1.hyphen_pair_line_id
    assert partner_id

    text = _Mark("text", "")
    vision = _Mark("vision", "·")
    pipeline = CorrectionPipeline(
        producer=text,
        observer=_Null(),
        # Only PART1's text scores high — PART2 alone would stay with text.
        qe_scorer=_KeyedQE({part1.ocr_text}),
        routing_policy=RoutingPolicy(escalate_at_or_above=0.8),
        escalation_producer=vision,
    )
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )
    # The unit moved together: 2 lines escalated, not 1 …
    assert result.escalated_lines == 2
    # … and BOTH members reached the vision producer, so the pair is
    # corrected in one call and reconciles normally. (escalated_lines is the
    # authoritative count — it IS the escalate set; this confirms the pair
    # actually travelled there.)
    assert {part1.line_id, partner_id} <= vision.lines_seen


def test_page_local_units_gathers_members():
    from corrigenda.core.pipeline import _page_local_units

    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    page = doc.pages[0]
    by_id = {lm.line_id: lm for lm in page.lines}
    part1 = next(lm for lm in page.lines if lm.hyphen_role is HyphenRole.PART1)

    units = _page_local_units(by_id)
    expected = {part1.line_id, part1.hyphen_pair_line_id}
    assert units[part1.line_id] == expected
    # Every member indexes the SAME unit — the caller may seed from either
    # side of the pair and must get the whole thing.
    assert units[part1.hyphen_pair_line_id] == expected


def test_page_local_units_omits_cross_page_and_dangling():
    """A unit that leaves the page cannot be gathered from one page's plan,
    so it is never escalated — the conservative behaviour. Absence from the
    index is how that is expressed."""
    from corrigenda.core.pipeline import _page_local_units

    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    page = doc.pages[0]
    by_id = {lm.line_id: lm for lm in page.lines}
    part1 = next(lm for lm in page.lines if lm.hyphen_role is HyphenRole.PART1)
    partner_id = part1.hyphen_pair_line_id

    def _units_with(**update):
        patched = dict(by_id)
        patched[part1.line_id] = part1.model_copy(update=update)
        return _page_local_units(patched)

    assert part1.line_id not in _units_with(hyphen_pair_page_id="SOME_OTHER_PAGE")
    assert part1.line_id not in _units_with(hyphen_pair_line_id="TL_NOPE")
    # The partner is dropped with it: half a unit is not a unit, and
    # escalating the half that stayed is precisely the split atomicity
    # forbids.
    assert partner_id not in _units_with(hyphen_pair_page_id="SOME_OTHER_PAGE")


@pytest.mark.asyncio
async def test_mixed_routing_splits_lines_between_producers():
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    lines = _nonhyphen_lines(doc)
    assert len(lines) >= 2
    hot = {lines[0].ocr_text}  # escalate exactly the first line's text

    text = _Mark("text", "")
    vision = _Mark("vision", "·")
    pipeline = CorrectionPipeline(
        producer=text,
        observer=_Null(),
        qe_scorer=_KeyedQE(hot),
        routing_policy=RoutingPolicy(escalate_at_or_above=0.8),
        escalation_producer=vision,
    )
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )
    apply_decisions(doc, result)

    escalated = [lm for lm in _nonhyphen_lines(doc) if lm.ocr_text in hot]
    others = [lm for lm in _nonhyphen_lines(doc) if lm.ocr_text not in hot]
    assert result.escalated_lines == len(escalated)
    for lm in escalated:
        assert lm.corrected_text.endswith("·")  # vision
    for lm in others:
        assert not lm.corrected_text.endswith("·")  # primary (identity)
    assert text.produce_calls > 0 and vision.produce_calls > 0


@pytest.mark.asyncio
async def test_no_escalation_producer_is_byte_identical_routing():
    """Without an escalation producer, ESCALATE lines go to the primary
    producer exactly as before — escalated_lines stays 0."""
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    text = _Mark("text", "")
    pipeline = CorrectionPipeline(
        producer=text,
        observer=_Null(),
        qe_scorer=_ConstQE(0.99),
        routing_policy=RoutingPolicy(escalate_at_or_above=0.8),
        # no escalation_producer
    )
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )
    assert result.escalated_lines == 0
    assert result.report.provenance is not None
    assert result.report.provenance.escalation_producer is None


@pytest.mark.asyncio
async def test_escalation_producer_without_images_fails_at_startup():
    """The escalation producer is preflighted too: a vision producer that
    wants images, with none supplied, is a start-up error."""

    class _VisionWants(_Mark):
        wants_image = True

    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    pipeline = CorrectionPipeline(
        producer=_Mark("text", ""),
        observer=_Null(),
        qe_scorer=_ConstQE(0.99),
        routing_policy=RoutingPolicy(escalate_at_or_above=0.8),
        escalation_producer=_VisionWants("vision", "·"),
    )
    with pytest.raises(ConfigurationError, match="page images"):
        await pipeline.run(document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE})
