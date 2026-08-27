"""Hybrid-selective routing: which lines get a producer call, and which one.

The QE router pre-decides SKIP lines (confirmed clean, no call at all) and
sends ESCALATE lines to the heavier producer, returning each chunk paired
with the producer that owns it. A no-op when routing is off — every chunk
pairs with the primary producer and every existing run stays byte-identical.

Free functions, each taking the scorer and policy it consults rather
than reading them off the engine: routing is a decision about chunks and a
policy, not about a run.
"""

from __future__ import annotations

from dataclasses import dataclass

from saknussemm.core import decide
from saknussemm.core.context import RunContext
from saknussemm.core.identity import LineRef
from saknussemm.core.protocols import EditProducer
from saknussemm.core.batching import _split_for_image_cap
from saknussemm.core.quality import (
    QEScorer,
    RoutingDecision,
    RoutingPolicy,
    route_line,
)
from saknussemm.core.reconcile import _page_local_units
from saknussemm.core.workspace import PageWorkspace
from saknussemm.core.schemas import (
    ChunkRequest,
    HyphenRole,
    LineManifest,
    LineTrace,
    PageManifest,
)


def _routing_enabled(
    *, qe_scorer: QEScorer | None, routing_policy: RoutingPolicy
) -> bool:
    """Routing runs only when a QE scorer is present AND the policy
    has at least one active bound. Otherwise a no-op (default)."""
    return qe_scorer is not None and (
        routing_policy.skip_at_or_below is not None
        or routing_policy.escalate_at_or_above is not None
    )


@dataclass(frozen=True)
class ChunkRouter:
    """Ce qui décide, pour une page planifiée, quel producteur reçoit quoi.

    Trois mécanismes vivaient sur :class:`~saknussemm.core.driver.PageDriver`
    et se lisaient donc avant le cas nominal : le score de qualité, le
    producteur d'escalade et le plafond d'images par appel. **Aucun des trois
    ne s'exécute par défaut.** Le pilote n'a plus à les connaître : il
    demande à cette couture ce que ses appels seront, et une couture inerte
    lui rend son plan inchangé.

    C'est un déplacement, pas une réécriture : la couture est au niveau du
    PLAN, là où le routage agit réellement — il réécrit les cibles d'un chunk
    et l'éclate en chunks frères. Un décorateur d'``EditProducer``, la forme
    qui vient d'abord à l'esprit, ne pourrait pas faire cela : un producteur
    reçoit une requête, pas un plan, donc un chunk entièrement SKIP serait
    quand même construit et ``producer_calls`` cesserait de mesurer
    l'économie que le mode existe pour prouver.

    Immuable et sans état de run, comme le pilote qui la porte.
    """

    #: Le scoreur de qualité ; ``None`` éteint le routage.
    qe_scorer: QEScorer | None
    #: Comment un score devient une décision. Le défaut envoie tout au
    #: producteur, donc un run par défaut est identique à un run sans
    #: routage.
    routing_policy: RoutingPolicy
    #: Le producteur du palier ESCALATE (un VLM), ou ``None``.
    escalation_producer: EditProducer | None

    def route(
        self,
        *,
        page: PageManifest,
        chunks: list[ChunkRequest],
        producer: EditProducer,
        ctx: RunContext,
        workspace: PageWorkspace,
    ) -> list[tuple[ChunkRequest, EditProducer]]:
        """Le plan d'une page, apparié au producteur qui portera chaque chunk.

        Deux étapes, dans cet ordre : router, puis plafonner les images. Le
        plafond vient APRÈS parce que seuls les chunks qui ont réellement
        atteint un producteur vision sont concernés — celui-ci recadre chaque
        ligne qu'on lui envoie, et les fournisseurs limitent le nombre
        d'images par appel.
        """
        routed = _route_and_filter_chunks(
            qe_scorer=self.qe_scorer,
            routing_policy=self.routing_policy,
            producer=producer,
            escalation_producer=self.escalation_producer,
            page=page,
            chunks=chunks,
            ctx=ctx,
            workspace=workspace,
        )
        return _split_for_image_cap(routed=routed, line_by_id=workspace.line_by_id)


