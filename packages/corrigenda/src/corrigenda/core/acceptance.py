"""Deciding whether a proposal may stand, and what falls back with it.

Four passes the orchestrator used to carry as methods (S2). Each takes the
policy it consults as an explicit argument rather than reading it off the
engine — which is what makes them readable on their own: "given THIS guard
config, is this line acceptable?" is a question about a line and a policy,
not about a run.

``_apply_unit_reverts`` is the one they share: a member of a hyphen unit
never falls back alone (ADR-010).
"""

from __future__ import annotations

from corrigenda.core.alignment import align_tokens
from corrigenda.core.guards import (
    check_adjacent_duplicates,
    check_boundary_migration,
    check_line,
)
from corrigenda.core.identity import LineRef, line_ref
from corrigenda.core.pairing import ends_with_break_mark, forward_ref, pair_ref
from corrigenda.core.reconcile import _lookup_ref
from corrigenda.core.traces import _set_trace
from corrigenda.core.units import derive_hyphen_groups, hyphen_group_by_line
from corrigenda.core.schemas import (
    DocumentManifest,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineStatus,
    LineTrace,
    LossPolicy,
    SidecarEntry,
)


def _apply_line_acceptance(
    *,
    guard_config: GuardConfig,
    chunk_lines: list[LineManifest],
    text_by_id: dict[str, str],
    all_lines_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    cross_page_partners: dict[LineRef, LineManifest] | None = None,
) -> None:
    """Apply the per-line acceptance policy on lines not already
    reconciled as hyphen pairs.

    Two guards in order:
      1. Orphan PART1/BOTH whose OCR ends in '-' but corrected does
         not → the LLM completed a hyphen we couldn't reconcile;
         fall back to OCR to keep the marker.
      2. Centralised :func:`check_line` with prev/next context — the
         single source of truth for "is this correction acceptable?".
    """
    for lm in chunk_lines:
        if lm.corrected_text is not None:
            continue
        corrected = text_by_id.get(lm.line_id)
        if corrected is None:
            continue

        # L5 — the repertoire, not the ASCII hyphen. This guard read
        # `endswith("-")`, so a line ending in ⸗ or ¬ whose correction
        # dropped the mark was NOT pulled back: 32 of the 363
        # hyphenated lines in the repo's corpora end in one of those.
        if (
            lm.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
            and ends_with_break_mark(lm.ocr_text)
            and not ends_with_break_mark(corrected)
        ):
            lm.corrected_text = lm.ocr_text
            lm.status = LineStatus.FALLBACK
            _set_trace(traces, lm, fallback_reason="orphan_hyphen_completed")
            continue

        # ADR-010 (unit fallback atomicity): a hyphen member whose
        # partner already fell back (its chunk was rejected — the
        # cross-page case: this side reaches acceptance because the
        # partner sits in no reconcile pass of THIS chunk) keeps its
        # source text too.
        # Both slots, DIRECT partners only — deliberately not the
        # transitive unit. Widening this to the whole chain is
        # defensible under unit atomicity but changes behaviour on
        # 3+-member chains, so it belongs behind a measurement, not
        # inside a refactor (noted in docs/PLAN.md under S1).
        fallen_partner = any(
            partner is not None and partner.status is LineStatus.FALLBACK
            for partner in (
                _lookup_ref(
                    ref,
                    page_id=lm.page_id,
                    line_by_id=all_lines_by_id,
                    cross_page_partners=cross_page_partners,
                )
                for ref in (pair_ref(lm), forward_ref(lm))
            )
        )
        if fallen_partner:
            lm.corrected_text = lm.ocr_text
            lm.status = LineStatus.FALLBACK
            _set_trace(traces, lm, fallback_reason="hyphen_partner_fell_back")
            continue

        prev_ocr = (
            all_lines_by_id[lm.prev_line_id].ocr_text
            if lm.prev_line_id and lm.prev_line_id in all_lines_by_id
            else None
        )
        next_ocr = (
            all_lines_by_id[lm.next_line_id].ocr_text
            if lm.next_line_id and lm.next_line_id in all_lines_by_id
            else None
        )
        result = check_line(
            lm.ocr_text, corrected, prev_ocr, next_ocr, config=guard_config
        )
        lm.corrected_text = result.text
        # P3.5 — the guard's once-computed metrics ride the trace to
        # the report's decision stage, accepted or not.
        _set_trace(traces, lm, proposal_features=result.features)
        if result.accepted:
            lm.status = LineStatus.CORRECTED
        else:
            lm.status = LineStatus.FALLBACK
            _set_trace(traces, lm, fallback_reason=result.reason)


