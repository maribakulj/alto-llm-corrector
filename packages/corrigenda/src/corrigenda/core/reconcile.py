"""Hyphen-unit helpers the orchestrator consumes but does not own.

Everything here answers a question ABOUT A UNIT — which lines travel
together, where a partner's manifest is, what one pair's reconciliation
decided — and none of it needs a pipeline, a producer or an observer. They
were 224 lines in the middle of a 3200-line orchestrator (S2), which is
where "who is my partner?" grew five parallel answers in the first place.

Every one of them reads the shared derivation (`units.derive_hyphen_groups`)
or the directed primitives (`pairing`); none reads a pointer field directly.
"""

from __future__ import annotations

from corrigenda.core.hyphenation import (
    classify_reconcile_outcome,
    reconcile_hyphen_pair,
)
from corrigenda.core.identity import LineRef
from corrigenda.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    BlockManifest,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineStatus,
    PageManifest,
)
from corrigenda.core.units import derive_hyphen_groups


def _subpage_for_lines(page: PageManifest, lines: list[LineManifest]) -> PageManifest:
    """Build a synthetic single-page manifest holding just ``lines`` (F1).

    Used to re-plan a failed chunk's lines at a finer granularity via the
    normal chunk planner: the planner needs a ``PageManifest`` with the
    blocks that own these lines. Blocks are copied with their ``line_ids``
    filtered to the subset, preserving block order and geometry so BLOCK /
    WINDOW planning behave exactly as on the real page.
    """
    kept_ids = {lm.line_id for lm in lines}
    sub_blocks = [
        BlockManifest(
            block_id=b.block_id,
            page_id=b.page_id,
            block_order=b.block_order,
            coords=b.coords,
            line_ids=[lid for lid in b.line_ids if lid in kept_ids],
        )
        for b in page.blocks
        if any(lid in kept_ids for lid in b.line_ids)
    ]
    return PageManifest(
        page_id=page.page_id,
        source_file=page.source_file,
        page_index=page.page_index,
        page_width=page.page_width,
        page_height=page.page_height,
        blocks=sub_blocks,
        lines=lines,
    )


def _build_hyphen_pairs(lines: list[LineManifest]) -> dict[str, str]:
    """Return PART1↔PART2 mapping (bidirectional) for lines in the chunk."""
    pairs: dict[str, str] = {}
    for lm in lines:
        if lm.hyphen_role == HyphenRole.PART1 and lm.hyphen_pair_line_id:
            pairs[lm.line_id] = lm.hyphen_pair_line_id
            pairs[lm.hyphen_pair_line_id] = lm.line_id
        elif lm.hyphen_role == HyphenRole.BOTH and lm.hyphen_forward_pair_id:
            pairs[lm.line_id] = lm.hyphen_forward_pair_id
            pairs[lm.hyphen_forward_pair_id] = lm.line_id
    return pairs


def _lookup_ref(
    ref: LineRef | None,
    *,
    page_id: str,
    line_by_id: dict[str, LineManifest],
    cross_page_partners: dict[LineRef, LineManifest] | None,
) -> LineManifest | None:
    """The manifest ``ref`` names, over the run's two lookup scopes.

    A LOOKUP, not a resolution: which slot the ref came from, and whether
    the role makes it a continuation, are decided by
    :mod:`corrigenda.core.pairing`'s primitives before we get here. This
    function only knows that a same-page ref is found by bare id in the
    page map and an off-page one needs the qualified map — because two
    ALTO files may declare the same TextLine ID, and a bare-id lookup
    would then return the wrong manifest.
    """
    if ref is None:
        return None

    if ref.page_id == page_id:
        return line_by_id.get(ref.line_id)

    if cross_page_partners is None:
        return None
    return cross_page_partners.get(ref)


def _page_local_units(
    line_by_id: dict[str, LineManifest],
) -> dict[str, set[str]]:
    """Every hyphen unit wholly resolvable on ONE page, by member line_id.

    Used by the router to move a hyphen unit to the escalation producer
    **as a unit**, and by the image-cap batcher to keep one in a single
    call: escalating or batching one member and leaving its partner
    behind would split the pair across producers, which is exactly what
    hyphen atomicity forbids. A unit whose link crosses a page boundary —
    or dangles — cannot be gathered from one page's plan, so it is absent
    here and its members are left to the primary producer (the
    conservative behaviour).

    Reads no pointer field. The grouping AND the "is this the whole
    unit?" question are both answered by the shared derivation
    (ADR-010): ``derive_hyphen_groups`` over one page marks a group
    incomplete exactly when it continues off-page or dangles. Re-reading
    the pointers here to ask the same thing is how a parallel resolver
    appears, and five of those are the debt this is paying down.

    Derived once per page rather than once per line — the previous
    per-line walk was quadratic in a page's hyphen density.
    """
    units: dict[str, set[str]] = {}
    for group in derive_hyphen_groups(line_by_id.values()):
        if not group.complete or group.spans_pages:
            continue
        members = {ref.line_id for ref in group.members}
        for line_id in members:
            units[line_id] = members
    return units


