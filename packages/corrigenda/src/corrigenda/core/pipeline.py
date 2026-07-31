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
import re
import uuid
from collections.abc import Callable
from typing import Any
from pathlib import Path

from corrigenda.core.editing import (
    EditOp,
    EditScript,
    ReplaceLine,
    ReplaceSpan,
    apply_edit_script,
)
from corrigenda.core.hyphenation import (
    enrich_chunk_lines,
)
from corrigenda.core.identity import (
    LineRef,
    ensure_unique_identities,
    ensure_unique_page_ids_across_files,
    line_ref,
)
from corrigenda.errors import (
    ConfigurationError,
    CorrectionAborted,
    CorrigendaError,
)
from corrigenda.core import events as ev
from corrigenda.core.decisions import (
    build_line_outcomes,
    derive_decision_set,
)
from corrigenda.core.planner import downgrade_granularity, plan_page
from corrigenda.core.acceptance import (
    _apply_line_acceptance,
    _global_adjacency_pass,
    _loss_policy_pass,
)
from corrigenda.core.batching import _split_for_image_cap
from corrigenda.core.context import RunContext
from corrigenda.core.projection import _fidelity_counts
from corrigenda.core.rendering import _render_outputs
from corrigenda.core.report import _build_final_edit_script
from corrigenda.core.routing import _route_and_filter_chunks
from corrigenda.core.traces import _set_trace
from corrigenda.core.reconcile import (
    _build_hyphen_pairs,
    _lookup_ref,
    _reconcile_one_pair,
    _subpage_for_lines,
    _unit_pool,
)
from corrigenda.core.result import CorrectionResult
from corrigenda.core.provenance import (
    _dependency_versions,
    _digest_sources,
)
from corrigenda.core.retry import _classify_retry
from corrigenda.core.units import (
    derive_hyphen_groups,
    units_containing,
)
from corrigenda.core.validator import validate_llm_response
from corrigenda.core.protocols import (
    EditProducer,
    FormatAdapter,
    PipelineObserver,
    ProducerMetadata,
    ProducerOptions,
    StructuredCompletionClient,
    ProviderPermanentError,
    ProviderTransientError,
    require_capabilities,
    require_page_images,
)
from corrigenda.core.pairing import (
    backward_partner_ref,
    forward_partner_ref,
    unpaired_break_refs,
    preserve_break_char,
)
from corrigenda.core.quality import (
    DEFAULT_ROUTING_POLICY,
    QEScorer,
    RoutingPolicy,
)
from corrigenda.core.confidence import (
    ConfidenceScorer,
    HeuristicScorer,
    build_line_confidence,
)
from corrigenda.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    DEFAULT_CONFIDENCE_POLICY,
    DEFAULT_LOSS_POLICY,
    DEFAULT_PAIRING_POLICY,
    DEFAULT_RETRY_POLICY,
    ChunkPlannerConfig,
    ChunkRequest,
    CorrectionReport,
    DocumentManifest,
    GuardConfig,
    HyphenRole,
    ImageAsset,
    PageImage,
    LineManifest,
    LineStatus,
    LineTrace,
    ConfidencePolicy,
    LossPolicy,
    ProducerProvenance,
    ProposalBatch,
    CorrectionRequest,
    PageManifest,
    PairingPolicy,
    RetryPolicy,
    RunProvenance,
    Usage,
)

# ADR-008 (revised) — recoverability is an ALLOWLIST. Exactly the two
# families the retry classifier can route are recoverable on the
# producer-attempt path:
#   - ProviderTransientError — transport flakiness a conforming provider
#     wrapped (wrapping is the provider CONTRACT, not a courtesy: the
#     provider-agnostic pipeline cannot name raw httpx/SDK exceptions,
#     so an unwrapped one is indistinguishable from a bug and fails the
#     run rather than degrading to a fake success);
#   - ValueError — the documented malformed-producer-output family
#     (ProposalValidationError, HyphenIntegrityError, json.JSONDecodeError all
#     inherit it; §8.4 keeps them value-shaped for exactly this route).
# Everything else — RuntimeError, KeyError, a pydantic bug, an SDK
# exception nobody classified — fails the run: an unknown exception
# must never become a silently-uncorrected "success".
_RECOVERABLE_ERROR_TYPES: tuple[type[BaseException], ...] = (
    ProviderTransientError,
    ValueError,
)

