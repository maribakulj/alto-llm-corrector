"""Turning a corrected document into the run's terminal decisions.

Between "every page has been through the producer" and "the outputs exist"
sit four document-wide passes, and their ORDER is the whole content of this
module — each one depends on running against what the previous left behind:

  1. the adjacent-duplicate consistency pass, which needs every
     line still holding its pre-revert accepted correction, so it must be
     the first thing to revert anything;
  2. break-character preservation (P5), which normalises the accepted text
     BEFORE it becomes a decision — historically the PAGE rewriter forced
     the source's break character after the decision was recorded, so the
     artefact spelled something the decision did not and the projection
     invariant raised on the engine's own output;
  3. the loss-policy gates (ADR-012 strict, token_realign), which reject a
     correction that cannot project without losing word granularity —
     before the decisions materialise and before any output exists, so the
     unit falls back to source and the markup keeps its Word geometry;
  4. deriving the immutable :class:`DecisionSet`, which refuses a line
     still PENDING: outputs exist only for a document where every line
     carries a terminal decision.

Free function. None of it is execution control — no producer, no
retry, no observer — and reading it inline in the orchestrator, between the
page loop and the report, is what made the ordering look incidental.

Since `RM-01` the order is no longer only stated here: each pass takes a
:class:`~saknussemm.core.acceptance._FinalizeOrder` token, declares what
must have run before it, and REFUSES otherwise. The list above is the
contract; the token is what makes breaking it an error instead of a
different output file.
"""

from __future__ import annotations

from saknussemm.core import decide
from saknussemm.core.acceptance import (
    _FinalizeOrder,
    _global_adjacency_pass,
    _loss_policy_pass,
)
from saknussemm.core.decisions import DecisionSet, derive_decision_set
from saknussemm.core.identity import LineRef
from saknussemm.core.pairing import preserve_break_char
from saknussemm.core.schemas import (
    DocumentManifest,
    GuardConfig,
    LineManifest,
    LineTrace,
    LossPolicy,
    SidecarEntry,
)


def _preserve_break_chars(
    document_manifest: DocumentManifest,
    order: _FinalizeOrder | None = None,
) -> None:
    """Force the SOURCE line's word-break character onto every accepted
    correction that changed it (P5, found by the OCR17+ corpus).

    Only the decided text is normalised: the proposal stage in the traces
    keeps the producer's RAW text, so what the producer actually said stays
    auditable.

    Goes through :func:`decide.renormalise` and NOT ``decide.accept``,
    which is the question ADR-013 left for `RM-01` to answer. This pass
    decides nothing: it does not choose between a proposal and a source,
    it respells a choice already made, and it never runs on a line that
    fell back — a reverted line has ``corrected_text == ocr_text``, which
    the guard above skips. Routing it through ``accept`` would stamp
    ``CORRECTED`` on lines whose status it has no business setting, which
    is a behaviour change bought for the tidiness of two verbs instead of
    three. The narrow verb keeps the call honest about what happened.
    """
    if order is not None:
        order.entering("break_chars", requires=("adjacency",))

    for page in document_manifest.pages:
        for lm in page.lines:
            if lm.corrected_text is not None and lm.corrected_text != lm.ocr_text:
                decide.renormalise(
                    lm, preserve_break_char(lm.ocr_text, lm.corrected_text)
                )


def _finalize_document(
    *,
    guard_config: GuardConfig,
    loss_policy: LossPolicy,
    document_manifest: DocumentManifest,
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace],
) -> tuple[DecisionSet, list[SidecarEntry]]:
    """Run the document-wide passes and materialise the run's decisions.

    Returns the terminal :class:`DecisionSet` and the sidecar entries the
    loss policy set aside — corrections the token_realign gate refused to
    project, preserved for review instead of lost.
    """
    order = _FinalizeOrder()
    _global_adjacency_pass(
        guard_config=guard_config,
        document_manifest=document_manifest,
        all_lines=all_lines,
        traces=traces,
        order=order,
    )
    _preserve_break_chars(document_manifest, order)
    sidecar_entries = _loss_policy_pass(
        loss_policy=loss_policy,
        document_manifest=document_manifest,
        all_lines=all_lines,
        traces=traces,
        order=order,
    )
    return derive_decision_set(document_manifest, traces), sidecar_entries