def _units_visible_on_page(
    line_by_id: dict[str, LineManifest],
) -> dict[str, set[str]]:
    """Every hyphen unit's members AS SEEN HERE, by member line_id —
    complete or not.

    The image-cap batcher's question, and NOT
    :func:`_page_local_units`'s (L7). That one answers "is this the whole
    unit?" and returns nothing when the answer is no, which is right for the
    ROUTER: escalating half a unit to a second producer would split it, so an
    incomplete unit is left to the primary and its members stay together by
    doing nothing.

    The batcher has no such option. It is slicing ONE chunk into several
    calls, so "leave them alone" is not available — every line lands in some
    batch. Handed nothing, it treated each member as a singleton and could
    put a pair in two different calls, which is the one thing pair atomicity
    forbids. Two shapes reached it: a group whose last pointer dangles, and a
    group that continues onto another page (its far member is simply not
    here, and the members that ARE still belong in one call).

    So: same shared derivation (ADR-010), same zero pointer reads, different
    projection — the members present, whether or not they are all of them.
    Keeping them together is never worse than splitting them.
    """
    units: dict[str, set[str]] = {}
    for group in derive_hyphen_groups(line_by_id.values()):
        members = {ref.line_id for ref in group.members if ref.line_id in line_by_id}
        if len(members) < 2:
            continue
        for line_id in members:
            units[line_id] = members
    return units


def _unit_pool(
    line_by_id: dict[str, LineManifest] | None,
    cross_page_partners: dict[LineRef, LineManifest] | None,
) -> list[LineManifest]:
    """Everything a unit query may reach from here: this page's lines plus
    the cross-page partners the run has resolved.

    The two maps are the scope the pipeline has always used. Flattening
    them into one pool lets :func:`~corrigenda.core.units.units_containing`
    answer "…and its partners" from the shared derivation instead of the
    pipeline carrying a second fixed-point walk over the pointer fields.
    """
    pool = list(line_by_id.values()) if line_by_id else []
    if cross_page_partners:
        pool.extend(cross_page_partners.values())
    return pool


def _reconcile_one_pair(
    lm: LineManifest,
    part2: LineManifest,
    text_by_id: dict[str, str],
    *,
    is_forward: bool,
    config: GuardConfig = DEFAULT_GUARD_CONFIG,
) -> str:
    """Apply reconcile_hyphen_pair and write results back onto the manifests.

    Returns the outcome classification produced by
    ``classify_reconcile_outcome``: ``"coherent"`` / ``"fallback"`` /
    ``"neutralised"``. The pipeline aggregates these into the per-job
    ReconcileMetrics surfaced on the reconcile_stats observability event.
    """
    # ADR-010 (unit fallback atomicity): a member whose partner already
    # fell back to OCR may not be corrected alone — the joined word would
    # be rewritten on one line and kept verbatim on the other. The whole
    # pair stays at source text; "fallback" is the classified outcome.
    if lm.status is LineStatus.FALLBACK or part2.status is LineStatus.FALLBACK:
        for member in (lm, part2):
            member.corrected_text = member.ocr_text
            member.status = LineStatus.FALLBACK
        return "fallback"

    corrected_p2 = text_by_id.get(part2.line_id, part2.ocr_text)

    if is_forward:
        corrected_p1 = lm.corrected_text or text_by_id.get(lm.line_id, lm.ocr_text)
        final_p1, final_p2, subs = reconcile_hyphen_pair(
            lm,
            part2,
            corrected_p1,
            corrected_p2,
            subs_content=lm.hyphen_forward_subs_content,
            source_explicit=lm.hyphen_forward_explicit,
            config=config,
        )
    else:
        # ``corrected_text`` first, exactly as the forward branch does. It
        # is what a CROSS-PAGE tail carries: its page ran earlier, so its
        # decision is on the manifest and not in this chunk's response,
        # and reading the response would silently substitute raw OCR for
        # the correction it already earned (L3).
        corrected_p1 = lm.corrected_text or text_by_id.get(lm.line_id, lm.ocr_text)
        final_p1, final_p2, subs = reconcile_hyphen_pair(
            lm,
            part2,
            corrected_p1,
            corrected_p2,
            config=config,
        )

    outcome = classify_reconcile_outcome(
        lm.ocr_text,
        part2.ocr_text,
        corrected_p1,
        corrected_p2,
        final_p1,
        final_p2,
        subs,
    )

    # The status follows the OUTCOME. It used to be CORRECTED
    # unconditionally — including when ``reconcile_hyphen_pair`` had
    # reverted BOTH sides to their OCR text because the pair was
    # incoherent. Two lines then kept their source text while reporting
    # as corrected, so the revert reached no fallback counter and no
    # reason: the same silent shape as the cross-page freeze (L3), and
    # not limited to cross-page pairs — any rejected intra-page pair had
    # it too. ``classify_reconcile_outcome`` only says "fallback" when
    # something was actually proposed and thrown away, so an identity
    # correction still lands as CORRECTED, which is what it is.
    status = LineStatus.FALLBACK if outcome == "fallback" else LineStatus.CORRECTED
    lm.corrected_text = final_p1
    lm.status = status
    part2.corrected_text = final_p2
    part2.status = status
    part2.hyphen_subs_content = subs

    if is_forward:
        lm.hyphen_forward_subs_content = subs
    else:
        lm.hyphen_subs_content = subs

    return outcome