# Patterns to redact common secret formats in error messages.
# Each pattern captures a prefix in the first group so the redacted
# output keeps human-readable context (e.g. "Bearer ****" instead of
# just "****"). Patterns are applied in order; first match wins.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # HTTP Authorization headers — both schemes
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(Basic\s+)[A-Za-z0-9+/=]+", re.IGNORECASE), r"\1****"),
    # Vendor-prefixed keys (OpenAI sk-, Mistral key-, Anthropic sk-ant-, ...).
    # Hint = 4 chars after the prefix (sk-AAAA****) — stable test contract.
    (re.compile(r"(sk-[A-Za-z0-9_-]{4})\S+"), r"\1****"),
    (re.compile(r"(key-[A-Za-z0-9_-]{4})\S+"), r"\1****"),
    # Generic key=value patterns in query strings / form bodies / JSON.
    # Matches `api_key`, `api-key`, `apikey`, `password`, `secret`, `token`
    # then an optional closing quote (JSON-style "token":), then the
    # separator, then the value. Stops at the next quote/space/delimiter.
    (
        re.compile(
            r"((?:api[_-]?key|password|passwd|secret|token)"
            r"[\"']?\s*[=:]\s*[\"']?)[^\s\"'&,}\]]+",
            re.IGNORECASE,
        ),
        r"\1****",
    ),
    # Custom HTTP headers: x-api-key, x-auth-token, ...
    (
        re.compile(
            r"(x-(?:api-key|auth-token|access-token)\s*[:=]\s*)\S+",
            re.IGNORECASE,
        ),
        r"\1****",
    ),
)


#: Critical dependencies recorded on the run's provenance (P3.9, §11).
#: Versions come from package METADATA (importlib.metadata), never from
#: an import — the pure core stays lxml-free by construction.


