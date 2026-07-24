"""Per-line producer selection — the escalation tier (ROADMAP V3 Phase 4, 5b).

A QE scorer + RoutingPolicy send some non-hyphen lines to ESCALATE; when an
``escalation_producer`` is set the pipeline routes exactly those lines to
it, leaving the rest (and every hyphen unit) with the primary producer.
Uses marker producers (primary = identity, escalation = appends "·") so
the FINAL text of each line reveals which producer handled it — no images,
no network.
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

    async def produce(self, payload, *, options):
        self.produce_calls += 1
        ops = [
            ReplaceLine(line_id=ln.line_id, text=ln.ocr_text + self._mark)
            for ln in payload.lines
        ]
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
async def test_all_escalate_routes_every_nonhyphen_line_to_vision():
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    n_nonhyphen = len(_nonhyphen_lines(doc))

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

    assert result.escalated_lines == n_nonhyphen
    assert result.fallback_chunks == 0
    apply_decisions(doc, result)
    for lm in _nonhyphen_lines(doc):
        assert lm.corrected_text == lm.ocr_text + "·"  # vision handled it
    # With every non-hyphen line escalated and (this sample) no hyphens, the
    # primary producer is never called.
    if n_nonhyphen == sum(len(p.lines) for p in doc.pages):
        assert text.produce_calls == 0
    assert vision.produce_calls > 0
    # Provenance records BOTH producer identities.
    prov = result.report.provenance
    assert prov is not None
    assert prov.producer.name == "text"
    assert prov.escalation_producer is not None
    assert prov.escalation_producer.name == "vision"


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