def _global_adjacency_pass(
    *,
    guard_config: GuardConfig,
    document_manifest: DocumentManifest,
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """ONE adjacent-duplicate pass over the whole document (P3.3).

    The canonical sequence is pages in manifest order, lines in page
    order, broken at source-file transitions: file A's last physical
    line is not adjacent to file B's first, and comparing them could
    spuriously revert either. Keys are :class:`LineRef`s, so the
    bare-id ambiguity that forced the old page-seam pass to skip
    colliding seams (ADR-007) cannot arise — every seam is checked.
    Runs after the page loop: no earlier pass has reverted anything,
    so the live ``corrected_text`` IS the pre-revert accepted
    correction, and a run of three identical corrections straddling
    any seam is seen whole on one comparison basis.
    """
    reverts: dict[LineRef, str] = {}
    segment: list[tuple[LineRef, str, str]] = []
    prev_file: str | None = None

    def flush() -> None:
        if len(segment) > 1:
            reverts.update(check_adjacent_duplicates(segment, config=guard_config))
            # A word migrating across a line seam is invisible to the
            # pair-level guards when the OCR mangled the break glyph
            # (the line was never paired). This line-role-agnostic pass
            # catches it; reverts merge — a line flagged by either guard
            # falls back, atomically with its hyphen unit below.
            reverts.update(check_boundary_migration(segment, config=guard_config))
        segment.clear()

    for page in document_manifest.pages:
        if page.source_file != prev_file:
            flush()
            prev_file = page.source_file
        for lm in page.lines:
            segment.append(
                (
                    line_ref(lm),
                    lm.ocr_text,
                    lm.corrected_text if lm.corrected_text is not None else lm.ocr_text,
                )
            )
    flush()

    _apply_unit_reverts(reverts=reverts, all_lines=all_lines, traces=traces)


def _loss_policy_pass(
    *,
    loss_policy: LossPolicy,
    document_manifest: DocumentManifest,
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> list[SidecarEntry]:
    """Loss policy gates (ADR-012 strict; token_realign).

    **STRICT**: reject corrections that cannot project without
    losing word granularity. The PAGE rewriter drops a line's
    ``Word`` children when the corrected word count diverges from
    the markup's (6.2 P4 slow path) — the one predictable,
    decision-relevant format loss. ``LineManifest.word_count``
    carries the markup's count from parse time, so the check runs in
    the pure core, BEFORE the decisions materialize: a rejected line
    falls back to source (whole hyphen unit, ADR-010) and its
    rewrite becomes untouched — the source geometry survives.

    **TOKEN_REALIGN** (``min_alignment_score`` set, not strict): a
    word-count-changing correction whose tokens cannot be aligned
    onto the source tokens with at least the threshold score — or
    ANY correction that raises the move flag — is not projected.
    The line reverts like strict, but the correction is preserved as
    a :class:`SidecarEntry` (returned; surfaced on
    ``CorrectionReport.sidecar``) instead of lost.

    Under REPORT (default) this pass is a no-op: the loss projects,
    is counted, and is attributed per line.
    """
    if loss_policy.strict:
        reverts: dict[LineRef, str] = {}
        for page in document_manifest.pages:
            for lm in page.lines:
                if lm.word_count is None or lm.corrected_text is None:
                    continue
                if lm.corrected_text == lm.ocr_text:
                    continue  # identity projects untouched
                n_corrected = len(lm.corrected_text.split())
                if n_corrected != lm.word_count:
                    reverts[line_ref(lm)] = (
                        "format_loss: corrected word count "
                        f"{n_corrected} != source Word markup {lm.word_count} "
                        "— unprojectable without dropping word geometry "
                        "(LossPolicy strict)"
                    )
        _apply_unit_reverts(
            reverts=reverts,
            all_lines=all_lines,
            traces=traces,
            atomicity_reason="format_loss_pair_atomicity",
        )
        return []

    threshold = loss_policy.min_alignment_score
    if threshold is None:
        return []

    gate_reverts: dict[LineRef, str] = {}
    evidence: dict[LineRef, tuple[float, bool]] = {}
    snapshots: dict[LineRef, tuple[str, str]] = {}
    for page in document_manifest.pages:
        for lm in page.lines:
            if lm.corrected_text is None or lm.corrected_text == lm.ocr_text:
                continue
            ref = line_ref(lm)
            snapshots[ref] = (lm.ocr_text, lm.corrected_text)
            source_tokens = lm.ocr_text.split()
            target_tokens = lm.corrected_text.split()
            al = align_tokens(source_tokens, target_tokens)
            if al.move_suspected:
                evidence[ref] = (al.score, True)
                gate_reverts[ref] = (
                    "token_realign: suspected word reorder — "
                    "correction preserved in sidecar"
                )
            elif len(target_tokens) != len(source_tokens) and al.score < threshold:
                evidence[ref] = (al.score, False)
                gate_reverts[ref] = (
                    f"token_realign: alignment score {al.score:.2f} < "
                    f"{threshold:.2f} — correction preserved in sidecar"
                )
    reverted = _apply_unit_reverts(
        reverts=gate_reverts,
        all_lines=all_lines,
        traces=traces,
        atomicity_reason="token_realign_pair_atomicity",
    )
    entries: list[SidecarEntry] = []
    for ref, reason in reverted.items():
        snapshot = snapshots.get(ref)
        if snapshot is None:
            continue  # unit member whose own text was never corrected
        source_text, corrected_text = snapshot
        score, moved = evidence.get(ref, (None, False))
        entries.append(
            SidecarEntry(
                page_id=ref.page_id,
                line_id=ref.line_id,
                source_text=source_text,
                corrected_text=corrected_text,
                reason=reason,
                alignment_score=score,
                move_suspected=moved,
            )
        )
    return entries


def _apply_unit_reverts(
    *,
    reverts: dict[LineRef, str],
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    atomicity_reason: str = "adjacent_duplicate_pair_atomicity",
) -> dict[LineRef, str]:
    """Revert flagged lines to OCR — atomically with their WHOLE
    hyphen unit. Returns the FULL revert map (flagged + pulled
    members, each with its reason) so a caller can attribute what
    was reverted — the sidecar builder needs the pulled members too.

    A mixed OCR+corrected pair is the exact state
    ``reconcile_hyphen_pair`` guarantees can never survive, so a
    flagged member pulls every other member of its unit with it —
    cross-page members included, ``all_lines`` being the
    page-qualified document-wide index. Membership is a group lookup
    on THE derivation (ADR-010): the pass runs after planning, when
    the pointer fields are final, so the derived groups cannot be
    stale. A flagged line keeps its own revert reason; pulled
    members are stamped ``atomicity_reason`` (the calling pass's
    vocabulary) unless an earlier fallback path already pinned one.
    """
    if not reverts:
        return {}
    by_line = hyphen_group_by_line(derive_hyphen_groups(all_lines.values()))
    to_revert: dict[LineRef, str] = dict(reverts)
    for ref in reverts:
        group = by_line.get(ref)
        if group is None:
            continue
        for member in group.members:
            to_revert.setdefault(member, atomicity_reason)

    for ref, reason in to_revert.items():
        lm = all_lines.get(ref)
        if lm is None:
            continue
        lm.corrected_text = lm.ocr_text
        lm.status = LineStatus.FALLBACK
        _set_trace(
            traces,
            lm,
            projected_text=lm.ocr_text,
            validation_status=lm.status.value,
        )
        if traces is not None:
            trace = traces.get(ref)
            if trace is not None and not trace.fallback_reason:
                trace.fallback_reason = reason
    return to_revert
