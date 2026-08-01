"""Assembling what a run REPORTS, separately from how it ran (S2).

The plan's target for splitting the orchestrator names this seam explicitly:
report assembly must not be entangled with execution control. This module is
the first piece of it — turning the ops a run actually applied into the
``EditScript`` the report carries.

Free function: it reads the run's recorded ops and decisions and needs
nothing from the engine.
"""

from __future__ import annotations

from corrigenda.core.context import RunContext
from corrigenda.core.decisions import DecisionSet
from corrigenda.core.editing import (
    EDIT_PROTOCOL_VERSION,
    EditOp,
    EditScript,
    LinePrecondition,
    ReplaceLine,
    line_digest,
)
from corrigenda.core.schemas import LineStatus


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

    P3.10 — the script is stamped with its protocol version, the
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