def sanitize_error(msg: str, api_key: str | None = None) -> str:
    """Strip API keys and common secret patterns from an error message.

    The caller can supply the exact ``api_key`` for first-pass redaction;
    any remaining secret-shaped substrings are then masked by the
    pattern set above. Patterns cover:
      - HTTP ``Authorization: Bearer …`` and ``Basic …`` headers
      - Vendor-prefixed keys (``sk-…``, ``key-…``)
      - Generic ``api_key=…``, ``password=…``, ``token=…`` pairs
      - Custom headers (``X-Api-Key:``, ``X-Auth-Token:``, …)
    """
    if api_key and len(api_key) > 8 and api_key in msg:
        msg = msg.replace(api_key, api_key[:4] + "****")
    for pattern, replacement in _SECRET_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


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

    @staticmethod
    def _record_reconcile_outcome(ctx: RunContext, outcome: str) -> None:
        """Bump the run's ReconcileMetrics counter for a single pair."""
        if outcome == "coherent":
            ctx.reconcile_metrics.coherent += 1
        elif outcome == "fallback":
            ctx.reconcile_metrics.fallback += 1
        elif outcome == "neutralised":
            ctx.reconcile_metrics.neutralised += 1

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
        """Body of :meth:`run`, working on the run's private manifest copy."""
        run_id = run_id or str(uuid.uuid4())
        # One fresh context per execution; no per-run state remains on
        # the instance.
        ctx = RunContext(should_abort=should_abort)

        # §5.1 — a vision producer without its images is a start-up error,
        # never a silent image-less call.
        require_page_images(self.producer, document_manifest.pages, page_images)
        # §5.2 bis — a producer whose declared capabilities
        # contradict its wiring (wants images but vision=False) is a
        # start-up error, not a mid-run surprise.
        require_capabilities(self.producer)
        # the escalation (vision) producer is the one that needs
        # images: preflight it too, so a run that WILL escalate fails at
        # start-up if its VLM lacks a scan, never mid-run.
        if self.escalation_producer is not None:
            require_page_images(
                self.escalation_producer, document_manifest.pages, page_images
            )
            require_capabilities(self.escalation_producer)

        # §3 — the format travels with the document. An injected adapter
        # that contradicts the format the manifest was parsed as would
        # only surface at write time (as a confusing projection failure);
        # refuse it before any correction work is spent. Adapters without
        # a ``format_name`` (custom implementations) are trusted as-is.
        declared = document_manifest.source_format
        adapter_format = getattr(self.format_adapter, "format_name", None)
        if declared and adapter_format and declared != adapter_format:
            raise ConfigurationError(
                f"the injected format_adapter writes {adapter_format!r} but "
                f"the manifest was parsed as {declared!r} — parse with the "
                "matching corrigenda parser or inject the matching adapter"
            )

        # ADR-007 — identity-uniqueness invariant, enforced at the pipeline
        # door so hand-built manifests get the same guarantee as
        # parser-built ones: within one source file every page/block/line
        # ID must be unique (correction-to-line association is keyed by
        # bare line_id per file), and page_ids must be unique across the
        # whole document (trace keys, per-page image/dimension lookups).
        pages_by_file: dict[str, list[PageManifest]] = {}
        for page in document_manifest.pages:
            pages_by_file.setdefault(page.source_file, []).append(page)
        for src_name, src_pages in pages_by_file.items():
            ensure_unique_identities(src_pages, src_name)
        ensure_unique_page_ids_across_files(document_manifest.pages)
        # §4.1 — per-page vision envelope lookups. Pure copying: the
        # ImageRef stays an opaque string end to end. A key matching no
        # page is refused: it is almost always a legacy file-name key
        # from the pre-page_images contract, silently dropping it would
        # reproduce the old wrong-image behaviour.
        images = page_images or {}
        known_pages = {page.page_id for page in document_manifest.pages}
        unknown = sorted(set(images) - known_pages)
        if unknown:
            raise ConfigurationError(
                f"page_images keys must be page ids; {unknown} match no "
                "page of this document (file-name keys are no longer "
                "accepted — pass one ImageRef per page_id)"
            )
        ctx.image_ref_by_page_id = dict(images)
        ctx.page_dims = {
            page.page_id: (page.page_width, page.page_height)
            for page in document_manifest.pages
        }

        total_hyphen_pairs = sum(
            sum(
                1
                for lm in page.lines
                if lm.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
            )
            for page in document_manifest.pages
        )

        self._emit(
            ev.DocumentParsed(
                total_pages=document_manifest.total_pages,
                total_lines=document_manifest.total_lines,
                hyphen_pairs=total_hyphen_pairs,
            )
        )

        # Initialize line traces
        traces: dict[LineRef, LineTrace] = {}
        for page in document_manifest.pages:
            for lm in page.lines:
                traces[line_ref(lm)] = LineTrace(
                    line_id=lm.line_id,
                    page_id=lm.page_id,
                    source_ocr_text=lm.ocr_text,
                    hyphen_role=lm.hyphen_role.value,
                )

        # Global page-qualified registry for cross-page partner lookups
        all_lines_global: dict[LineRef, LineManifest] = {}
        for page in document_manifest.pages:
            for lm in page.lines:
                all_lines_global[line_ref(lm)] = lm

        total_chunks = 0
        total_reconciled = 0

        for page in document_manifest.pages:
            # F10 — cooperative cancellation between pages, before any work
            # on this page and before any output is written.
            if should_abort is not None and should_abort():
                raise CorrectionAborted(
                    f"run aborted before page {page.page_id!r} (page {page.page_index})"
                )

            # Cross-page partners needed by this page's lines
            cross_page: dict[LineRef, LineManifest] = {}
            for lm in page.lines:
                for partner_id, partner_page in (
                    (lm.hyphen_pair_line_id, lm.hyphen_pair_page_id),
                    (lm.hyphen_forward_pair_id, lm.hyphen_forward_pair_page_id),
                ):
                    if not partner_id or not partner_page:
                        continue
                    if partner_page == page.page_id:
                        continue
                    partner = all_lines_global.get(
                        LineRef(page_id=partner_page, line_id=partner_id)
                    )
                    if partner is not None:
                        cross_page[
                            LineRef(page_id=partner_page, line_id=partner_id)
                        ] = partner

            page_chunks, page_reconciled = await self._process_page(
                ctx=ctx,
                page=page,
                document_id=document_manifest.document_id,
                traces=traces,
                cross_page_partners=cross_page if cross_page else None,
                should_abort=should_abort,
            )
            total_chunks += page_chunks
            total_reconciled += page_reconciled

        # P3.3 — ONE document-wide consistency pass. Chunk finalization no
        # longer reverts duplicates, so every line still holds its
        # PRE-REVERT accepted correction here: the pass compares live
        # corrected_text over the canonical reading order on one basis,
        # and extends rejections to whole hyphen units through THE
        # derivation (ADR-010). Replaces three partial sweeps — the
        # intra-chunk sweep, the cross-chunk boundary pass and the
        # page-seam pass — that each carried their own comparison base.
        _global_adjacency_pass(
            guard_config=self.guard_config,
            document_manifest=document_manifest,
            all_lines=all_lines_global,
            traces=traces,
        )

        # ADR-012 — STRICT loss policy: a correction that cannot project
        # without losing word granularity is rejected HERE, before the
        # decisions materialize and before any output exists — the unit
        # falls back to source text and the source markup keeps its
        # Word geometry (the rewrite sees an untouched line).
        # P5, decision-side (found by the OCR17+ corpus, 2026-07-23): if
        # the SOURCE line ends in a word-break character and the accepted
        # correction ends in a DIFFERENT one, force the source's char
        # BEFORE decisions materialize — historically the PAGE rewriter
        # enforced this after the decision was recorded, so the artefact
        # diverged from the decision and _verify_projection raised.
        for page in document_manifest.pages:
            for lm in page.lines:
                if lm.corrected_text is not None and lm.corrected_text != lm.ocr_text:
                    # The proposal stage in the traces keeps the
                    # producer's RAW text (auditability); only the
                    # decided text is normalized.
                    lm.corrected_text = preserve_break_char(
                        lm.ocr_text, lm.corrected_text
                    )

        sidecar_entries = _loss_policy_pass(
            loss_policy=self.loss_policy,
            document_manifest=document_manifest,
            all_lines=all_lines_global,
            traces=traces,
        )

        # ADR-011 — materialize the run's decisions. Refuses a PENDING
        # line (the run-level terminality backstop): outputs exist only
        # for a document where every line carries a terminal decision.
        decisions = derive_decision_set(document_manifest, traces)

        format_losses, corrected_files = await _render_outputs(
            format_adapter=self.format_adapter,
            producer_metadata=self.producer_metadata,
            config_fingerprint=self.config_fingerprint(),
            emit=self._emit,
            document_manifest=document_manifest,
            source_files=source_files,
            traces=traces,
            decisions=decisions,
        )

        # P3.9/P3.10 — one digest computation feeds BOTH the provenance
        # record and the final edit script's preconditions.
        source_digests = _digest_sources(source_files)

        report = CorrectionReport(
            run_id=run_id,
            total_lines=len(decisions.decisions),
            # P3.5 / ADR-011 slice C — the report builder reads the
            # DecisionSet (terminal stage) + the working traces
            # (proposal/projection stages), staged per line (§9 v2).
            lines=build_line_outcomes(decisions, traces),
            # ADR-011 — the rewrite's granularity-loss counters surface on
            # the report. None when no MARKUP was dropped (or nothing was
            # written) — never read as "the run lost nothing": a flattened
            # character is counted on the fidelity scale below (R8).
            format_losses=format_losses or None,
            # How faithfully each rewritten line carries its decision,
            # counted by level. A non-zero "normalized" is the run telling
            # its host that a significant whitespace character did not
            # survive the format — the thing the invariant used to compare
            # away before anyone could count it.
            projection_fidelity=_fidelity_counts(traces) or None,
            # A break whose partner this run never found: silent until now,
            # and not the same thing as a fallback — the line WAS corrected,
            # just alone and without its pair-drift guards.
            unpaired_breaks=len(unpaired_break_refs(document_manifest.pages)) or None,
            # R6 — the units this run CUT to fit the request cap. Distinct
            # from unpaired_breaks: there the link was never there, here the
            # engine severed one on purpose, and the split resets the tail's
            # role to NONE so it cannot show up in that count either.
            hyphen_splits=ctx.hyphen_splits or None,
            # P3.9 (§11) — the run's full provenance record.
            provenance=self._build_provenance(
                document_manifest=document_manifest,
                source_digests=source_digests,
                image_assets=ctx.image_ref_by_page_id,
            ),
            # F14/§11 — the aggregated usage is part of the persisted
            # artefact, not just the transient result. None when nothing
            # was reported: a zero Usage would be indistinguishable from
            # "the provider reported zero tokens".
            usage=(
                ctx.usage if ctx.usage.total_tokens or ctx.usage.response_ids else None
            ),
            # corrections the token_realign gate refused to
            # project, preserved for review instead of lost.
            sidecar=sidecar_entries or None,
        )

        # line confidences (report-only; write_wc stays locked
        # until calibration). Filled AFTER the report is built so every
        # outcome scores its FINAL decided text, whatever path decided it.
        if self.confidence_policy.mode != "drop":
            for outcome in report.lines:
                ref = LineRef(page_id=outcome.page_id, line_id=outcome.line_id)
                scored_line = all_lines_global.get(ref)
                # The producer's verified self-assessment rides the
                # captured ops (uncertainty channel); min over a line's
                # ops when several declared one.
                producer_conf: float | None = None
                captured_line = ctx.producer_ops.get(ref)
                if captured_line is not None:
                    declared_confidences: list[float] = [
                        pc
                        for op in captured_line[0]
                        if (pc := getattr(op, "producer_confidence", None)) is not None
                    ]
                    if declared_confidences:
                        producer_conf = min(declared_confidences)
                outcome.confidence = build_line_confidence(
                    source_text=outcome.source_text,
                    final_text=outcome.decision.final_text,
                    ocr_confidence=(
                        scored_line.ocr_confidence if scored_line is not None else None
                    ),
                    producer_confidence=producer_conf,
                    scorers=self.confidence_scorers,
                )

        # Line-level fallback accounting, read from the DecisionSet
        # (ADR-011): it covers every path that leaves a line at its OCR
        # text (chunk fallback, guard rejection, duplicate revert), not
        # just chunks whose attempts were exhausted.
        return CorrectionResult(
            total_chunks=total_chunks,
            total_reconciled=total_reconciled,
            retry_count=ctx.retry_count,
            fallback_chunks=ctx.fallback_chunks,
            fallback_lines=decisions.fallback_lines,
            fallback_reasons=decisions.fallback_reason_counts(),
            traces=traces,
            reconcile_metrics=ctx.reconcile_metrics,
            usage=ctx.usage,
            report=report,
            edit_script=_build_final_edit_script(
                decisions, ctx, source_digests=source_digests
            ),
            decisions=decisions,
            corrected_files=corrected_files,
            # routing economics: lines skipped (no producer
            # call) and the run's total producer-call count.
            lines_skipped=ctx.lines_skipped,
            # lines routed to the escalation (vision) producer.
            escalated_lines=ctx.escalated_lines,
            producer_calls=ctx.producer_calls,
        )

    def _build_provenance(
        self,
        *,
        document_manifest: DocumentManifest,
        source_digests: dict[str, str],
        image_assets: dict[str, PageImage],
    ) -> RunProvenance:
        """The run's §11 provenance record (P3.9): library + producer
        identity, policy fingerprint, per-file digests of the INPUT
        bytes (computed once in :meth:`run` via ``_digest_sources`` and
        shared with the edit script's preconditions), per-page image
        digests, and critical dependency versions."""
        from corrigenda import __version__ as _lib_version

        md = self.producer_metadata
        # copy the digest each structured ImageAsset already
        # carries; the core never opens an image (I4). Bare ImageRef
        # strings and digest-less assets contribute nothing.
        image_digests = {
            page_id: f"sha256:{asset.sha256}"
            for page_id, asset in image_assets.items()
            if isinstance(asset, ImageAsset) and asset.sha256
        }
        # record the escalation (vision) producer's identity too,
        # from its own declared metadata (the same optional-attribute
        # convention as the primary producer's). None for a single-producer
        # run, so text-only provenance is unchanged.
        escalation_prov: ProducerProvenance | None = None
        if self.escalation_producer is not None:
            emd = (
                getattr(self.escalation_producer, "metadata", None)
                or ProducerMetadata()
            )
            escalation_prov = ProducerProvenance(
                name=emd.name,
                version=emd.version,
                implementation=emd.implementation,
                configuration_fingerprint=emd.configuration_fingerprint,
            )
        return RunProvenance(
            lib_version=_lib_version,
            config_fingerprint=self.config_fingerprint(),
            producer=ProducerProvenance(
                name=md.name,
                version=md.version,
                implementation=md.implementation,
                configuration_fingerprint=md.configuration_fingerprint,
            ),
            escalation_producer=escalation_prov,
            source_digests=source_digests,
            image_digests=image_digests,
            source_format=document_manifest.source_format,
            dependencies=_dependency_versions(),
        )

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
        (
            response,
            attempts_used,
            can_downgrade,
            last_msg,
            usage,
        ) = await self._attempt_chunk(
            ctx=ctx,
            chunk=chunk,
            producer=producer,
            chunk_lines=chunk_lines,
            hyphen_pairs=hyphen_pairs,
            all_lines_by_id=line_by_id,
            traces=traces,
            max_attempts=attempts_cap,
        )
        budget[0] -= attempts_used

        if response is not None:
            return self._finish_successful_chunk(
                ctx=ctx,
                chunk=chunk,
                chunk_lines=chunk_lines,
                response=response,
                line_by_id=line_by_id,
                cross_page_partners=cross_page_partners,
                traces=traces,
                usage=usage,
            )

        # --- Failure: try a granularity descent (F1). ---
        next_g = downgrade_granularity(chunk.granularity)
        if can_downgrade and next_g is not None and budget[0] > 0:
            # F1×F8 — only the chunk's TARGET lines descend. Context lines
            # are owned by an adjacent chunk; re-planning them here would
            # correct them at a finer grain and make their rightful window
            # skip them (acceptance ignores already-corrected lines).
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
                # F10 — the descent can spawn many finest-grain chunks;
                # keep the run cancellable inside it, not only between
                # top-level chunks.
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

        # --- Terminal fallback (LINE grain, budget gone, or hard error). ---
        self._apply_chunk_fallback(
            chunk=chunk,
            chunk_lines=chunk_lines,
            traces=traces,
            sanitised_msg=last_msg or "all_attempts_exhausted",
            line_by_id=line_by_id,
            cross_page_partners=cross_page_partners,
        )
        ctx.fallback_chunks += 1
        return 0

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

        reconciled_count = self._reconcile_chunk_hyphens(
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

    async def _attempt_chunk(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        producer: EditProducer,
        chunk_lines: list[LineManifest],
        hyphen_pairs: dict[str, str],
        all_lines_by_id: dict[str, LineManifest],
        traces: dict[LineRef, LineTrace] | None,
        max_attempts: int,
    ) -> tuple[ProposalBatch | None, int, bool, str, Usage | None]:
        """Call the edit producer with retries; return the outcome.

        Returns ``(response, attempts_used, can_downgrade, last_msg, usage)``:
          - ``response`` — the validated :class:`ProposalBatch`, or ``None``
            on failure;
          - ``attempts_used`` — how many attempts this call consumed
            (charged against the per-chunk budget by the caller);
          - ``can_downgrade`` — on failure, ``True`` when the terminal
            error was retryable (malformed output / transient) and hence
            worth retrying at a finer granularity (F1); ``False`` for a
            non-retryable hard error (e.g. 4xx), which won't heal on
            smaller chunks;
          - ``last_msg`` — the sanitised terminal error message.

        This method NEVER applies the OCR fallback — that decision (and
        the ``warning`` event) belongs to the caller (:meth:`_run_chunk`),
        which may instead downgrade the granularity.

        Retry strategy (F9): up to ``max_attempts`` attempts (bounded by
        the caller to the remaining budget); temperature from
        ``retry_policy.temperatures`` (default 0.0 → 0.3 → 0.5), pinned at
        0.0 after a ``HyphenIntegrityError``; backoff 0 s for the first
        hyphen violation, ``attempt * transient_backoff_base`` for
        transient HTTP, ``attempt * output_backoff_base`` for other
        malformed output. Each retry emits a ``retry`` event.
        """
        hyphen_violation = False
        attempts_used = 0
        last_msg = ""
        # F14 — token usage accumulated across EVERY call of this chunk's
        # attempt loop, including calls whose response later failed
        # validation (tokens were spent regardless). Returned on success so
        # the chunk_completed event reports the chunk's true total, not
        # just the final successful call.
        chunk_usage = Usage()

        for attempt in range(1, max_attempts + 1):
            attempts_used = attempt
            # F9 — temperature comes from the injected RetryPolicy. A hyphen
            # violation still pins the next attempt to 0.0 (the LLM mishandled
            # the pair; a colder attempt sticks closer to source).
            if hyphen_violation:
                temperature = 0.0
            else:
                temperature = self.retry_policy.temperature_for(attempt)

            # §4.1 — vision envelope, copied only when the producer asks.
            enriched = enrich_chunk_lines(
                chunk_lines,
                all_lines_by_id,
                include_geometry=getattr(producer, "wants_geometry", False),
                page_dims=ctx.page_dims,
            )

            enriched_by_id = {e.line_id: e for e in enriched}
            for lm in chunk_lines:
                ei = enriched_by_id.get(lm.line_id)
                if ei is not None:
                    _set_trace(traces, lm, model_input_text=ei.ocr_text)

            payload = CorrectionRequest(
                granularity=chunk.granularity,
                document_id=chunk.document_id,
                page_id=chunk.page_id,
                block_id=chunk.block_id,
                lines=enriched,
                image_ref=(
                    ctx.image_ref_by_page_id.get(chunk.page_id)
                    if getattr(producer, "wants_image", False)
                    else None
                ),
            )

            try:
                # P3.7 — the producer gets a per-call envelope, not the
                # engine's whole RetryPolicy: the ramp (and the hyphen
                # 0.0 pin) is decided HERE; the probe lets long I/O be
                # abandoned mid-flight.
                # count every invocation (this attempt hits the
                # producer whether or not it succeeds): the real cost.
                ctx.producer_calls += 1
                script, usage = await producer.produce(
                    payload,
                    options=ProducerOptions(
                        attempt=attempt,
                        temperature=temperature,
                        should_abort=ctx.should_abort,
                    ),
                )
                raw = self._script_to_raw(script, chunk_lines, producer=producer)
                if usage is not None:
                    ctx.usage = ctx.usage + usage
                    chunk_usage = chunk_usage + usage

                lm_by_id = {lm.line_id: lm for lm in chunk_lines}
                raw_lines = raw.get("lines", []) if isinstance(raw, dict) else []
                for rl in raw_lines:
                    if not isinstance(rl, dict):
                        continue
                    target = lm_by_id.get(rl.get("line_id", ""))
                    if target is not None:
                        _set_trace(
                            traces,
                            target,
                            model_corrected_text=rl.get("corrected_text", ""),
                        )

                hyphen_subs: dict[str, str] = {}
                for lm in chunk_lines:
                    if lm.hyphen_role == HyphenRole.PART1 and lm.hyphen_subs_content:
                        hyphen_subs[lm.line_id] = lm.hyphen_subs_content
                    elif (
                        lm.hyphen_role == HyphenRole.BOTH
                        and lm.hyphen_forward_subs_content
                    ):
                        hyphen_subs[lm.line_id] = lm.hyphen_forward_subs_content

                response = validate_llm_response(
                    raw,
                    [lm.line_id for lm in chunk_lines],
                    hyphen_pairs if hyphen_pairs else None,
                    {lm.line_id: lm.ocr_text for lm in chunk_lines},
                    hyphen_subs if hyphen_subs else None,
                    guard_config=self.guard_config,
                    # F8 — the 1:1 count is enforced on targets; a missing
                    # context line's output is not an error (it belongs to
                    # an adjacent chunk).
                    target_line_ids=chunk.target_line_ids,
                )
                # §4 — capture each TARGET line's producer op alongside the
                # text that op produced (pre-guard, pre-reconcile). The final
                # EditScript is NOT emitted from here: a line later reverted
                # (duplicate / rejected by check_line) or reconciled to
                # different text must not leave a stale op behind (a
                # dry-run consumer replaying it would diverge from the
                # pipeline's own corrected XML). _build_final_edit_script
                # reconciles these captured ops against the FINAL per-line
                # state, preserving the producer's op TYPE (e.g. a rules
                # producer's replace_span) when its output survived unchanged.
                target_ids = set(chunk.targets())
                produced_by_line = {o.line_id: o.corrected_text for o in response.lines}
                ops_by_line: dict[str, list[EditOp]] = {}
                for op in script.ops:
                    if op.line_id in target_ids and op.line_id in produced_by_line:
                        ops_by_line.setdefault(op.line_id, []).append(op)
                for line_id, line_ops in ops_by_line.items():
                    # Chunks are page-scoped, so chunk.page_id qualifies
                    # every target line unambiguously.
                    ctx.producer_ops[
                        LineRef(page_id=chunk.page_id, line_id=line_id)
                    ] = (
                        line_ops,
                        produced_by_line[line_id],
                    )
                return response, attempts_used, False, "", chunk_usage

            except ProviderPermanentError:
                # ADR-008 — credentials/model rejected: retrying is pointless
                # and falling back would fake success. Fatal for the run.
                raise
            except Exception as exc:
                # ADR-008 (attempt-path branch, revised): only the
                # allowlisted recoverable families degrade to
                # retry-then-OCR-fallback. Anything else — a programming
                # error, an unwrapped SDK transport exception, a broken
                # invariant — FAILS the run: masking it as uncorrected OCR
                # text would degrade EVERY chunk while still reporting
                # success. Providers signal transport flakiness by
                # wrapping it as ProviderTransientError (their contract).
                if not isinstance(exc, _RECOVERABLE_ERROR_TYPES):
                    raise
                # §5.1 — the pipeline no longer holds credentials; the
                # pattern-based redaction still masks secret-shaped
                # substrings a producer may leak into the message, and the
                # consumer layer (which DOES hold the key) sanitises again
                # on its own error paths.
                msg = sanitize_error(str(exc))
                last_msg = msg
                decision = _classify_retry(
                    exc=exc,
                    sanitised_msg=msg,
                    attempt=attempt,
                    hyphen_already_seen=hyphen_violation,
                    policy=self.retry_policy,
                )

                if attempt < max_attempts and decision.is_retryable:
                    if decision.is_hyphen_violation:
                        hyphen_violation = True
                    if decision.backoff > 0:
                        await asyncio.sleep(decision.backoff)
                    self._emit(
                        ev.Retry(
                            chunk_id=chunk.chunk_id,
                            attempt=attempt,
                            error=decision.error_tag,
                        )
                    )
                    ctx.retry_count += 1
                    continue

                # Attempts exhausted (or non-retryable error class). Do NOT
                # fall back here — the caller decides between a granularity
                # downgrade (F1) and the OCR fallback. ``can_downgrade`` is
                # True only when the terminal error was retryable.
                return None, attempts_used, decision.is_retryable, msg, None

        # max_attempts <= 0 (no budget left): nothing attempted.
        return None, attempts_used, False, last_msg, None

    def _script_to_raw(
        self,
        script: EditScript,
        chunk_lines: list[LineManifest],
        *,
        producer: EditProducer,
    ) -> dict[str, Any]:
        """Normalise a producer's EditScript into the validator's raw shape.

        - ``replace_line`` ops pass through as-is (duplicates and empty
          texts included — the validator's structural checks must see them
          exactly as the historical raw response did).
        - ``replace_span`` ops are normalised and applied against the
          chunk's canonical text via :func:`apply_edit_script` (E1–E5); a
          rejected op leaves its line uncovered.
        - When the producer declares ``requires_full_coverage = False``
          (deterministic producers: no op == no edit), uncovered lines are
          filled with their canonical text so the validator's 1:1 check
          passes. An LLM producer keeps full-coverage semantics: a dropped
          target line stays missing → ProposalValidationError → retry.
        """
        canonical = {lm.line_id: lm.ocr_text for lm in chunk_lines}
        entries: list[dict[str, str]] = []

        span_ops = [op for op in script.ops if isinstance(op, ReplaceSpan)]
        for op in script.ops:
            if isinstance(op, ReplaceLine):
                entries.append({"line_id": op.line_id, "corrected_text": op.text})
        if span_ops:
            span_result = apply_edit_script(
                EditScript(ops=list(span_ops)),
                canonical,
                chunk_line_ids=set(canonical),
                guard_config=self.guard_config,
                line_by_id={lm.line_id: lm for lm in chunk_lines},
            )
            for lid, txt in span_result.text_by_id.items():
                entries.append({"line_id": lid, "corrected_text": txt})

        if not getattr(producer, "requires_full_coverage", True):
            covered = {e["line_id"] for e in entries}
            for lid, txt in canonical.items():
                if lid not in covered:
                    entries.append({"line_id": lid, "corrected_text": txt})

        return {"lines": entries}

    # ------------------------------------------------------------------
    # Chunk helpers extracted from _run_chunk
    # ------------------------------------------------------------------

    def _reconcile_chunk_hyphens(
        self,
        *,
        ctx: RunContext,
        chunk_id: str,
        chunk_lines: list[LineManifest],
        text_by_id: dict[str, str],
        line_by_id: dict[str, LineManifest],
        cross_page_partners: dict[LineRef, LineManifest] | None,
        traces: dict[LineRef, LineTrace] | None = None,
    ) -> int:
        """Unit-driven hyphen reconciliation (ADR-010).

        The chunk's target lines and their resolved partners are handed
        to THE derivation (:func:`derive_hyphen_groups`), and each unit's
        joins are then reconciled with one walk in reading order —
        replacing the historical two role-keyed passes (PART1→partner,
        then BOTH→forward) that re-derived the grouping from pointer
        fields at every step. A join is owned by its TAIL: it reconciles
        here iff the tail is one of this chunk's targets (the partner may
        be a context line, another chunk's line, or a cross-page member),
        so the derived groups are the unit AS THIS CHUNK SEES IT — a
        member two hops away contributes nothing and is simply absent.

        **A join that leaves the page is owned by its HEAD instead** (L3).
        Tail-ownership is unreachable there: the tail always sits on the
        earlier page and is decided before the head exists, so the tail's
        pass read the head's text out of a response that never mentioned
        it, fell back to raw OCR, and wrote that as the head's decision
        with ``status = CORRECTED``. The later page then skipped the line
        (``corrected_text is not None``) and threw away the correction it
        had just paid for. The head is the only point at which both sides
        exist, so the head claims it.

        Returns the number of joins successfully reconciled. Emits a
        ``hyphen_partner_missing`` event for each unresolvable partner
        so observers can surface the diagnostic.
        """
        # 1. Collect the joins this chunk owns. Outgoing ones (this line
        #    continues onto another) unless they leave the page; incoming
        #    ones (another line continues onto this one) only when they
        #    do. Every join is therefore owned exactly once, by whichever
        #    side can see both members.
        joins: dict[LineRef, tuple[LineManifest, LineManifest, bool]] = {}
        pool: dict[LineRef, LineManifest] = {line_ref(lm): lm for lm in chunk_lines}

        def _claim(tail: LineManifest, head: LineManifest) -> None:
            pool[line_ref(tail)] = tail
            pool[line_ref(head)] = head
            # ``is_forward`` names the SLOT the tail links through, and
            # only a BOTH tail uses its FORWARD slot (see pairing.py).
            joins[line_ref(tail)] = (
                tail,
                head,
                tail.hyphen_role == HyphenRole.BOTH,
            )

        for lm in chunk_lines:
            # The role→slot map is NOT re-derived here. It used to be, in
            # a ternary two lines long, sitting beside a helper that
            # already owned it — and "forward" naming the SLOT rather
            # than the direction is exactly the kind of thing a second
            # copy gets subtly wrong (ADR-010).
            out_ref = forward_partner_ref(lm)
            if out_ref is not None and out_ref.page_id == lm.page_id:
                head = _lookup_ref(
                    out_ref,
                    page_id=lm.page_id,
                    line_by_id=line_by_id,
                    cross_page_partners=cross_page_partners,
                )
                if head is None:
                    self._emit(
                        ev.HyphenPartnerMissing(
                            chunk_id=chunk_id,
                            line_id=lm.line_id,
                            missing_partner_id=out_ref.line_id,
                            direction=(
                                "forward"
                                if lm.hyphen_role == HyphenRole.BOTH
                                else "backward"
                            ),
                        )
                    )
                else:
                    _claim(lm, head)

            in_ref = backward_partner_ref(lm)
            if in_ref is not None and in_ref.page_id != lm.page_id:
                tail = _lookup_ref(
                    in_ref,
                    page_id=lm.page_id,
                    line_by_id=line_by_id,
                    cross_page_partners=cross_page_partners,
                )
                if tail is None:
                    self._emit(
                        ev.HyphenPartnerMissing(
                            chunk_id=chunk_id,
                            line_id=lm.line_id,
                            missing_partner_id=in_ref.line_id,
                            direction="backward",
                        )
                    )
                else:
                    _claim(tail, lm)

        # 2. One walk per unit, members in reading order. Every join's
        #    tail and partner are both in the pool, so the derivation
        #    groups them and the walk visits every join exactly once.
        reconciled_count = 0
        written_heads: set[LineRef] = set()
        for group in derive_hyphen_groups(pool.values()):
            for member in group.members:
                join = joins.get(member)
                if join is None:
                    continue
                tail, head, is_forward = join
                head_ref = line_ref(head)
                if head_ref in written_heads:
                    continue  # two tails claiming one head — corrupt link
                outcome = _reconcile_one_pair(
                    tail,
                    head,
                    text_by_id,
                    is_forward=is_forward,
                    config=self.guard_config,
                )
                self._record_reconcile_outcome(ctx, outcome)
                # Both members' traces are refreshed here, not only the
                # chunk's own. A cross-page join is decided on the HEAD's
                # page, and an incoherent pair reverts the TAIL — whose
                # page closed already, so nothing downstream would fix
                # its trace. A FALLBACK with no reason on the trace
                # surfaces as a decision with no reason at all
                # (derive_decision_set reads the reason from there).
                # NB ``side``, not ``member``: the enclosing loop's
                # ``member`` is a LineRef, and shadowing it here type-checks
                # as a conflict for good reason — it is read at the top of
                # this loop body.
                for side in (tail, head):
                    fell = side.status is LineStatus.FALLBACK
                    _set_trace(
                        traces,
                        side,
                        projected_text=side.corrected_text,
                        validation_status="fallback" if fell else "corrected",
                    )
                    if not fell:
                        continue
                    trace = traces.get(line_ref(side)) if traces is not None else None
                    if trace is not None and not trace.fallback_reason:
                        trace.fallback_reason = f"hyphen_pair_{outcome}"
                written_heads.add(head_ref)
                reconciled_count += 1

        return reconciled_count

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
