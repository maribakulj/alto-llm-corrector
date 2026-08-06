"""Which reason survives when two passes revert the same line (`RM-01`).

Characterisation, not aspiration: every assertion here records what the
code does TODAY, so that `RM-01` — which will move all of these writes
behind one entry point — can prove it changed nothing it did not mean to.
Some of what is pinned below is arguably wrong. It is still pinned.

The rule is not "first writer wins" or "last writer wins". It is BOTH,
depending on the site, and the split is what makes the behaviour hard to
predict from a call site:

  * four writes are UNCONDITIONAL — ``_apply_line_acceptance`` (three of
    them) and ``_fall_back_to_source`` pass ``fallback_reason`` straight
    to ``_set_trace``, which assigns. Last writer wins.
  * three writes DEFER — ``_extend_to_units``, ``_refresh_pair_traces``
    and ``_apply_unit_reverts`` each guard with ``if not
    trace.fallback_reason``. First writer wins.

And the asymmetry that matters most is not between the two groups, it is
inside the deferring one: those three passes change ``corrected_text``
and ``status`` **unconditionally** while changing the reason only when
there is room. A line can therefore be reverted by a pass whose name
appears nowhere in its reason — the text says one thing happened, the
audit trail says another. :func:`test_a_second_revert_keeps_the_first_
reason_though_it_did_the_reverting` is that case, and it is the single
most useful line in this file for whoever executes `RM-01`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from corrigenda.core.acceptance import _apply_unit_reverts
from corrigenda.core.identity import line_ref
from corrigenda.core.outcome import _extend_to_units, _fall_back_to_source
from corrigenda.core.schemas import HyphenRole, LineStatus

from tests.decision._state import document, line

SRC = Path(__file__).parent.parent.parent / "src" / "corrigenda"


def _one_line(reason: str | None = None):
    lines = [line(1, "aaa", "AAA")]
    manifest, all_lines, traces = document(lines)
    if reason is not None:
        traces[line_ref(lines[0])].fallback_reason = reason
    return lines, all_lines, traces


def _linked_pair(partner_reason: str | None = None):
    """A PART1/PART2 unit, built as data — no pairing logic involved."""
    tail = line(1, "par-", "PAR-")
    head = line(2, "tir", "TIR")
    tail.hyphen_role = HyphenRole.PART1
    tail.hyphen_pair_line_id = head.line_id
    head.hyphen_role = HyphenRole.PART2
    head.hyphen_pair_line_id = tail.line_id
    manifest, all_lines, traces = document([tail, head])
    if partner_reason is not None:
        traces[line_ref(head)].fallback_reason = partner_reason
    return tail, head, all_lines, traces


# ---------------------------------------------------------------------------
# The unconditional writer
# ---------------------------------------------------------------------------


def test_fall_back_to_source_overwrites_an_existing_reason() -> None:
    """``_fall_back_to_source`` assigns through ``_set_trace``: whatever a
    previous pass recorded is replaced."""
    lines, _all_lines, traces = _one_line("first_reason")
    _fall_back_to_source(lines, traces, reason="second_reason")
    assert traces[line_ref(lines[0])].fallback_reason == "second_reason"


# ---------------------------------------------------------------------------
# The deferring writers
# ---------------------------------------------------------------------------


def test_extend_to_units_never_overwrites() -> None:
    """A line dragged down by its unit keeps the reason it already had —
    ``hyphen_unit_fallback`` only fills a hole."""
    lines, _all_lines, traces = _one_line("first_reason")
    _extend_to_units(
        lines,
        traces,
        line_by_id={lm.line_id: lm for lm in lines},
        cross_page_partners=None,
    )
    assert traces[line_ref(lines[0])].fallback_reason == "first_reason"


def test_unit_revert_stamps_the_atomicity_reason_on_a_silent_member() -> None:
    """A member pulled down by its partner, with nothing on its trace,
    gets the calling pass's vocabulary."""
    tail, head, all_lines, traces = _linked_pair()
    _apply_unit_reverts(
        reverts={line_ref(tail): "reason_of_the_flagged_line"},
        all_lines=all_lines,
        traces=traces,
        atomicity_reason="pulled_by_unit",
    )
    assert traces[line_ref(head)].fallback_reason == "pulled_by_unit"
    assert head.corrected_text == head.ocr_text
    assert head.status is LineStatus.FALLBACK


