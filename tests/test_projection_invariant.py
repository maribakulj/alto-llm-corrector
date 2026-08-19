"""The rendered artefact must SAY what the run decided (§9 projection).

The rewrite returns the per-line texts of the final tree its bytes were
serialized from (ADR-011 — no second parse of the output), and the
pipeline verifies them against the decided texts BEFORE the bytes reach
the result: any word-level divergence fails the run — a divergent
artefact is corruption, not a degradation, and it must never become a
``CorrectionResult`` a caller could persist. Serialization fidelity
(tree → bytes) is lxml's contract; what the invariant guards is the
rewriter's tree diverging from the run's decisions.

Known, tolerated projection loss: ALTO/PAGE tokenize line text into
word elements, so runs of consecutive whitespace cannot survive the
round-trip. The invariant therefore compares in whitespace-run normal
form; exact-spacing accounting belongs to the loss policy, not here.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from saknussemm.core.protocols import ProducerMetadata
from saknussemm import CorrectionPipeline
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.formats.alto.adapter import AltoFormatAdapter
from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._paths import EXAMPLES

_SAMPLE = EXAMPLES / "sample.xml"


class _Null:
    def on_event(self, *a, **k):
        pass


class _CorruptingAdapter:
    """Real ALTO adapter whose rewrite ends with one line's text altered —
    simulates a rewriter bug that puts text the run never decided into
    the tree it serializes."""

    def __init__(self) -> None:
        self._inner = AltoFormatAdapter()

    def rewrite_file(self, *args, **kwargs):
        result = self._inner.rewrite_file(*args, **kwargs)
        first = next(iter(sorted(result.texts)))
        return replace(
            result, texts={**result.texts, first: "XX" + result.texts[first]}
        )


class _LineDroppingAdapter:
    """Real ALTO adapter whose rewrite loses one line — simulates a
    rewrite that dropped a TextLine from the artefact."""

    def __init__(self) -> None:
        self._inner = AltoFormatAdapter()

    def rewrite_file(self, *args, **kwargs):
        result = self._inner.rewrite_file(*args, **kwargs)
        texts = dict(result.texts)
        texts.pop(next(iter(sorted(texts))))
        return replace(result, texts=texts)


def _pipeline(adapter) -> CorrectionPipeline:
    return CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("e", "3")]),
        observer=_Null(),
        format_adapter=adapter,
        producer_metadata=ProducerMetadata(name="rules", implementation="v1"),
    )


@pytest.mark.asyncio
async def test_a_corrupted_rewrite_is_withheld_not_delivered() -> None:
    """The file is ABSENT, and named. It is never handed back doubtful.

    The run used to raise here, which threw away every other file and the
    report with them. What must not change is the artefact itself: a
    divergent rewrite is never a deliverable, whatever else the run
    returns.
    """
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    result = await _pipeline(_CorruptingAdapter()).run(
        document_manifest=doc,
        source_files={_SAMPLE.name: _SAMPLE},
    )
    assert _SAMPLE.name not in result.corrected_files
    with pytest.raises(KeyError):
        result.corrected_files[_SAMPLE.name]

    why = result.undeliverable_files[_SAMPLE.name]
    assert _SAMPLE.name in why and "TL" in why, why
    assert result.report.undeliverable_files == result.undeliverable_files


@pytest.mark.asyncio
async def test_a_dropped_line_is_withheld_too() -> None:
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    result = await _pipeline(_LineDroppingAdapter()).run(
        document_manifest=doc,
        source_files={_SAMPLE.name: _SAMPLE},
    )
    assert _SAMPLE.name not in result.corrected_files
    assert "missing" in result.undeliverable_files[_SAMPLE.name]


@pytest.mark.asyncio
async def test_writing_an_incomplete_set_is_refused(tmp_path) -> None:
    """The one door that puts bytes on disk will not do it by omission.

    This is what replaces the raise. Withholding the file is not enough on
    its own: a caller looping over `corrected_files` would persist 299 of
    300 pages and report success. `write` answers for that.
    """
    from saknussemm.errors import ConfigurationError

    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    result = await _pipeline(_CorruptingAdapter()).run(
        document_manifest=doc,
        source_files={_SAMPLE.name: _SAMPLE},
    )
    with pytest.raises(ConfigurationError, match="INCOMPLETE"):
        result.write(tmp_path)
    assert not list(tmp_path.glob("*")), "nothing may be written before the refusal"

    written = result.write(tmp_path, allow_partial=True)
    assert [p.name for p in written] == ["report.json"], written


class _DoubleSpaceProducer:
    """Proposes a correction ALTO cannot represent exactly (consecutive
    spaces) — the documented, tolerated projection loss."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = False

    async def produce(self, payload, *, options):
        first = payload.lines[0]
        return (
            EditScript(
                ops=[
                    ReplaceLine(
                        line_id=first.line_id,
                        text=first.ocr_text.replace(" ", "  ", 1),
                    )
                ]
            ),
            None,
        )


@pytest.mark.asyncio
async def test_whitespace_collapse_is_tolerated_not_fatal() -> None:
    """Word tokenization collapses whitespace runs; that is a known
    projection property of the formats, not corruption — the run
    succeeds and the artefact is on the result."""
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    pipeline = CorrectionPipeline(
        producer=_DoubleSpaceProducer(),
        observer=_Null(),
        producer_metadata=ProducerMetadata(name="x", implementation="y"),
    )
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )
    assert result.corrected_files, "the run must have produced its artefact"


@pytest.mark.asyncio
async def test_healthy_run_passes_the_invariant() -> None:
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    pipeline = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("e", "3")]),
        observer=_Null(),
        producer_metadata=ProducerMetadata(name="rules", implementation="v1"),
    )
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )
    assert result.corrected_files
