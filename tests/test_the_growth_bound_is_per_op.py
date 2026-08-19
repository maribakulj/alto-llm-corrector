"""`E4a` — a span may grow by so much, and each one is judged alone.

`docs/promises.md` carried this as **partial**: the guard existed and one
test reached it, but with a single op in the script. One op cannot tell a
PER-OP bound from a per-LINE one — both accept it and both reject it — so
the word that makes the promise a promise was the one thing unproven. Nor
was there a negative control: a test that only ever asserts rejection stays
green against a guard that rejects everything.

**And the obvious two-op test does not close it either.** Two spans both
within the ratio prove nothing, because ``len_i <= r * span_i`` for each op
implies it for their sum: a cumulative bound accepts exactly the same
scripts. Written that way first, and the mutation that turns the guard
cumulative left it green. The case that discriminates runs the other way —
see :func:`test_a_quiet_op_cannot_pay_for_a_greedy_one`.

Both halves are here. `E4b`, the per-line changed-character budget, is a
different sentence with its own tests (`test_editing.py`); this file is only
about the ratio each span is measured against on its own.
"""

from __future__ import annotations

from saknussemm.core.editing import (
    EditScript,
    RangeAnchor,
    ReplaceSpan,
    apply_edit_script,
)
from saknussemm.core.schemas import GuardConfig

#: Ratio 3, and a line long enough to carry two independent spans.
_GUARD = GuardConfig(edit_span_max_growth_ratio=3.0, edit_line_max_changed_chars=1000)
_LINE = "aaaa bbbb cccc dddd"


def _apply(*ops: ReplaceSpan):
    return apply_edit_script(
        EditScript(ops=list(ops)), {"l1": _LINE}, guard_config=_GUARD
    )


def _span(start: int, end: int, text: str) -> ReplaceSpan:
    return ReplaceSpan(
        line_id="l1", anchor=RangeAnchor(start=start, end=end), text=text
    )


def test_an_op_under_the_ratio_is_accepted() -> None:
    """The negative control the promise was missing.

    Four source characters may become twelve at a ratio of 3. Without this,
    every assertion in the file would still pass against a guard that
    rejected every span, and the bound would be unfalsifiable.
    """
    result = _apply(_span(0, 4, "x" * 12))
    assert result.rejected == []
    assert result.text_by_id["l1"].startswith("x" * 12)


def test_one_character_past_the_ratio_is_rejected() -> None:
    """And the bound is where it says it is, not somewhere nearby."""
    result = _apply(_span(0, 4, "x" * 13))
    assert [r.reason for r in result.rejected] == ["e4_span_growth"]


def test_a_quiet_op_cannot_pay_for_a_greedy_one() -> None:
    """The word the promise turns on, and the case that actually tests it.

    The first attempt here was two spans each exactly at the ratio, asserting
    both survive. It proves nothing: if every op satisfies
    ``len_i <= r * span_i`` then so does their sum, so a per-LINE reading
    accepts precisely the same scripts. Mutating the guard into a cumulative
    one left that test green — which is how a test can guard a word it never
    checks.

    A summed bound is strictly WEAKER, so the discriminating case runs the
    other way: one op that shrinks a long span, and one that blows the ratio
    on a short one. Per op the second is refused. Summed — 12 characters out
    of 11 spanned, against a ratio of 3 — the first one's slack pays for it
    and the greedy op sails through.
    """
    result = _apply(_span(0, 10, "z"), _span(11, 12, "y" * 11))
    assert [r.reason for r in result.rejected] == ["e4_span_growth"]
    assert "y" * 11 not in result.text_by_id["l1"]


def test_two_ops_within_the_ratio_both_land() -> None:
    """The companion control: per-op strictness must not refuse the ordinary.

    Two spans, each at the ratio, both accepted — so the case above is the
    guard being precise rather than the guard being harsh.
    """
    result = _apply(_span(0, 4, "x" * 12), _span(5, 9, "y" * 12))
    assert result.rejected == []
    assert "x" * 12 in result.text_by_id["l1"]
    assert "y" * 12 in result.text_by_id["l1"]


def test_a_second_op_over_the_ratio_takes_only_itself_down() -> None:
    """Rejection is per op too, which is the other half of "per op".

    A bound that rejected the whole script on one bad span would be
    indistinguishable from a per-line bound at exactly the moment it
    matters. The good span must still land.
    """
    result = _apply(_span(0, 4, "x" * 12), _span(5, 9, "y" * 13))
    assert [r.reason for r in result.rejected] == ["e4_span_growth"]
    assert "x" * 12 in result.text_by_id["l1"]
    assert "y" * 13 not in result.text_by_id["l1"]


def test_an_insertion_is_measured_against_one_character_not_zero() -> None:
    """A zero-length span would make every ratio infinite.

    `max(1, span_len)` in the guard is what stops an insertion anchored at a
    point from being unbounded. Asserted here because it is the one place the
    ratio has no natural denominator, and reading it as `0` would silently
    exempt exactly the ops that add the most text.
    """
    assert _apply(_span(4, 4, "xyz")).rejected == []
    assert [r.reason for r in _apply(_span(4, 4, "xyzw")).rejected] == [
        "e4_span_growth"
    ]
