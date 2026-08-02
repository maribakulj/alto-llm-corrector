"""Pure correction pipeline.

The pipeline takes a parsed :class:`DocumentManifest`, drives the chunk
planner, asks the injected :class:`EditProducer` for an
:class:`EditScript` per chunk, validates the result, reconciles hyphen
pairs, and renders the corrected XML in memory. It depends only on the
Protocols in :mod:`corrigenda.core.protocols` — no job store, no
FastAPI, no filesystem path manipulation beyond reading source files.
Credentials never reach the pipeline: an LLM's API key lives inside its
producer (see :class:`LLMEditProducer` and the
:meth:`CorrectionPipeline.for_provider` convenience).

Side effects:
  - producer calls via :class:`EditProducer` (LLM HTTP, rules engine, …)
  - Event notifications via :class:`PipelineObserver`

The engine never persists (ADR-011): the corrected artefacts, the §9
report and the run's statistics all travel on
:class:`CorrectionResult`; the caller persists them
(:meth:`CorrectionResult.write`, or its own transaction).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable
from typing import Any
from pathlib import Path

from corrigenda.core.identity import (
    LineRef,
    line_ref,
)
from corrigenda.errors import (
    CorrectionAborted,
    CorrigendaError,
)
from corrigenda.core import events as ev
from corrigenda.core.planner import downgrade_granularity, plan_page
from corrigenda.core.acceptance import (
    _apply_line_acceptance,
)
from corrigenda.core.attempt import _attempt_chunk
from corrigenda.core.batching import _split_for_image_cap
from corrigenda.core.redaction import sanitize_error
from corrigenda.core.context import RunContext
from corrigenda.core.finalize import _finalize_document
from corrigenda.core.indexing import (
    DocumentIndex,
    _cross_page_partners,
    _index_document,
)
from corrigenda.core.preflight import _preflight
from corrigenda.core.rendering import _render_outputs
from corrigenda.core.report import _build_correction_report
from corrigenda.core.routing import _route_and_filter_chunks
from corrigenda.core.traces import _set_trace
from corrigenda.core.reconcile import (
    _build_hyphen_pairs,
    _reconcile_chunk_hyphens,
    _subpage_for_lines,
    _unit_pool,
)
from corrigenda.core.result import CorrectionResult, _build_correction_result
from corrigenda.core.provenance import (
    _build_run_provenance,
    _digest_sources,
)
from corrigenda.core.units import (
    units_containing,
)
from corrigenda.core.protocols import (
    EditProducer,
    FormatAdapter,
    PipelineObserver,
    ProducerMetadata,
    StructuredCompletionClient,
    ProviderPermanentError,
)
from corrigenda.core.quality import (
    DEFAULT_ROUTING_POLICY,
    QEScorer,
    RoutingPolicy,
)
from corrigenda.core.confidence import (
    ConfidenceScorer,
    HeuristicScorer,
)
from corrigenda.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    DEFAULT_CONFIDENCE_POLICY,
    DEFAULT_LOSS_POLICY,
    DEFAULT_PAIRING_POLICY,
    DEFAULT_RETRY_POLICY,
    ChunkGranularity,
    ChunkPlannerConfig,
    ChunkRequest,
    DocumentManifest,
    GuardConfig,
    HyphenRole,
    PageImage,
    LineManifest,
    LineStatus,
    LineTrace,
    ConfidencePolicy,
    LossPolicy,
    ProposalBatch,
    PageManifest,
    PairingPolicy,
    RetryPolicy,
    Usage,
)


class CorrectionPipeline:
    """Pure orchestration of the correction pipeline over an EditProducer.

    Dependencies are injected via the constructor; the pipeline never
    reaches for global state. The instance holds only immutable
    configuration: every run creates a fresh :class:`RunContext` and its
    own deep copy of the input manifest (ADR-011 — the input is never
    modified, the instance is reentrant), and everything the run decided
    is exposed on the final `CorrectionResult` for the caller to persist.

    §5.1 resorption — the pipeline is constructed around an
    :class:`EditProducer`; there is no ``api_key``/``model`` anywhere on
    the pipeline surface. For the common LLM case, use
    :meth:`for_provider`, which wraps a :class:`StructuredCompletionClient` +
    credentials into an ``LLMEditProducer`` and sets the provenance
    labels in one call.
    """

    def __init__(
        self,
        producer: EditProducer,
        observer: PipelineObserver,
        config: ChunkPlannerConfig | None = None,
        retry_policy: RetryPolicy | None = None,
        guard_config: GuardConfig | None = None,
        pairing_policy: PairingPolicy | None = None,
        format_adapter: FormatAdapter | None = None,
        *,
        loss_policy: LossPolicy | None = None,
        producer_metadata: ProducerMetadata | None = None,
        confidence_policy: ConfidencePolicy | None = None,
        confidence_scorers: tuple[ConfidenceScorer, ...] | None = None,
        qe_scorer: QEScorer | None = None,
        routing_policy: RoutingPolicy | None = None,
        escalation_producer: EditProducer | None = None,
    ) -> None:
        self.producer = producer
        self.observer = observer
        self.config = config or ChunkPlannerConfig()
        # F9 — retry ramp / attempt cap / per-chunk budget. Default reproduces
        # the historical temperature ramp (0.0/0.3/0.5) and 3-attempt cap.
        self.retry_policy = retry_policy or DEFAULT_RETRY_POLICY
        # F13 — all anti-migration / acceptance thresholds. Default reproduces
        # the historical constants byte-for-byte.
        self.guard_config = guard_config or DEFAULT_GUARD_CONFIG
        # §11 — provenance only. Hyphen pairing happens at PARSE time, before
        # the pipeline exists; pass the same PairingPolicy you parsed with so
        # the configuration fingerprint stamped into the corrected XML covers
        # every §8.2 policy. The pipeline itself never re-pairs lines.
        self.pairing_policy = pairing_policy or DEFAULT_PAIRING_POLICY
        # ADR-012 — what a run does when projecting a correction would
        # lose format granularity: REPORT (default, historical) counts
        # and attributes; STRICT rejects the unit pre-projection.
        self.loss_policy = loss_policy or DEFAULT_LOSS_POLICY
        # line confidences on the report. DROP
        # (default) computes nothing; REPORT_ONLY fills
        # LineOutcome.confidence via the injected scorers (default: the
        # zero-dependency HeuristicScorer). Deliberately outside the
        # §8.2 composite fingerprint until write_wc unlocks (report-only
        # never affects the corrected XML).
        self.confidence_policy = confidence_policy or DEFAULT_CONFIDENCE_POLICY
        self.confidence_scorers: tuple[ConfidenceScorer, ...] = (
            confidence_scorers
            if confidence_scorers is not None
            else (HeuristicScorer(),)
        )
        # hybrid-selective routing. A line the QE
        # scorer + RoutingPolicy send to SKIP is confirmed clean and
        # never reaches the producer (no LLM call — the economics). Both
        # OFF by default: no scorer, and DEFAULT_ROUTING_POLICY routes
        # every line to LLM, so a default run is byte-identical. A hyphen
        # unit is NEVER skipped (atomicity) — its members always route to
        # the producer. Outside the §8.2 fingerprint until a run actually
        # skips (same rule that held ConfidencePolicy out until write_wc).
        self.qe_scorer = qe_scorer
        self.routing_policy = routing_policy or DEFAULT_ROUTING_POLICY
        # §5.2 bis — the ESCALATE tier's producer.
        # When set AND routing is on, a non-hyphen line the QE scorer +
        # RoutingPolicy send to ESCALATE is corrected by THIS producer (a
        # VLM) instead of the primary text producer, on a per-line basis —
        # the VLM routed only to the lines that earn its cost. None (the
        # default) keeps the historical behaviour: ESCALATE lines go to the
        # primary producer exactly as before, so a default run is
        # byte-identical. A hyphen unit is NEVER escalated (atomicity — a
        # pair split across two producers could not reconcile), so its
        # members always route to the primary producer.
        self.escalation_producer = escalation_producer
        # §3 format seam — None derives the adapter from the MANIFEST's
        # stamped source_format at write time (_adapter_for_format); an
        # injected adapter that contradicts that format is refused at
        # run start. There is no implicit default format.
        self.format_adapter = format_adapter
        # §11 — provenance identity stamped into the corrected XML's
        # processingStep (P3.7-4: ProducerMetadata replaces the bare
        # provider_name/model strings — a rules producer has no "model").
        # Explicit constructor metadata wins; else the producer's own
        # declaration (optional `metadata` attribute, same convention as
        # requires_full_coverage); else anonymous. The pipeline never
        # dials a vendor either way.
        if producer_metadata is None:
            declared = getattr(producer, "metadata", None)
            producer_metadata = (
                declared if isinstance(declared, ProducerMetadata) else None
            )
        self.producer_metadata = producer_metadata or ProducerMetadata()
        # No reentrancy guard (ADR-011 slice E, retiring ADR-005): the
        # instance carries only immutable configuration, every run works
        # on a fresh RunContext plus its own deep copy of the input
        # manifest, so concurrent runs on one instance cannot contaminate
        # each other. The shared observer sees interleaved events under
        # concurrency — inherent to sharing an observer, and the
        # caller's choice.

    @classmethod
    def for_provider(
        cls,
        provider: StructuredCompletionClient,
        *,
        api_key: str,
        model: str,
        provider_name: str = "unknown",
        observer: PipelineObserver,
        config: ChunkPlannerConfig | None = None,
        retry_policy: RetryPolicy | None = None,
        guard_config: GuardConfig | None = None,
        pairing_policy: PairingPolicy | None = None,
        format_adapter: FormatAdapter | None = None,
        loss_policy: LossPolicy | None = None,
        confidence_policy: ConfidencePolicy | None = None,
        confidence_scorers: tuple[ConfidenceScorer, ...] | None = None,
        qe_scorer: QEScorer | None = None,
        routing_policy: RoutingPolicy | None = None,
        system_prompt: str | None = None,
        output_schema: dict[str, Any] | None = None,
        uncertainty_channel: bool = False,
        lexicon: set[str] | None = None,
    ) -> CorrectionPipeline:
        """Build a pipeline around a raw ``StructuredCompletionClient`` (§5.1).

        P3.7 split — the core only requires ``complete_structured``: a
        client with no ``list_models`` is fully supported (model
        discovery is application vocabulary, see ``ModelCatalog``).

        Composition-boundary convenience: wraps the provider + credentials
        + prompt contract into an ``LLMEditProducer`` so callers migrating
        from the legacy ``run(api_key=…, model=…, provider_name=…)`` keep a
        one-call setup. The import is function-local — this is one of the
        two pinned lazy composition defaults the import-contract test
        allows in core (the other is the ALTO format adapter).
        """
        from corrigenda.producers.llm_edit import LLMEditProducer

        producer = LLMEditProducer(
            provider,
            api_key,
            model,
            system_prompt=system_prompt,
            output_schema=output_schema,
            uncertainty_channel=uncertainty_channel,
            lexicon=lexicon,
        )
        return cls(
            producer=producer,
            observer=observer,
            config=config,
            retry_policy=retry_policy,
            guard_config=guard_config,
            pairing_policy=pairing_policy,
            format_adapter=format_adapter,
            loss_policy=loss_policy,
            confidence_policy=confidence_policy,
            confidence_scorers=confidence_scorers,
            qe_scorer=qe_scorer,
            routing_policy=routing_policy,
            # Vendor vocabulary is native HERE (the LLM convenience):
            # the two strings become the generic identity envelope. The
            # producer's configuration fingerprint (prompt + schema)
            # rides along — the explicit envelope overrides IDENTITY,
            # it must not erase configuration provenance (§11).
            producer_metadata=ProducerMetadata(
                name=provider_name,
                implementation=model,
                configuration_fingerprint=producer.metadata.configuration_fingerprint,
            ),
        )

    def config_fingerprint(self) -> str:
        """Stable 16-hex hash over the pipeline's §8.2 policies (§11).

        Public and reproducible from the public API alone: it is the sha256
        (truncated to 16 hex chars) of the sorted JSON object mapping each
        policy name to its ``policy_fingerprint()``::

            {"chunk_planner": …, "guard": …, "loss": …, "pairing": …, "retry": …}

        Covers all five §8.2 policies — RetryPolicy, GuardConfig,
        ChunkPlannerConfig, PairingPolicy and LossPolicy (ADR-012) — so
        the ``processingStep`` stamped into a corrected XML records the
        exact configuration it was produced under, and a consumer holding
        the same policy objects can recompute and verify it.
        """
        payload = json.dumps(
            {
                "chunk_planner": self.config.policy_fingerprint(),
                "guard": self.guard_config.policy_fingerprint(),
                # ADR-012 — decision-affecting (strict rejects units), so
                # it must be part of the provenance like every §8.2 policy.
                "loss": self.loss_policy.policy_fingerprint(),
                "pairing": self.pairing_policy.policy_fingerprint(),
                "retry": self.retry_policy.policy_fingerprint(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _emit(self, event: ev.EngineEvent) -> None:
        """Render a typed event onto the wire-shaped observer port
        (P3.6): the dataclass is the payload's single definition; the
        observer keeps receiving ``(event_type, payload_dict)``."""
        self.observer.on_event(event.type, event.payload())

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        document_manifest: DocumentManifest,
        source_files: dict[str, Path],
        run_id: str | None = None,
        should_abort: Callable[[], bool] | None = None,
        page_images: dict[str, PageImage] | None = None,
    ) -> CorrectionResult:
        """Run the full pipeline. The input manifest is never modified.

        **Immutability & reentrancy (ADR-011 slice E, retiring
        ADR-005)** — the engine works on its own deep copy of
        ``document_manifest``: the input is read, never written, so the
        same document object can be run again (or concurrently) and
        every run starts from the original OCR text. All per-run state
        lives in a fresh :class:`RunContext` plus that copy; the
        instance carries only immutable configuration, so one pipeline
        instance supports concurrent ``run()`` calls (within one event
        loop — instances are still not thread-safe). The run's
        decisions are returned on the result
        (:attr:`CorrectionResult.decisions`), not written back onto the
        caller's manifest.

        §5.1 resorption — there is no ``api_key``/``model``/``provider_name``
        here anymore: credentials and the vendor call live inside the
        injected :class:`EditProducer` (see :meth:`for_provider`), and the
        provenance labels are constructor state.

        ``page_images`` (§5.1) — optional mapping of **page_id** (document-
        unique, ADR-007) to a :data:`PageImage`: the historical opaque
        :data:`ImageRef` (str) or the richer, recommended
        :class:`~corrigenda.core.schemas.ImageAsset` — one image per
        physical page, so a multipage XML carries one ref per scan. The
        library forwards each page's ref verbatim into the producer payload
        when the producer asks (``wants_image``) and NEVER opens it (I4).
        A ``wants_image`` producer run without a complete mapping raises
        :class:`ConfigurationError` before any work starts; a key matching
        no page (e.g. a legacy file-name key) is refused explicitly.

        ``run_id`` is an optional identifier embedded in the emitted
        :class:`CorrectionReport` (which is also what ``trace.json``
        contains) so consumers can correlate the persisted report with
        their own job/request id. Generated as a uuid4 when omitted; it
        never leaks back into the public events.

        ``should_abort`` (F10) is an optional cancellation probe. It is
        polled between pages and between chunks; when it returns ``True``
        the run raises :class:`CorrectionAborted` and no result is
        produced. A provider call already in flight is not interrupted —
        cancellation is cooperative and observed only at chunk/page
        boundaries.

        **Persistence (ADR-011)** — the engine never writes: the
        returned :class:`CorrectionResult` carries the corrected XML
        (:attr:`~CorrectionResult.corrected_files`) and the §9 report,
        and persisting them is the caller's choice —
        :meth:`CorrectionResult.write` for the simple case, or a
        host-owned transaction (like the demo backend's staging writer)
        when the host needs commit/discard semantics.
        """
        # ADR-011 slice E — the working copy IS the run's mutable state;
        # the caller's document stays exactly as parsed.
        return await self._run_impl(
            document_manifest=document_manifest.model_copy(deep=True),
            source_files=source_files,
            run_id=run_id,
            should_abort=should_abort,
            page_images=page_images,
        )

    async def _run_impl(
        self,
        *,
        document_manifest: DocumentManifest,
        source_files: dict[str, Path],
        run_id: str | None,
        should_abort: Callable[[], bool] | None,
        page_images: dict[str, PageImage] | None,
    ) -> CorrectionResult:
        """Body of :meth:`run`, on the run's private manifest copy — the
        sequence and nothing else: refuse what cannot proceed, index,
        correct every page, finalise the decisions, render, report. Each
        step lives in its own module (S2).
        """
        run_id = run_id or str(uuid.uuid4())
        # One fresh context per execution; no per-run state remains on
        # the instance.
        ctx = RunContext(should_abort=should_abort)

        _preflight(
            producer=self.producer,
            escalation_producer=self.escalation_producer,
            format_adapter=self.format_adapter,
            document_manifest=document_manifest,
            page_images=page_images,
            ctx=ctx,
        )

        index = _index_document(document_manifest)
        self._emit(
            ev.DocumentParsed(
                total_pages=document_manifest.total_pages,
                total_lines=document_manifest.total_lines,
                hyphen_pairs=index.hyphen_pairs,
            )
        )

        total_chunks, total_reconciled = await self._process_pages(
            ctx=ctx,
            document_manifest=document_manifest,
            index=index,
            should_abort=should_abort,
        )

        decisions, sidecar_entries = _finalize_document(
            guard_config=self.guard_config,
            loss_policy=self.loss_policy,
            document_manifest=document_manifest,
            all_lines=index.lines,
            traces=index.traces,
        )

        format_losses, corrected_files = await _render_outputs(
            format_adapter=self.format_adapter,
            producer_metadata=self.producer_metadata,
            config_fingerprint=self.config_fingerprint(),
            emit=self._emit,
            document_manifest=document_manifest,
            source_files=source_files,
            traces=index.traces,
            decisions=decisions,
        )

        # P3.9/P3.10 — one digest computation feeds BOTH the provenance
        # record and the final edit script's preconditions.
        source_digests = _digest_sources(source_files)

        report = _build_correction_report(
            run_id=run_id,
            document_manifest=document_manifest,
            decisions=decisions,
            traces=index.traces,
            ctx=ctx,
            provenance=_build_run_provenance(
                producer_metadata=self.producer_metadata,
                escalation_producer=self.escalation_producer,
                config_fingerprint=self.config_fingerprint(),
                document_manifest=document_manifest,
                source_digests=source_digests,
                image_assets=ctx.image_ref_by_page_id,
            ),
            format_losses=format_losses,
            sidecar_entries=sidecar_entries,
            confidence_policy=self.confidence_policy,
            confidence_scorers=self.confidence_scorers,
            all_lines=index.lines,
        )

        return _build_correction_result(
            ctx=ctx,
            decisions=decisions,
            traces=index.traces,
            report=report,
            corrected_files=corrected_files,
            source_digests=source_digests,
            total_chunks=total_chunks,
            total_reconciled=total_reconciled,
        )

    async def _process_pages(
        self,
        *,
        ctx: RunContext,
        document_manifest: DocumentManifest,
        index: DocumentIndex,
        should_abort: Callable[[], bool] | None,
    ) -> tuple[int, int]:
        """Correct every page in manifest order.

        Returns the run's ``(chunks, reconciled pairs)`` totals. Each page
        is given the partners its hyphen units need from other pages: a
        unit straddling a page break is still ONE unit, and the page that
        holds one end cannot resolve it from its own lines (ADR-010).
        """
        total_chunks = 0
        total_reconciled = 0
        for page in document_manifest.pages:
            # F10 — cooperative cancellation between pages, before any work
            # on this page and before any output is written.
            if should_abort is not None and should_abort():
                raise CorrectionAborted(
                    f"run aborted before page {page.page_id!r} (page {page.page_index})"
                )
            page_chunks, page_reconciled = await self._process_page(
                ctx=ctx,
                page=page,
                document_id=document_manifest.document_id,
                traces=index.traces,
                cross_page_partners=_cross_page_partners(page, index.lines),
                should_abort=should_abort,
            )
            total_chunks += page_chunks
            total_reconciled += page_reconciled
        return total_chunks, total_reconciled

    def run_sync(
        self,
        *,
        document_manifest: DocumentManifest,
        source_files: dict[str, Path],
        run_id: str | None = None,
        should_abort: Callable[[], bool] | None = None,
        page_images: dict[str, PageImage] | None = None,
    ) -> CorrectionResult:
        """Synchronous façade over :meth:`run` (§8.1).

        Wraps the coroutine in :func:`asyncio.run` for consumers without an
        event loop (scripts, notebooks, CLIs). Same parameters and return
        value as :meth:`run`. Must NOT be called from within a running
        event loop — ``asyncio.run`` raises ``RuntimeError`` there; use
        ``await pipeline.run(...)`` instead.
        """
        return asyncio.run(
            self.run(
                document_manifest=document_manifest,
                source_files=source_files,
                run_id=run_id,
                should_abort=should_abort,
                page_images=page_images,
            )
        )

    # ------------------------------------------------------------------
    # Per-page orchestration
    # ------------------------------------------------------------------

    async def _process_page(
        self,
        *,
        ctx: RunContext,
        page: PageManifest,
        document_id: str,
        traces: dict[LineRef, LineTrace],
        cross_page_partners: dict[LineRef, LineManifest] | None,
        should_abort: Callable[[], bool] | None = None,
    ) -> tuple[int, int]:
        line_by_id: dict[str, LineManifest] = {lm.line_id: lm for lm in page.lines}

        page_hyphen_pairs = sum(
            1
            for lm in page.lines
            if lm.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
        )
        self._emit(
            ev.PageStarted(
                page_id=page.page_id,
                page_index=page.page_index,
                line_count=len(page.lines),
                hyphen_pair_count=page_hyphen_pairs,
            )
        )

        plan = plan_page(page, document_id, self.config)
        ctx.hyphen_splits.extend(plan.hyphen_splits)

        # hybrid-selective routing: pre-decide SKIP lines
        # (confirmed clean, no producer call) and route ESCALATE lines to
        # the vision producer, returning each chunk paired with the
        # producer that owns it. A no-op when routing is off (default), so
        # every chunk pairs with the primary producer and every existing
        # run is byte-identical.
        routed_chunks = _route_and_filter_chunks(
            qe_scorer=self.qe_scorer,
            routing_policy=self.routing_policy,
            producer=self.producer,
            escalation_producer=self.escalation_producer,
            page=page,
            chunks=plan.chunks,
            line_by_id=line_by_id,
            ctx=ctx,
            traces=traces,
        )

        # a vision producer crops every line it is sent, and
        # providers cap images per call. Split AFTER routing: only the
        # chunks that actually reached a vision producer are constrained.
        routed_chunks = _split_for_image_cap(
            routed=routed_chunks, line_by_id=line_by_id
        )

        self._emit(
            ev.ChunkPlanned(
                page_id=page.page_id,
                chunk_count=len(routed_chunks),
                granularity=plan.granularity.value,
            )
        )

        page_reconciled = 0
        page_chunks = 0

        for chunk, producer in routed_chunks:
            # F10 — cooperative cancellation between chunks. Checked before
            # the per-chunk try/except so CorrectionAborted propagates out
            # instead of being swallowed as a chunk error.
            if should_abort is not None and should_abort():
                raise CorrectionAborted(
                    f"run aborted before chunk {chunk.chunk_id!r} on page "
                    f"{page.page_id!r}"
                )

            page_chunks += 1
            try:
                n = await self._run_chunk(
                    ctx=ctx,
                    chunk=chunk,
                    producer=producer,
                    page=page,
                    line_by_id=line_by_id,
                    traces=traces,
                    cross_page_partners=cross_page_partners,
                    should_abort=should_abort,
                )
                page_reconciled += n
            except (CorrectionAborted, ProviderPermanentError):
                # F10 — cancellation must propagate, never be downgraded
                # to a chunk_error event. ADR-008 — a permanent provider
                # rejection (401/403/404) is fatal for the whole run: it
                # would hit every remaining chunk identically, and
                # converting it into per-chunk OCR fallbacks would let the
                # run END AS A SUCCESS with silently uncorrected text.
                raise
            except Exception as exc:
                # ADR-006: pipeline does not log directly; emit an
                # event the host application can log/trace.
                self._emit(
                    ev.ChunkError(
                        chunk_id=chunk.chunk_id,
                        message=str(exc)[:200],
                        exception_type=type(exc).__name__,
                    )
                )
                # ADR-008 — only RECOVERABLE domain errors may be absorbed as
                # a chunk_error + continue. Anything else (KeyError,
                # AttributeError, a pydantic bug, a broken invariant) is a
                # programming error: continuing would let the run complete
                # "successfully" with lines in an unknown state.
                if not isinstance(exc, CorrigendaError):
                    raise
                # The absorbed error may have interrupted the chunk between
                # its producer attempt and its finalization: any target
                # line still awaiting a decision falls back to its source
                # text NOW. The run may degrade; it may never continue
                # with undecided lines (lines the chunk — or a descent
                # sub-chunk — already finalized keep their decision).
                undecided = [
                    line_by_id[lid]
                    for lid in chunk.targets()
                    if lid in line_by_id
                    and line_by_id[lid].status is LineStatus.PENDING
                ]
                if undecided:
                    # ADR-010 — the absorbed chunk's unit members on OTHER
                    # pages (already corrected or not yet processed) fall
                    # back too: a mixed pair may not survive the absorb.
                    undecided = units_containing(
                        undecided, _unit_pool(line_by_id, cross_page_partners)
                    )
                    reason = sanitize_error(str(exc))[:120]
                    for lm in undecided:
                        lm.corrected_text = lm.ocr_text
                        lm.status = LineStatus.FALLBACK
                        _set_trace(
                            traces,
                            lm,
                            projected_text=lm.ocr_text,
                            validation_status="fallback",
                            fallback_reason=f"chunk_error_absorbed: {reason}",
                        )
                    ctx.fallback_chunks += 1

        # Duplicate detection is no page business anymore: the single
        # document-wide adjacency pass (P3.3) runs after the page loop,
        # comparing every line's live pre-revert correction on one basis —
        # chunk seams, descent sub-chunk seams and page seams included.

        page_corrections = sum(
            1
            for lm in page.lines
            if lm.corrected_text is not None and lm.corrected_text != lm.ocr_text
        )
        self._emit(
            ev.PageCompleted(
                page_id=page.page_id,
                page_index=page.page_index,
                corrections=page_corrections,
                hyphen_pairs_reconciled=page_reconciled,
            )
        )

        return page_chunks, page_reconciled

    # ------------------------------------------------------------------
    # Per-chunk LLM call + reconciliation
    # ------------------------------------------------------------------

    async def _run_chunk(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        producer: EditProducer,
        page: PageManifest,
        line_by_id: dict[str, LineManifest],
        traces: dict[LineRef, LineTrace] | None = None,
        cross_page_partners: dict[LineRef, LineManifest] | None = None,
        budget: list[int] | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> int:
        """Process one chunk through the LLM, with F1 granularity descent.

        On success: reconcile + accept + finalize, return reconciled pairs.

        On retry-budget exhaustion at a granularity coarser than LINE:
        emit ``chunk_downgraded`` and re-plan **this chunk's TARGET lines**
        one granularity finer (PAGE→BLOCK→WINDOW→LINE), retrying each
        sub-chunk. Context lines (F8) are NOT re-planned — they belong to
        an adjacent chunk, and correcting them here at a finer grain would
        steal ownership from the window where their context is maximal.
        Only lines whose LINE-level chunk still fails — or that run out of
        the shared ``RetryPolicy.per_chunk_budget`` (default 6 cumulative
        attempts) — fall back to OCR source. A non-retryable error (e.g.
        HTTP 4xx) skips the descent and falls back immediately: smaller
        chunks would hit the same wall.

        ``budget`` is a 1-element list holding the remaining cumulative
        attempts for this original chunk's whole descent; ``None`` at the
        top level starts a fresh budget. ``should_abort`` (F10) is probed
        before each sub-chunk of the descent — a long PAGE→…→LINE cascade
        stays cancellable.
        """
        chunk_lines = [line_by_id[lid] for lid in chunk.line_ids if lid in line_by_id]
        if not chunk_lines:
            return 0

        if budget is None:
            budget = [self.retry_policy.per_chunk_budget]

        hyphen_pairs = _build_hyphen_pairs(chunk_lines)

        self._emit(
            ev.ChunkStarted(
                chunk_id=chunk.chunk_id,
                granularity=chunk.granularity.value,
                line_count=len(chunk_lines),
            )
        )

        attempts_cap = min(self.retry_policy.max_attempts, max(budget[0], 0))
        outcome = await _attempt_chunk(
            ctx=ctx,
            chunk=chunk,
            producer=producer,
            chunk_lines=chunk_lines,
            hyphen_pairs=hyphen_pairs,
            all_lines_by_id=line_by_id,
            traces=traces,
            max_attempts=attempts_cap,
            retry_policy=self.retry_policy,
            guard_config=self.guard_config,
            emit=self._emit,
        )
        budget[0] -= outcome.attempts_used

        if outcome.response is not None:
            return self._finish_successful_chunk(
                ctx=ctx,
                chunk=chunk,
                chunk_lines=chunk_lines,
                response=outcome.response,
                line_by_id=line_by_id,
                cross_page_partners=cross_page_partners,
                traces=traces,
                usage=outcome.usage,
            )

        # --- Failure: try a granularity descent (F1). ---
        next_g = downgrade_granularity(chunk.granularity)
        if outcome.can_downgrade and next_g is not None and budget[0] > 0:
            return await self._descend_granularity(
                ctx=ctx,
                chunk=chunk,
                next_g=next_g,
                producer=producer,
                page=page,
                chunk_lines=chunk_lines,
                line_by_id=line_by_id,
                traces=traces,
                cross_page_partners=cross_page_partners,
                budget=budget,
                should_abort=should_abort,
                last_msg=outcome.last_msg,
            )

        # --- Terminal fallback (LINE grain, budget gone, or hard error). ---
        self._apply_chunk_fallback(
            chunk=chunk,
            chunk_lines=chunk_lines,
            traces=traces,
            sanitised_msg=outcome.last_msg or "all_attempts_exhausted",
            line_by_id=line_by_id,
            cross_page_partners=cross_page_partners,
        )
        ctx.fallback_chunks += 1
        return 0

    async def _descend_granularity(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        next_g: ChunkGranularity,
        producer: EditProducer,
        page: PageManifest,
        chunk_lines: list[LineManifest],
        line_by_id: dict[str, LineManifest],
        traces: dict[LineRef, LineTrace] | None,
        cross_page_partners: dict[LineRef, LineManifest] | None,
        budget: list[int],
        should_abort: Callable[[], bool] | None,
        last_msg: str,
    ) -> int:
        """Re-plan a failed chunk one granularity finer and retry it (F1).

        F1×F8 — only the chunk's TARGET lines descend. Context lines are
        owned by an adjacent chunk; re-planning them here would correct
        them at a finer grain and make their rightful window skip them
        (acceptance ignores already-corrected lines).

        Returns the pairs reconciled across the whole descent. Sub-chunks
        share the caller's cumulative ``budget``; when it runs out
        mid-descent the remaining ones fall back to OCR source rather than
        borrowing attempts from a chunk that has none left.
        """
        target_ids = set(chunk.targets())
        descent_lines = [lm for lm in chunk_lines if lm.line_id in target_ids]
        self._emit(
            ev.ChunkDowngraded(
                chunk_id=chunk.chunk_id,
                from_granularity=chunk.granularity.value,
                to_granularity=next_g.value,
                line_count=len(chunk_lines),
                target_count=len(descent_lines),
                budget_remaining=budget[0],
            )
        )
        sub_plan = plan_page(
            _subpage_for_lines(page, descent_lines),
            chunk.document_id,
            self.config,
            force_granularity=next_g,
        )
        ctx.hyphen_splits.extend(sub_plan.hyphen_splits)
        total = 0
        for sub in sub_plan.chunks:
            # F10 — the descent can spawn many finest-grain chunks; keep
            # the run cancellable inside it, not only between top-level
            # chunks.
            if should_abort is not None and should_abort():
                raise CorrectionAborted(
                    f"run aborted during granularity descent of chunk "
                    f"{chunk.chunk_id!r} on page {page.page_id!r}"
                )
            if budget[0] <= 0:
                # Budget spent mid-descent: OCR-fallback the rest.
                sub_lines = [
                    line_by_id[lid] for lid in sub.line_ids if lid in line_by_id
                ]
                self._apply_chunk_fallback(
                    chunk=sub,
                    chunk_lines=sub_lines,
                    traces=traces,
                    sanitised_msg=last_msg or "per_chunk_budget exhausted",
                    line_by_id=line_by_id,
                    cross_page_partners=cross_page_partners,
                )
                ctx.fallback_chunks += 1
                continue
            total += await self._run_chunk(
                ctx=ctx,
                chunk=sub,
                producer=producer,
                page=page,
                line_by_id=line_by_id,
                traces=traces,
                cross_page_partners=cross_page_partners,
                budget=budget,
                should_abort=should_abort,
            )
        return total

    def _finish_successful_chunk(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        chunk_lines: list[LineManifest],
        response: ProposalBatch,
        line_by_id: dict[str, LineManifest],
        cross_page_partners: dict[LineRef, LineManifest] | None,
        traces: dict[LineRef, LineTrace] | None,
        usage: Usage | None = None,
    ) -> int:
        """Reconcile / accept / finalize a chunk whose LLM call succeeded.

        F8 — only the chunk's *target* lines are corrected here. Context
        lines (in ``line_ids`` but not ``target_line_ids``) were sent to the
        producer for context but are owned by an adjacent chunk, so their
        output is discarded on this pass.
        """
        # The validated response is already the applied EditScript's output
        # (the producer's ops were normalised and applied in _attempt_chunk,
        # which also accumulated them for CorrectionResult.edit_script).
        text_by_id: dict[str, str] = {
            o.line_id: o.corrected_text for o in response.lines
        }

        target_ids = set(chunk.targets())
        target_lines = [lm for lm in chunk_lines if lm.line_id in target_ids]

        reconciled_count = _reconcile_chunk_hyphens(
            guard_config=self.guard_config,
            emit=self._emit,
            ctx=ctx,
            chunk_id=chunk.chunk_id,
            chunk_lines=target_lines,
            text_by_id=text_by_id,
            line_by_id=line_by_id,
            cross_page_partners=cross_page_partners,
            traces=traces,
        )
        _apply_line_acceptance(
            guard_config=self.guard_config,
            chunk_lines=target_lines,
            text_by_id=text_by_id,
            all_lines_by_id=line_by_id,
            traces=traces,
            cross_page_partners=cross_page_partners,
        )
        self._finalize_chunk_traces(chunk_lines=target_lines, traces=traces)

        self._emit(
            ev.ChunkCompleted(
                chunk_id=chunk.chunk_id,
                line_count=len(chunk_lines),
                target_count=len(target_lines),
                hyphen_pairs_reconciled=reconciled_count,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
            )
        )
        return reconciled_count

    def _apply_chunk_fallback(
        self,
        *,
        chunk: ChunkRequest,
        chunk_lines: list[LineManifest],
        traces: dict[LineRef, LineTrace] | None,
        sanitised_msg: str,
        line_by_id: dict[str, LineManifest] | None = None,
        cross_page_partners: dict[LineRef, LineManifest] | None = None,
    ) -> None:
        """Revert the chunk's TARGET lines to their OCR text and emit a
        ``warning`` event. Mutates ``corrected_text`` / ``status`` /
        line traces. Called once the retry loop exhausts its budget or
        hits a non-retryable error.

        F8 — only target lines are reverted; context lines are owned by an
        adjacent chunk and must not be forced to OCR here.

        ADR-010 (unit fallback atomicity): a fallback covers the WHOLE
        hyphen unit. Intra-page partners of a target are co-targets by
        planner atomicity, so the closure only ever ADDS cross-page
        members — the partner on the other page whose chunk succeeded
        (or has not run yet) is pulled to OCR too, instead of leaving
        the joined word rewritten on one line and verbatim on the other.

        The pipeline-level ``_fallback_chunks`` is bumped by the caller,
        mirroring how ``_retry_count`` is incremented at the retry
        call site — both counters are pipeline-orchestration state, not
        chunk-level side effects.
        """
        self._emit(
            ev.Warning(
                chunk_id=chunk.chunk_id,
                message=f"Fallback to OCR source: {sanitised_msg[:120]}",
            )
        )
        target_ids = set(chunk.targets())
        targets = [lm for lm in chunk_lines if lm.line_id in target_ids]
        for lm in targets:
            lm.corrected_text = lm.ocr_text
            lm.status = LineStatus.FALLBACK
            _set_trace(
                traces,
                lm,
                projected_text=lm.ocr_text,
                validation_status="fallback",
                fallback_reason=f"all_attempts_exhausted: {sanitised_msg[:120]}",
            )
        unit_members = units_containing(
            targets, _unit_pool(line_by_id, cross_page_partners)
        )
        for lm in unit_members:
            if lm.line_id in target_ids:
                continue
            lm.corrected_text = lm.ocr_text
            lm.status = LineStatus.FALLBACK
            _set_trace(
                traces,
                lm,
                projected_text=lm.ocr_text,
                validation_status="fallback",
            )
            if traces is not None:
                trace = traces.get(line_ref(lm))
                if trace is not None and not trace.fallback_reason:
                    trace.fallback_reason = "hyphen_unit_fallback"

    # ------------------------------------------------------------------
    # Chunk helpers extracted from _run_chunk
    # ------------------------------------------------------------------

    def _finalize_chunk_traces(
        self,
        *,
        chunk_lines: list[LineManifest],
        traces: dict[LineRef, LineTrace] | None,
    ) -> None:
        """Project the chunk's post-acceptance state onto the traces
        (when the host opted in by passing a non-None ``traces`` dict).

        Duplicate detection is not chunk business anymore: the single
        document-wide adjacency pass (P3.3) runs after the page loop, so
        the state projected here is provisional until that pass ran.
        """
        for lm in chunk_lines:
            _set_trace(
                traces,
                lm,
                projected_text=(
                    lm.corrected_text if lm.corrected_text is not None else lm.ocr_text
                ),
                validation_status=lm.status.value,
            )

    # ------------------------------------------------------------------
    # Output rendering (rewriter + trace assembly)
    # ------------------------------------------------------------------


# --- public surface ---
__all__ = [
    "sanitize_error",
    "CorrectionResult",
    "CorrectionPipeline",
]
