"""Rewriting the corrected files in memory, and verifying what they say.

The last stage before a run hands anything back: the format adapter rewrites
each source file, the projection invariant checks that the bytes carry the
run's decisions, and the per-line traces gain what the rewrite actually did.

Free function (S2). Everything the engine used to supply is an argument now —
the adapter, the producer's identity, the config fingerprint stamped into the
provenance, and the observer callback. Rendering is a step over a manifest
and a set of decisions, not a property of a run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from corrigenda.core import events as ev
from corrigenda.core.decisions import DecisionSet
from corrigenda.core.identity import LineRef, line_ref
from corrigenda.core.projection import _verify_projection
from corrigenda.core.provenance import _adapter_for_format
from corrigenda.core.protocols import FormatAdapter, ProducerMetadata
from corrigenda.core.schemas import DocumentManifest, LineTrace


async def _render_outputs(
    *,
    format_adapter: FormatAdapter | None,
    producer_metadata: ProducerMetadata,
    config_fingerprint: str,
    emit: Callable[[ev.EngineEvent], None],
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
    traces: dict[LineRef, LineTrace],
    decisions: DecisionSet,
) -> tuple[dict[str, int], dict[str, bytes]]:
    """Rewrite corrected files in memory and update the traces.
    Returns ``(losses, corrected_files)`` — the format's
    granularity-loss counters aggregated across every file (for
    ``CorrectionReport.format_losses``) and the corrected bytes per
    source file name (for ``CorrectionResult.corrected_files``).

    ADR-011 — pure computation: nothing is persisted here (the
    engine has no writer; the caller persists from the result). The
    projection invariant verifies against the
    :class:`RewriteResult`'s texts, read off the very tree the bytes
    were serialized from: the second full parse of the output is
    gone. The heavy ``rewrite_file`` call (a full lxml
    parse/rewrite/serialize of the source file) runs in a worker
    thread so a ~100 MiB rewrite no longer freezes the host's event
    loop (SSE keepalives, /health). Observer events stay ON the
    loop — emit sites must never run from a thread (the store's
    queues are not thread-safe).
    """
    # §11 — provenance stamped into every corrected file's processingStep.
    from corrigenda import __version__ as _lib_version

    config_fingerprint = config_fingerprint
    # Adapter resolution is lazy (first file to write): a run with no
    # output files — every hand-built-manifest dry-run in the test
    # suite passes source_files={} — needs no format at all.
    adapter: FormatAdapter | None = format_adapter
    losses_total: dict[str, int] = {}
    corrected_files: dict[str, bytes] = {}

    for source_name, xml_path in source_files.items():
        pages_for_file = [
            p for p in document_manifest.pages if p.source_file == source_name
        ]
        if not pages_for_file:
            continue
        if adapter is None:
            adapter = _adapter_for_format(document_manifest.source_format)

        provider_label, model_label = producer_metadata.provenance_labels()
        result = await asyncio.to_thread(
            adapter.rewrite_file,
            xml_path,
            pages_for_file,
            # §11 provenance labels — constructor state since the §5.1
            # resorption (run() no longer carries provider/model).
            provider_label,
            model_label,
            lib_version=_lib_version,
            config_fingerprint=config_fingerprint,
        )

        # Projection invariant: the artefact must SAY what the run
        # decided. Verified BEFORE the writer sees the bytes — a
        # divergent artefact is corruption, never a valid output.
        # What it CAN'T refuse — a whitespace character the format
        # flattened — comes back as a per-line fidelity level and
        # goes on the record rather than disappearing.
        fidelity_by_lid = _verify_projection(
            source_name,
            pages_for_file,
            result.texts,
            decisions,
            result.texts_verbatim,
        )
        corrected_files[source_name] = result.xml_bytes

        # rewriter_stats observability event — pure read-only diagnostic
        # surfacing how each line classified (UNTOUCHED / SUBS_ONLY /
        # FAST_PATH / SLOW_PATH). Zero impact on the corrected XML.
        emit(
            ev.RewriterStats(
                source_stem=xml_path.stem,
                untouched=result.metrics.untouched,
                subs_only=result.metrics.subs_only,
                fast_path=result.metrics.fast_path,
                slow_path=result.metrics.slow_path,
            )
        )
        for key, count in result.losses.items():
            losses_total[key] = losses_total.get(key, 0) + count

        lid_to_ref: dict[str, LineRef] = {}
        for p in pages_for_file:
            for lm in p.lines:
                lid_to_ref[lm.line_id] = line_ref(lm)

        for lid, rpath in result.rewriter_paths.items():
            tkey = lid_to_ref.get(lid)
            if tkey:
                t = traces.get(tkey)
                if t is not None:
                    t.rewriter_path = rpath

        # ADR-012 — the rewrite's per-line loss attribution rides the
        # traces onto the report's projection stage.
        for lid, line_losses in result.losses_by_line.items():
            tkey = lid_to_ref.get(lid)
            if tkey:
                t = traces.get(tkey)
                if t is not None:
                    t.projection_losses = line_losses

        for lid, otxt in result.texts.items():
            tkey = lid_to_ref.get(lid)
            if tkey:
                t = traces.get(tkey)
                if t is not None:
                    t.output_alto_text = otxt

        for lid, level in fidelity_by_lid.items():
            tkey = lid_to_ref.get(lid)
            if tkey:
                t = traces.get(tkey)
                if t is not None:
                    t.projection_fidelity = level

        # R5 — the alignment's reorder suspicion, on its own channel
        # rather than inside the loss counters where summing it counted
        # a non-loss.
        for lid in result.word_order_suspected:
            tkey = lid_to_ref.get(lid)
            if tkey:
                t = traces.get(tkey)
                if t is not None:
                    t.word_order_suspected = True

    # No trace persistence anywhere in the engine: trace.json IS the
    # CorrectionReport (§9), carried on the result for the caller.
    return losses_total, corrected_files
