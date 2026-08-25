"""Hyphen-unit helpers the orchestrator consumes but does not own.

Everything here answers a question ABOUT A UNIT — which lines travel
together, where a partner's manifest is, what one pair's reconciliation
decided — and none of it needs a pipeline, a producer or an observer. They
were 224 lines in the middle of a 3200-line orchestrator, which is
where "who is my partner?" grew five parallel answers in the first place.

Every one of them reads the shared derivation (`units.derive_hyphen_groups`)
or the directed primitives (`pairing`); none reads a pointer field directly.
That sentence stood here while ``_build_hyphen_pairs`` replayed the role→slot
map six lines below it, which is the whole reason the claim is now held by a
census — ``tests/hyphenation/test_only_pairing_reads_the_pointer_fields.py``
counts every pointer-field access in the package and refuses a seventh site.
"""

from __future__ import annotations

from collections.abc import Callable

from saknussemm.core import decide, events as ev
from saknussemm.core.context import RunContext
from saknussemm.core.hyphenation import (
    classify_reconcile_outcome,
    reconcile_hyphen_pair,
)
from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.pairing import (
    backward_partner_ref,
    forward_partner_id,
    forward_partner_ref,
)
from saknussemm.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    BlockManifest,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineStatus,
    LineTrace,
    PageManifest,
)
from saknussemm.core.traces import _set_trace
from saknussemm.core.units import derive_hyphen_groups
from saknussemm.core.workspace import PageWorkspace


def _subpage_for_lines(page: PageManifest, lines: list[LineManifest]) -> PageManifest:
    """Build a synthetic single-page manifest holding just ``lines``.

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
    """La carte bidirectionnelle des paires du chunk, pour le validateur.

    Le lien dirigé vient de :func:`~saknussemm.core.pairing.forward_partner_id`
    — la carte rôle→slot est détenue là et nulle part ailleurs. Ce site la
    rejouait à la main (``PART1`` → slot PAIR, ``BOTH`` → slot FORWARD),
    soixante lignes sous une docstring de module qui l'interdisait.

    Les clés restent des ``line_id`` NUS, et ce n'est pas un oubli : c'est la
    forme que ``validate_llm_response`` consomme, et elle est sûre parce
    qu'un chunk est page-scopé. La changer serait un changement du contrat du
    validateur, pas un déplacement.
    """
    pairs: dict[str, str] = {}
    for lm in lines:
        partner = forward_partner_id(lm)
        if partner is None:
            continue
        pairs[lm.line_id] = partner
        pairs[partner] = lm.line_id
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
    :mod:`saknussemm.core.pairing`'s primitives before we get here. This
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
    :func:`_page_local_units`'s. That one answers "is this the whole
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
    them into one pool lets :func:`~saknussemm.core.units.units_containing`
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
    traces: dict[LineRef, LineTrace] | None = None,
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
            decide.fall_back(member, reason="hyphen_pair_fallback", traces=traces)
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
        # the correction it already earned.
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
    # reason: the same silent shape as the cross-page freeze, and
    # not limited to cross-page pairs — any rejected intra-page pair had
    # it too. ``classify_reconcile_outcome`` only says "fallback" when
    # something was actually proposed and thrown away, so an identity
    # correction still lands as CORRECTED, which is what it is.
    # ``classify_reconcile_outcome`` returns "fallback" ONLY when
    # ``final_p1 == lm.ocr_text and final_p2 == part2.ocr_text`` — the
    # classification is defined by that equality — so ``fall_back``,
    # which writes ``ocr_text``, writes exactly ``final_p1``/``final_p2``
    # here. That is a guarantee from the classifier's own definition, not
    # an empirical one, and ``test_reconcile_translation.py`` pins it.
    if outcome == "fallback":
        decide.fall_back(lm, reason="hyphen_pair_fallback", traces=traces)
        decide.fall_back(part2, reason="hyphen_pair_fallback", traces=traces)
    else:
        decide.accept(lm, final_p1, traces=traces)
        decide.accept(part2, final_p2, traces=traces)
    # NOT a decision field, and deliberately left here: the SUBS_CONTENT
    # a pair resolved is hyphen state, which the single decision writer
    # deliberately does not own (`RM-01`).
    part2.hyphen_subs_content = subs

    if is_forward:
        lm.hyphen_forward_subs_content = subs
    else:
        lm.hyphen_subs_content = subs

    return outcome


def _record_reconcile_outcome(ctx: RunContext, outcome: str) -> None:
    """Bump the run's ReconcileMetrics counter for a single pair."""
    if outcome == "coherent":
        ctx.reconcile_metrics.coherent += 1
    elif outcome == "fallback":
        ctx.reconcile_metrics.fallback += 1
    elif outcome == "neutralised":
        ctx.reconcile_metrics.neutralised += 1


