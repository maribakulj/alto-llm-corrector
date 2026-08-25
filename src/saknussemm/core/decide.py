"""The one place a line's decision is written (ADR-013).

A line's decision is two manifest fields — ``corrected_text`` and
``status`` — plus the trace's ``fallback_reason``. Every write of them goes
through here; ``tests/decision/test_decision_write_exclusivity.py`` refuses
the first statement anywhere else in the package.

Three verbs, because there are three genuinely different things to say
about a line, and collapsing them would make the module lie about what
happened:

:func:`accept`
    A correction stands. Text and status both change.

:func:`fall_back`
    A correction is taken away and the line returns to its source. Text
    and status both change; the reason is recorded **only into an empty
    trace**.

:func:`renormalise`
    A decision already made keeps standing, and only its spelling
    changes. Text changes; status does not, because nothing was decided
    here.

**Why ``fall_back`` defers, and why that is not merely cautious**
(ADR-013). It rests on an invariant, verified over the corpora rather
than assumed, and pinned by
``tests/decision/test_fallback_reason_precedence.py``:

    **I-1 — a line carrying a ``fallback_reason`` has already been
    reverted: its final text equals its source text.**

So a second revert of an already-reverted line changes no text a reader
can see. The pass that actually took the correction away is the FIRST
one, and its reason is therefore the true one, not the stale one. A
last-writer-wins rule would name a pass that did nothing.

**The revert of text and status stays unconditional**, and that
asymmetry is deliberate: ``acceptance._apply_unit_reverts`` pulls hyphen
members that may not be reverted yet, and that pull is the whole of
ADR-010's fallback atomicity. Deferring the text too would leave a mixed
pair — one member at source, one corrected — which is the single state
the reconciler guarantees cannot survive.

**Why ``renormalise`` exists rather than reusing ``accept``.**
``finalize._preserve_break_chars``
forces the source line's word-break character onto an accepted
correction. It decides nothing: it does not choose between a proposal
and a source, it respells a choice already made, and it never runs on a
line that fell back (a reverted line has ``corrected_text ==
ocr_text``, which it skips). Routing it through ``accept`` would make it
assert ``CORRECTED`` on lines whose status it has no business setting —
a behaviour change bought for the tidiness of two verbs instead of
three. A reader must be able to tell what happened to a line from the call
alone, and "text only, decision untouched" is a third thing to say.
"""

from __future__ import annotations

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.schemas import LineManifest, LineStatus, LineTrace
from saknussemm.core.traces import _set_trace


#: Le vocabulaire CLOS des raisons de repli.
#:
#: Un repli est ce qu'un consommateur lit en premier quand une ligne n'a pas
#: été corrigée, et il l'agrège par ce code — ``fallback_reason_counts`` coupe
#: sur le ``:`` et compte le préfixe. Un code inconnu dans un rapport est donc
#: un défaut de la bibliothèque, pas une raison inédite.
#:
#: L'ensemble était ouvert : vingt littéraux dispersés sur huit modules, et
#: rien ne disait combien il y en avait. `docs/la-vie-d-une-ligne.md` les
#: documente pour un lecteur ; cette constante les ferme pour un programme, et
#: ``tests/test_the_fallback_reasons_are_a_closed_set.py`` refuse un
#: vingt-et-unième qui n'y figurerait pas.
#:
#: Volontairement un ``frozenset[str]`` et non un ``Enum`` : ``DecisionReason.code``
#: est ``str`` sur une surface publique versionnée, et le durcir serait un
#: changement de contrat, pas une clôture.
FALLBACK_REASON_CODES: frozenset[str] = frozenset(
    {
        # -- étage C : la ligne et ses voisines (`guards.check_line`) -------
        "too_different_from_source",
        "closer_to_previous_line",
        "closer_to_next_line",
        "absorbs_previous_line",
        "absorbs_next_line",
        # Le défaut de `check_line` quand une branche de refus ne nomme pas
        # sa raison. Aucune ne le fait aujourd'hui ; il reste parce que le
        # site d'appel ne peut pas le prouver.
        "rejected",
        # -- césure : l'unité, jamais un membre seul (ADR-010) -------------
        "hyphen_pair_fallback",
        "hyphen_partner_fell_back",
        "hyphen_unit_fallback",
        "orphan_hyphen_completed",
        # -- passes document-wide (`core/finalize.py`) ---------------------
        "adjacent_duplicate_detected",
        "adjacent_duplicate_pair_atomicity",
        "boundary_migration_forward",
        "boundary_migration_backward",
        "format_loss",
        "format_loss_pair_atomicity",
        "token_realign",
        "token_realign_pair_atomicity",
        # -- niveau chunk (`core/outcome.py`) ------------------------------
        "all_attempts_exhausted",
        "chunk_error_absorbed",
    }
)


def accept(
    line: LineManifest,
    text: str,
    *,
    traces: dict[LineRef, LineTrace] | None = None,
) -> None:
    """This text is the line's decision, and it stands.

    Used for a correction the guards passed, and for a line the QE router
    confirmed clean without asking any producer (``text`` is then the
    line's own OCR text — a skip is still a decision, and the auditable
    signature that distinguishes it from a producer answering identically
    is the trace's ``model_input_text`` staying ``None``, which this
    function does not touch).
    """
    line.corrected_text = text
    line.status = LineStatus.CORRECTED
    _set_trace(
        traces,
        line,
        projected_text=text,
        validation_status=LineStatus.CORRECTED.value,
    )


def fall_back(
    line: LineManifest,
    *,
    reason: str,
    traces: dict[LineRef, LineTrace] | None = None,
) -> None:
    """Take the correction away: the line goes back to its source text.

    Text and status are written unconditionally; ``reason`` is recorded
    only when the trace carries none, so the pass that FIRST removed the
    correction keeps the attribution (ADR-013, invariant I-1). See this
    module's docstring for why that asymmetry is the correct one and not
    an oversight.
    """
    line.corrected_text = line.ocr_text
    line.status = LineStatus.FALLBACK
    _set_trace(
        traces,
        line,
        projected_text=line.ocr_text,
        validation_status=LineStatus.FALLBACK.value,
    )
    if traces is None:
        return
    trace = traces.get(line_ref(line))
    if trace is not None and not trace.fallback_reason:
        trace.fallback_reason = reason


def renormalise(line: LineManifest, text: str) -> None:
    """Respell a decision that already stands — no status, no reason.

    The narrow verb for a pass that normalises decided text rather than
    deciding anything (``finalize._preserve_break_chars``). Deliberately
    does not touch the trace: the caller's historical behaviour wrote
    nothing there, and widening it here would be a behaviour change
    smuggled into a migration.
    """
    line.corrected_text = text


__all__ = ["FALLBACK_REASON_CODES", "accept", "fall_back", "renormalise"]
