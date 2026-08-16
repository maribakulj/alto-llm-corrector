"""Every channel the rewrite reports on reaches the trace it belongs to.

The rendering stage takes one :class:`RewriteResult` and fans it out onto
six independent per-line channels: which path the rewriter took, what the
artefact ends up saying, how faithfully that carries the decision, what the
format dropped and where, and whether the alignment suspected a word
reorder. They are separate channels on purpose — R5 and R8 exist precisely
because two of them had been folded into the loss counters, where summing
them counted a non-loss.

Nothing was checking that the fan-out lands. The stage was 81% covered and
every uncovered branch was one of these writes, which is the one kind of
defect that stays invisible: a channel that quietly stops being filled makes
the report *look* clean.

The adapter here is a fake, and deliberately so — driving all six channels
through a real ALTO rewrite would need six contrived documents, and would
test the ALTO rewriter (which has its own suites) rather than the wiring.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from lidenbrock.core import events as ev
from lidenbrock.core.decisions import derive_decision_set
from lidenbrock.core.fidelity import ProjectionFidelity
from lidenbrock.core.identity import LineRef
from lidenbrock.core.protocols import (
    ProducerMetadata,
    RewriteResult,
)
from lidenbrock.core.rendering import _render_outputs
from lidenbrock.core.schemas import (
    BlockManifest,
    Coords,
    DocumentManifest,
    LineManifest,
    LineStatus,
    LineTrace,
    PageManifest,
)

_XML = b'<?xml version="1.0"?><alto/>'


@dataclass(frozen=True)
class _Metrics:
    """A concrete stand-in for the RewriteMetrics structural protocol."""

    untouched: int
    subs_only: int
    fast_path: int
    slow_path: int


def _document() -> DocumentManifest:
    lines = [
        LineManifest(
            line_id=f"l{i}",
            page_id="p1",
            block_id="b1",
            line_order_global=i - 1,
            line_order_in_block=i - 1,
            coords=Coords(hpos=0, vpos=10 * i, width=100, height=8),
            ocr_text=f"source {i}",
            corrected_text=f"source {i}",
            status=LineStatus.CORRECTED,
        )
        for i in (1, 2)
    ]
    page = PageManifest(
        page_id="p1",
        page_index=0,
        source_file="doc.xml",
        page_width=200,
        page_height=100,
        blocks=[
            BlockManifest(
                block_id="b1",
                page_id="p1",
                block_order=0,
                coords=Coords(hpos=0, vpos=0, width=200, height=100),
                line_ids=[lm.line_id for lm in lines],
            )
        ],
        lines=lines,
    )
    return DocumentManifest(
        document_id="d1", pages=[page], source_format="alto", source_files=["doc.xml"]
    )


def _traces(doc: DocumentManifest) -> dict[LineRef, LineTrace]:
    return {
        LineRef(page_id=lm.page_id, line_id=lm.line_id): LineTrace(
            line_id=lm.line_id,
            page_id=lm.page_id,
            source_ocr_text=lm.ocr_text,
            hyphen_role=lm.hyphen_role.value,
        )
        for page in doc.pages
        for lm in page.lines
    }


class _FakeAdapter:
    """Returns one prepared RewriteResult, exercising every channel."""

    format_name = "alto"

    def __init__(self, result: RewriteResult) -> None:
        self.result = result
        self.calls: list[tuple[Any, ...]] = []

    def rewrite_file(
        self,
        xml_path: Path,
        pages: list[PageManifest],
        provider: str,
        model: str,
        **kwargs: Any,
    ) -> RewriteResult:
        self.calls.append((xml_path, provider, model, kwargs))
        return self.result


def _result(**overrides: Any) -> RewriteResult:
    base: dict[str, Any] = dict(
        xml_bytes=_XML,
        metrics=_Metrics(untouched=1, subs_only=0, fast_path=1, slow_path=0),
        rewriter_paths={"l1": "untouched", "l2": "fast_path"},
        texts={"l1": "source 1", "l2": "source 2"},
        losses={"word_dropped": 3},
        losses_by_line={"l2": {"word_dropped": 3}},
        word_order_suspected=frozenset({"l2"}),
    )
    base.update(overrides)
    return RewriteResult(**base)


def _render(adapter: _FakeAdapter, tmp_path: Path) -> tuple[Any, ...]:
    doc = _document()
    traces = _traces(doc)
    path = tmp_path / "doc.xml"
    path.write_bytes(_XML)
    events: list[ev.EngineEvent] = []
    losses, files = asyncio.run(
        _render_outputs(
            format_adapter=adapter,
            producer_metadata=ProducerMetadata(name="rules", implementation="v1"),
            config_fingerprint="fp",
            emit=events.append,
            document_manifest=doc,
            source_files={"doc.xml": path},
            traces=traces,
            decisions=derive_decision_set(doc, traces),
        )
    )
    return losses, files, traces, events


def test_every_channel_lands_on_its_trace(tmp_path: Path) -> None:
    _, _, traces, _ = _render(_FakeAdapter(_result()), tmp_path)
    t1 = traces[LineRef(page_id="p1", line_id="l1")]
    t2 = traces[LineRef(page_id="p1", line_id="l2")]

    assert t1.rewriter_path == "untouched"
    assert t2.rewriter_path == "fast_path"
    assert t1.output_alto_text == "source 1"
    assert t2.output_alto_text == "source 2"
    assert t1.projection_fidelity is ProjectionFidelity.EXACT
    # Per-line loss attribution rides the trace, and ONLY for the line that
    # lost something — a zeroed entry everywhere would make the report's
    # projection stage unreadable.
    assert t2.projection_losses == {"word_dropped": 3}
    assert t1.projection_losses is None
    # R5 — a suspected reorder is its own channel, never a loss counter.
    assert t2.word_order_suspected is True
    assert t1.word_order_suspected is not True


def test_losses_aggregate_and_bytes_come_back(tmp_path: Path) -> None:
    losses, files, _, _ = _render(_FakeAdapter(_result()), tmp_path)
    assert losses == {"word_dropped": 3}
    assert files == {"doc.xml": _XML}


def test_rewriter_stats_event_carries_the_metrics(tmp_path: Path) -> None:
    _, _, _, events = _render(_FakeAdapter(_result()), tmp_path)
    stats = [e for e in events if isinstance(e, ev.RewriterStats)]
    assert len(stats) == 1
    assert (stats[0].untouched, stats[0].fast_path) == (1, 1)
    assert stats[0].source_stem == "doc"


def test_a_channel_the_rewrite_left_empty_writes_nothing(tmp_path: Path) -> None:
    """An adapter that reports no losses and no suspicion must leave those
    channels untouched, not fill them with falsy values — the report reads
    ``None`` as "not measured" and ``{}`` as "measured, nothing found"."""
    adapter = _FakeAdapter(
        _result(losses={}, losses_by_line={}, word_order_suspected=frozenset())
    )
    losses, _, traces, _ = _render(adapter, tmp_path)
    assert losses == {}
    for trace in traces.values():
        assert trace.projection_losses is None
        assert trace.word_order_suspected is not True


def test_a_line_the_rewrite_never_mentions_is_a_projection_failure(
    tmp_path: Path,
) -> None:
    """The invariant runs BEFORE the bytes are handed back: a rewrite that
    drops a line is corruption of the deliverable, not a partial success."""
    from lidenbrock.errors import ProjectionError

    adapter = _FakeAdapter(_result(texts={"l1": "source 1"}))
    with pytest.raises(ProjectionError):
        _render(adapter, tmp_path)


def test_a_file_with_no_pages_is_skipped_entirely(tmp_path: Path) -> None:
    """A source file the manifest has no pages for is not rewritten — and
    the adapter is never called for it."""
    doc = _document()
    traces = _traces(doc)
    other = tmp_path / "other.xml"
    other.write_bytes(_XML)
    adapter = _FakeAdapter(_result())
    losses, files = asyncio.run(
        _render_outputs(
            format_adapter=adapter,
            producer_metadata=ProducerMetadata(name="rules", implementation="v1"),
            config_fingerprint="fp",
            emit=lambda _e: None,
            document_manifest=doc,
            source_files={"other.xml": other},
            traces=traces,
            decisions=derive_decision_set(doc, traces),
        )
    )
    assert adapter.calls == []
    assert (losses, files) == ({}, {})