def _reconcile_chunk_hyphens(
    *,
    guard_config: GuardConfig,
    emit: Callable[[ev.EngineEvent], None],
    ctx: RunContext,
    chunk_id: str,
    chunk_lines: list[LineManifest],
    text_by_id: dict[str, str],
    workspace: PageWorkspace,
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

    **A join that leaves the page is owned by its HEAD instead.**
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
    joins, pool = _claim_joins(
        chunk_id=chunk_id,
        chunk_lines=chunk_lines,
        line_by_id=workspace.line_by_id,
        cross_page_partners=workspace.cross_page_partners,
        emit=emit,
    )
    return _walk_units_reconciling(
        joins,
        pool,
        guard_config=guard_config,
        ctx=ctx,
        text_by_id=text_by_id,
        traces=workspace.traces,
    )


#: A join this chunk owns: ``(tail, head, is_forward)``. ``is_forward``
#: names the SLOT the tail links through, and only a BOTH tail uses its
#: FORWARD slot (see pairing.py) — it is not a direction.
_Join = tuple[LineManifest, LineManifest, bool]


def _claim_joins(
    *,
    chunk_id: str,
    chunk_lines: list[LineManifest],
    line_by_id: dict[str, LineManifest],
    cross_page_partners: dict[LineRef, LineManifest] | None,
    emit: Callable[[ev.EngineEvent], None],
) -> tuple[dict[LineRef, _Join], dict[LineRef, LineManifest]]:
    """Collect the joins this chunk owns, and the pool they live in.

    Outgoing joins (this line continues onto another) unless they leave
    the page; incoming ones (another line continues onto this one) only
    when they do. Every join is therefore owned exactly once, by
    whichever side can see both members — tail-ownership on a page,
    head-ownership across one.

    Emits ``hyphen_partner_missing`` for each partner it cannot resolve,
    so an observer sees the diagnostic instead of a silent skip.
    """
    joins: dict[LineRef, _Join] = {}
    pool: dict[LineRef, LineManifest] = {line_ref(lm): lm for lm in chunk_lines}

    def _claim(tail: LineManifest, head: LineManifest) -> None:
        pool[line_ref(tail)] = tail
        pool[line_ref(head)] = head
        joins[line_ref(tail)] = (tail, head, tail.hyphen_role == HyphenRole.BOTH)

    def _resolve(ref: LineRef, lm: LineManifest, direction: str) -> LineManifest | None:
        partner = _lookup_ref(
            ref,
            page_id=lm.page_id,
            line_by_id=line_by_id,
            cross_page_partners=cross_page_partners,
        )
        if partner is None:
            emit(
                ev.HyphenPartnerMissing(
                    chunk_id=chunk_id,
                    line_id=lm.line_id,
                    missing_partner_id=ref.line_id,
                    direction=direction,
                )
            )
        return partner

    for lm in chunk_lines:
        # The role→slot map is NOT re-derived here. It used to be, in a
        # ternary two lines long, sitting beside a helper that already
        # owned it — and "forward" naming the SLOT rather than the
        # direction is exactly the kind of thing a second copy gets
        # subtly wrong (ADR-010).
        out_ref = forward_partner_ref(lm)
        if out_ref is not None and out_ref.page_id == lm.page_id:
            head = _resolve(
                out_ref,
                lm,
                "forward" if lm.hyphen_role == HyphenRole.BOTH else "backward",
            )
            if head is not None:
                _claim(lm, head)

        in_ref = backward_partner_ref(lm)
        if in_ref is not None and in_ref.page_id != lm.page_id:
            tail = _resolve(in_ref, lm, "backward")
            if tail is not None:
                _claim(tail, lm)

    return joins, pool


def _refresh_pair_traces(
    tail: LineManifest,
    head: LineManifest,
    *,
    outcome: str,
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """Refresh BOTH members' traces, not only the chunk's own.

    A cross-page join is decided on the HEAD's page, and an incoherent
    pair reverts the TAIL — whose page closed already, so nothing
    downstream would fix its trace. A FALLBACK with no reason on the
    trace surfaces as a decision with no reason at all, since
    ``derive_decision_set`` reads the reason from there.
    """
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


def _walk_units_reconciling(
    joins: dict[LineRef, _Join],
    pool: dict[LineRef, LineManifest],
    *,
    guard_config: GuardConfig,
    ctx: RunContext,
    text_by_id: dict[str, str],
    traces: dict[LineRef, LineTrace] | None,
) -> int:
    """One walk per unit, members in reading order.

    Every claimed join has both its tail and its head in the pool, so THE
    derivation groups them and this walk visits each join exactly once.
    Returns the number reconciled.
    """
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
                config=guard_config,
                traces=traces,
            )
            _record_reconcile_outcome(ctx, outcome)
            _refresh_pair_traces(tail, head, outcome=outcome, traces=traces)
            written_heads.add(head_ref)
            reconciled_count += 1
    return reconciled_count
