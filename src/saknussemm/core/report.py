"""Assembling what a run REPORTS, separately from how it ran.

The plan's target for splitting the orchestrator names this seam explicitly:
report assembly must not be entangled with execution control. Two pieces
here — the ``EditScript`` of what the run actually applied, and the §9
:class:`CorrectionReport` itself.

Free functions throughout: everything is read off the run's recorded ops,
its terminal decisions, the working traces and the accumulated
:class:`RunContext`. Nothing needs the engine, and nothing here can change
what the run did — a report that could would not be a report.
"""

from __future__ import annotations

from saknussemm.core.confidence import ConfidenceScorer, build_line_confidence
from saknussemm.core.context import RunContext
from saknussemm.core.decisions import DecisionSet, build_line_outcomes
from saknussemm.core.editing import (
    EDIT_PROTOCOL_VERSION,
    EditOp,
    EditScript,
    LinePrecondition,
    ReplaceLine,
    line_digest,
)
from saknussemm.core.identity import LineRef
from saknussemm.core.pairing import unpaired_break_refs
from saknussemm.core.projection import _fidelity_counts
from saknussemm.core.schemas import (
    ConfidencePolicy,
    CorrectionReport,
    DocumentManifest,
    LineManifest,
    LineStatus,
    LineTrace,
    RunProvenance,
    SidecarEntry,
)


def _build_final_edit_script(
    decisions: DecisionSet,
    ctx: RunContext,
    *,
    source_digests: dict[str, str] | None = None,
) -> EditScript:
    """§4 — the EditScript the run *actually applied*, in document order.

    Reconciles the captured producer ops against the FINAL per-line
    decision (ADR-011 — read from the immutable :class:`DecisionSet`,
    which is already in document reading order), after
    reconciliation, the acceptance guard, and the global consistency
    pass have run. It therefore never carries an op for a line that
    was reverted to OCR or reconciled to different text (a dry-run
    consumer replaying it would otherwise diverge from the
    pipeline's own corrected XML):

    - line not ``CORRECTED`` (fallback / failed) → no op;
    - ``CORRECTED`` and the producer's op output survived unchanged →
      the producer's original op, preserving its TYPE (e.g. a rules
      producer's ``replace_span``);
    - ``CORRECTED`` but the final text differs from the op output
      (a reconciled hyphen member) → a ``replace_line`` carrying the
      final text, since the original span no longer describes it.

    The script is stamped with its protocol version, the
    run's source-file digests, and one :class:`LinePrecondition`
    per op-carrying line (the digest of the SOURCE text the ops
    were computed against), so replaying it on a different document
    fails explicitly instead of editing a lookalike line.
    """
    ops: list[EditOp] = []
    preconditions: list[LinePrecondition] = []
    for decision in decisions.decisions:
        if decision.status is not LineStatus.CORRECTED:
            continue
        captured = ctx.producer_ops.get(decision.ref)
        if captured is None:
            # An accepted line the producer left untouched (no op) —
            # e.g. a rules producer's uncovered line. Nothing applied.
            continue
        preconditions.append(
            LinePrecondition(
                line_id=decision.ref.line_id,
                page_id=decision.ref.page_id,
                digest=line_digest(decision.source_text),
            )
        )
        line_ops, produced_text = captured
        if produced_text == decision.final_text:
            # The producer's output survived every guard unchanged —
            # keep its original ops (and their TYPE, e.g. span),
            # stamped with the page_id so a consumer can attribute
            # them per file (bare line_ids repeat across
            # files — ADR-001).
            ops.extend(
                op.model_copy(update={"page_id": decision.ref.page_id})
                for op in line_ops
            )
        else:
            # A guard / the reconciler rewrote the final text; the
            # original ops no longer describe it.
            ops.append(
                ReplaceLine(
                    line_id=decision.ref.line_id,
                    text=decision.final_text,
                    page_id=decision.ref.page_id,
                )
            )
    return EditScript(
        ops=ops,
        protocol_version=EDIT_PROTOCOL_VERSION,
        source_digests=source_digests or {},
        preconditions=preconditions,
    )


def _attach_line_confidences(
    report: CorrectionReport,
    *,
    policy: ConfidencePolicy,
    scorers: tuple[ConfidenceScorer, ...],
    all_lines: dict[LineRef, LineManifest],
    ctx: RunContext,
) -> None:
    """Score every outcome's FINAL decided text (report-only).

    Runs AFTER the outcomes are built, so a line scores what actually
    decided it, whatever path got there — a reconciled hyphen member and a
    line the guard reverted are both scored on the text the artefact will
    carry, not on the proposal. ``write_wc`` stays locked until
    calibration: this reaches the report and nothing else.
    """
    if policy.mode == "drop":
        return
    for outcome in report.lines:
        ref = LineRef(page_id=outcome.page_id, line_id=outcome.line_id)
        scored_line = all_lines.get(ref)
        # The producer's verified self-assessment rides the captured ops
        # (uncertainty channel); min over a line's ops when several
        # declared one.
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
            scorers=scorers,
        )


def _build_correction_report(
    *,
    run_id: str,
    document_manifest: DocumentManifest,
    decisions: DecisionSet,
    traces: dict[LineRef, LineTrace],
    ctx: RunContext,
    provenance: RunProvenance,
    format_losses: dict[str, int],
    sidecar_entries: list[SidecarEntry],
    confidence_policy: ConfidencePolicy,
    confidence_scorers: tuple[ConfidenceScorer, ...],
    all_lines: dict[LineRef, LineManifest],
) -> CorrectionReport:
    """The §9 report: everything the run has to SAY about what it did."""
    report = CorrectionReport(
        run_id=run_id,
        total_lines=len(decisions.decisions),
        # ADR-011 slice C — the report builder reads the
        # DecisionSet (terminal stage) + the working traces
        # (proposal/projection stages), staged per line (§9 v2).
        lines=build_line_outcomes(decisions, traces),
        # ADR-011 — the rewrite's granularity-loss counters surface on
        # the report. None when no MARKUP was dropped (or nothing was
        # written) — never read as "the run lost nothing": a flattened
        # character is counted on the fidelity scale below.
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
        # The units this run CUT to fit the request cap. Distinct
        # from unpaired_breaks: there the link was never there, here the
        # engine severed one on purpose, and the split resets the tail's
        # role to NONE so it cannot show up in that count either.
        hyphen_splits=ctx.hyphen_splits or None,
        # §11 — the run's full provenance record.
        provenance=provenance,
        # §11 — the aggregated usage is part of the persisted
        # artefact, not just the transient result. None when nothing
        # was reported: a zero Usage would be indistinguishable from
        # "the provider reported zero tokens".
        usage=(ctx.usage if ctx.usage.total_tokens or ctx.usage.response_ids else None),
        # corrections the token_realign gate refused to
        # project, preserved for review instead of lost.
        sidecar=sidecar_entries or None,
    )
    _attach_line_confidences(
        report,
        policy=confidence_policy,
        scorers=confidence_scorers,
        all_lines=all_lines,
        ctx=ctx,
    )
    return report
