"""The one place a line's decision is written (ADR-013, `RM-01`).

A line's decision is two manifest fields — ``corrected_text`` and
``status`` — plus the trace's ``fallback_reason``. Twenty-two statements
across seven functions in five modules used to write them, and what kept
them coherent was the order the document-wide passes happened to run in.
This module is where they are collapsing to, one site per commit;
``tests/decision/test_decision_write_exclusivity.py`` is the ratchet that
counts what is left.

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

**Why ``renormalise`` exists rather than reusing ``accept``** (`RM-01`
phase 2, the question ADR-013 left open). ``finalize._preserve_break_chars``
forces the source line's word-break character onto an accepted
correction. It decides nothing: it does not choose between a proposal
and a source, it respells a choice already made, and it never runs on a
line that fell back (a reverted line has ``corrected_text ==
ocr_text``, which it skips). Routing it through ``accept`` would make it
assert ``CORRECTED`` on lines whose status it has no business setting —
a behaviour change bought for the tidiness of having two verbs instead
of three. The point of this module is that a reader can tell what
happened to a line from the call; a verb that means "text only, decision
untouched" is the honest one.
"""

from __future__ import annotations

from lidenbrock.core.identity import LineRef, line_ref
from lidenbrock.core.schemas import LineManifest, LineStatus, LineTrace
from lidenbrock.core.traces import _set_trace


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


__all__ = ["accept", "fall_back", "renormalise"]