def _route_and_filter_chunks(
    *,
    qe_scorer: QEScorer | None,
    routing_policy: RoutingPolicy,
    producer: EditProducer,
    escalation_producer: EditProducer | None,
    page: PageManifest,
    chunks: list[ChunkRequest],
    ctx: RunContext,
    workspace: PageWorkspace,
) -> list[tuple[ChunkRequest, EditProducer]]:
    """Route each chunk's target lines by QE tier, returning per-chunk
    ``(chunk, producer)`` work items.

    SKIP: a line the QE scorer + RoutingPolicy route to SKIP
    is confirmed clean — its final text is its OCR text, its status is
    CORRECTED, and (the auditable signature of a skip vs an LLM
    identity pass) it never reaches a producer, so its trace's
    ``model_input_text`` stays ``None``. It remains in each chunk's
    ``line_ids`` (context for its neighbours) but leaves
    ``target_line_ids``.

    ESCALATE: when an ``escalation_producer`` is set, a
    non-hyphen line routed to ESCALATE is split out of the chunk into a
    sibling chunk (same context ``line_ids``, disjoint targets) carried
    by the escalation producer — the VLM corrects only those lines. The
    remaining targets stay with the primary producer. A chunk with no
    targets left after SKIP is dropped (no producer call at all).

    A hyphen unit is NEVER skipped (atomicity — a half-skipped pair
    could not reconcile). It MAY escalate, but only as a whole unit:
    when any member routes to ESCALATE, every member goes, so the pair
    reaches one producer together and reconciles normally. A unit whose
    links leave the page (or dangle) cannot be gathered from this
    page's plan and stays with the primary producer.

    When routing is off (default), returns every chunk paired with the
    primary producer unchanged — a byte-identical run.
    """
    if not _routing_enabled(qe_scorer=qe_scorer, routing_policy=routing_policy):
        return [(chunk, producer) for chunk in chunks]
    assert qe_scorer is not None  # _routing_enabled guarantees it

    skip, escalate = _score_page_into_tiers(
        qe_scorer=qe_scorer,
        routing_policy=routing_policy,
        page=page,
        line_by_id=workspace.line_by_id,
        can_escalate=escalation_producer is not None,
    )
    _confirm_skipped_lines(
        skip, line_by_id=workspace.line_by_id, traces=workspace.traces
    )
    ctx.lines_skipped += len(skip)
    ctx.escalated_lines += len(escalate)
    return _work_items(
        chunks,
        skip=skip,
        escalate=escalate,
        producer=producer,
        escalation_producer=escalation_producer,
    )


def _score_page_into_tiers(
    *,
    qe_scorer: QEScorer,
    routing_policy: RoutingPolicy,
    page: PageManifest,
    line_by_id: dict[str, LineManifest],
    can_escalate: bool,
) -> tuple[set[str], set[str]]:
    """Score every line of the page and sort it into the two tiers that
    change what happens to it: ``(skip, escalate)``.

    A hyphen member is NEVER skipped — a half-skipped pair could not
    reconcile. It may still escalate, but only with its whole unit, so
    both halves reach one producer together: measured on real 19th-c.
    press OCR, leaving units behind was the hybrid's entire residual
    error. A unit whose links leave the page (or dangle) cannot be
    gathered from this page's plan and is left to the primary producer.
    """
    skip: set[str] = set()
    escalate: set[str] = set()
    page_units = _page_local_units(line_by_id)
    for lm in page.lines:
        decision = route_line(qe_scorer.needs_correction(lm.ocr_text), routing_policy)
        if lm.hyphen_role is not HyphenRole.NONE:
            if decision is RoutingDecision.ESCALATE and can_escalate:
                unit = page_units.get(lm.line_id)
                if unit is not None:
                    escalate |= unit
            continue
        if decision is RoutingDecision.SKIP:
            skip.add(lm.line_id)
        elif decision is RoutingDecision.ESCALATE and can_escalate:
            escalate.add(lm.line_id)
    return skip, escalate


def _confirm_skipped_lines(
    skip: set[str],
    *,
    line_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """Decide the skipped lines: their OCR text IS their final text.

    A skip is an ACCEPTANCE, not a fallback — the QE scorer judged the
    line already clean, so its source text is a decision rather than a
    retreat from one, and it goes through :func:`decide.accept` with the
    line's own text. Nothing about the write differs from an accepted
    correction; what differs is upstream, and stays upstream.

    The trace's ``model_input_text`` is deliberately left ``None`` — that
    absence is the auditable signature of a skip, and the only thing that
    distinguishes it from a producer that was asked and answered
    identically. :func:`decide.accept` does not touch it, which is why
    the seam holds.
    """
    for line_id in skip:
        lm = line_by_id[line_id]
        decide.accept(lm, lm.ocr_text, traces=traces)


def _work_items(
    chunks: list[ChunkRequest],
    *,
    skip: set[str],
    escalate: set[str],
    producer: EditProducer,
    escalation_producer: EditProducer | None,
) -> list[tuple[ChunkRequest, EditProducer]]:
    """Rebuild the plan as ``(chunk, producer)`` pairs.

    A skipped line leaves ``target_line_ids`` but stays in ``line_ids``:
    it is still context for its neighbours. A chunk with no targets left
    is dropped entirely — that is the economics, one producer call not
    spent. Escalated targets are split into a sibling chunk with the same
    context and disjoint targets, so the VLM corrects only the lines that
    earned its cost.
    """
    routed: list[tuple[ChunkRequest, EditProducer]] = []
    for chunk in chunks:
        targets = [t for t in chunk.targets() if t not in skip]
        if not targets:
            continue
        primary_targets = [t for t in targets if t not in escalate]
        escalate_targets = [t for t in targets if t in escalate]
        if primary_targets:
            routed.append(
                (chunk, producer)
                if primary_targets == chunk.targets()
                else (
                    chunk.model_copy(update={"target_line_ids": primary_targets}),
                    producer,
                )
            )
        if escalate_targets:
            assert escalation_producer is not None  # can_escalate
            routed.append(
                (
                    chunk.model_copy(
                        update={
                            "target_line_ids": escalate_targets,
                            "chunk_id": f"{chunk.chunk_id}#esc",
                        }
                    ),
                    escalation_producer,
                )
            )
    return routed
