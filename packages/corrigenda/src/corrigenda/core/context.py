"""All mutable state of ONE pipeline execution.

Lifted out of the orchestrator (S2). It is a VALUE — what a run accumulates
as it goes — not execution control, and keeping it beside the retry loop was
also a circular-import waiting to happen: the report assembly needs to read
this state, and could not import it from the module that imports the report
assembly.

Nothing here survives the run: the public outcome is copied into
:class:`~corrigenda.core.result.CorrectionResult` before returning.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from corrigenda.core.editing import EditOp
from corrigenda.core.hyphenation import ReconcileMetrics
from corrigenda.core.identity import LineRef
from corrigenda.core.schemas import HyphenSplit, PageImage, Usage


@dataclass
class RunContext:
    """All mutable state of ONE pipeline execution.

    Created fresh at the top of every :meth:`CorrectionPipeline.run`
    (together with the run's private manifest copy — ADR-011 slice E)
    and threaded through the internal methods, so ``CorrectionPipeline``
    itself carries only immutable configuration and injected
    dependencies. Nothing here survives the run: the public outcome is
    copied into :class:`CorrectionResult` before returning.

    Not exported: this is internal orchestration state, not API surface.
    """

    #: Retries consumed across every chunk's attempt loop.
    retry_count: int = 0
    #: Chunks (or descent sub-chunks) that fell back to OCR source text.
    fallback_chunks: int = 0
    #: lines the QE router SKIPPED (confirmed clean, no producer
    #: call). 0 when routing is off.
    lines_skipped: int = 0
    #: non-hyphen lines routed to the ``escalation_producer``
    #: (a VLM) instead of the primary producer. 0 when none is set.
    escalated_lines: int = 0
    #: number of ``producer.produce`` invocations across the run,
    #: retries INCLUDED (the real per-call cost driver for an LLM API).
    #: Routing lowers it by dropping whole all-skipped chunks; comparing
    #: routing-on vs routing-off runs on one document is how the hybrid
    #: PROVES it is cheaper.
    producer_calls: int = 0
    #: Per-pair reconciliation outcomes (coherent / fallback / neutralised).
    reconcile_metrics: ReconcileMetrics = field(default_factory=ReconcileMetrics)
    #: Aggregate token consumption across every producer call of the run.
    usage: Usage = field(default_factory=Usage)
    #: §4 — per target line, the producer's ops (a line may carry several,
    #: e.g. one replace_span per occurrence) and the text those ops
    #: produced (pre-guard, pre-reconcile). Consumed by
    #: _build_final_edit_script to emit the ops the run ACTUALLY applied.
    #: Keyed by (page_id, line_id): bare line_ids may legitimately repeat
    #: across FILES (only page_ids are unique document-wide), and a
    #: bare-id key would let the last file's ops overwrite an earlier
    #: file's, corrupting the dry-run edit_script.
    producer_ops: dict[LineRef, tuple[list[EditOp], str]] = field(default_factory=dict)
    #: The run's cooperative cancellation probe, forwarded to producers
    #: via :class:`ProducerOptions` (P3.7) so long I/O can be abandoned.
    should_abort: Callable[[], bool] | None = None
    #: R6 — every forward hyphen link the LINE planner severed this run
    #: (ADR-010 unit SPLIT). Accumulated here because the cut happens deep
    #: in planning, once per page and again per granularity descent, while
    #: the only place it is worth SAYING is the report: a split leaves a
    #: line whose text still ends mid-word with its role reset to NONE, so
    #: it is not a fallback, not an unpaired break, and not a format loss.
    #: It was recorded on the ChunkPlan and read by nobody — the one
    #: deliberately destructive operation in the engine, invisible to the
    #: host.
    hyphen_splits: list[HyphenSplit] = field(default_factory=list)
    #: §4.1 vision envelope — resolved once per run from run(page_images=…).
    image_ref_by_page_id: dict[str, PageImage] = field(default_factory=dict)
    page_dims: dict[str, tuple[int, int]] = field(default_factory=dict)