def test_unit_revert_leaves_a_members_own_earlier_reason_alone() -> None:
    """The same pull, onto a member that already explained itself: the
    earlier reason survives, which is the behaviour you want."""
    tail, head, all_lines, traces = _linked_pair("earlier_reason_of_the_member")
    _apply_unit_reverts(
        reverts={line_ref(tail): "reason_of_the_flagged_line"},
        all_lines=all_lines,
        traces=traces,
        atomicity_reason="pulled_by_unit",
    )
    assert traces[line_ref(head)].fallback_reason == "earlier_reason_of_the_member"


def test_a_second_revert_keeps_the_first_reason_though_it_did_the_reverting() -> None:
    """The sharp case, and the reason this file exists.

    ``_apply_unit_reverts`` writes ``corrected_text`` and ``status``
    unconditionally but the reason only when the trace is empty. A line
    that already carried a reason is therefore reverted BY THIS PASS while
    the audit trail goes on attributing it to the earlier one.

    Pinned as-is. It is defensible ("the first cause is the real cause")
    and it is also how a run reports a ``token_realign`` gate as an
    ``adjacent_duplicate`` — a consumer counting reasons gets a number
    that is off by however many lines were flagged twice. `RM-01` should
    decide this deliberately rather than inherit it; whatever it decides,
    this test has to be updated ON PURPOSE.
    """
    lines, all_lines, traces = _one_line("first_reason")
    result = _apply_unit_reverts(
        reverts={line_ref(lines[0]): "the_reason_that_actually_reverted_it"},
        all_lines=all_lines,
        traces=traces,
    )

    # The revert happened, and this pass is the one that did it.
    assert lines[0].corrected_text == lines[0].ocr_text
    assert lines[0].status is LineStatus.FALLBACK
    assert result[line_ref(lines[0])] == "the_reason_that_actually_reverted_it"

    # The trace still names the earlier cause. This is the gap.
    assert traces[line_ref(lines[0])].fallback_reason == "first_reason"


# ---------------------------------------------------------------------------
# The asymmetry itself, pinned statically
# ---------------------------------------------------------------------------


def _reason_writes() -> tuple[int, int]:
    """``(guarded, unguarded)`` writes of ``fallback_reason`` in ``core``.

    Guarded = the assignment sits under an ``if`` that tests the field
    (``if not trace.fallback_reason``). Unguarded = it is handed to
    ``_set_trace`` as a keyword, which always assigns.
    """
    guarded = unguarded = 0
    for path in sorted((SRC / "core").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                assigns = [
                    sub
                    for sub in ast.walk(node)
                    if isinstance(sub, ast.Assign)
                    and any(
                        isinstance(t, ast.Attribute) and t.attr == "fallback_reason"
                        for t in sub.targets
                    )
                ]
                if assigns and "fallback_reason" in ast.unparse(node.test):
                    guarded += len(assigns)
            elif isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                )
                if name == "_set_trace":
                    unguarded += sum(
                        1 for kw in node.keywords if kw.arg == "fallback_reason"
                    )
    return guarded, unguarded


def test_the_precedence_rule_is_split_four_ways_against_three() -> None:
    """Four writes assign, three defer. That split IS the precedence rule,
    and it lives nowhere but in the shape of seven ``if`` statements.

    When `RM-01` lands there should be ONE writer and this test should be
    deleted, not adjusted."""
    guarded, unguarded = _reason_writes()
    assert (guarded, unguarded) == (3, 4), (
        f"the precedence split moved to {guarded} deferring / {unguarded} "
        "assigning writes. If that was deliberate, update the behavioural "
        "pins above in the same commit — they are what says which reason a "
        "consumer actually sees."
    )
