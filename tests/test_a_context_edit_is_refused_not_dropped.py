"""An edit on a context line is now REFUSED, and the report says so.

`E1` reads "``line_id`` in the targeted chunk". Its check had two clauses,
and `docs/promises.md` graded the row **partial** because removing the first
one left the suite green. The 2026-08-17 investigation
(`test_an_edit_may_not_land_on_a_context_line.py`) found why, and it was not
a weak test: **the clause was unreachable.** ``attempt.py`` passed every
chunk line as ``chunk_line_ids``, so "outside the set" could only be true
where "unknown" already was.

The protection was real anyway — measured, 13 of 52 payloads on
``X0000002.xml`` open with a context line, and none of those edits reaches a
decision — but it came from target filtering far downstream, and nothing
named it. That file said what closing it needed: pass the TARGET set, and a
field on the report to carry the refusal. ``edit_rejections`` landed on
2026-08-17, so this is that.

**The corrected text does not move.** A context edit was dropped before and
is refused now; the file on disk is the same either way. What changes is that
one of the two tells the operator a producer proposed something the engine
declined, and with which of the two accusations: an id nobody knows is a
producer inventing a line, a known id outside the target set is a producer
answering a question it was not asked. Reporting both as ``e1_unknown_line``
made the second unreadable — and the second is the common one, because a
payload does not mark which of its lines are targets.
"""

from __future__ import annotations

from saknussemm.core.editing import (
    EditScript,
    RangeAnchor,
    ReplaceSpan,
    apply_edit_script,
)


def _script(line_id: str) -> EditScript:
    return EditScript(
        ops=[
            ReplaceSpan(line_id=line_id, anchor=RangeAnchor(start=0, end=3), text="xyz")
        ]
    )


def test_a_known_line_outside_the_target_set_is_refused_as_context() -> None:
    """The clause that could not fire before, firing.

    ``l2`` is in the canonical texts — it is a real line of the payload — and
    absent from the target set. That combination was unreachable while the
    caller passed every chunk line as the target set.
    """
    result = apply_edit_script(
        _script("l2"),
        {"l1": "aaa bbb", "l2": "ccc ddd"},
        chunk_line_ids={"l1"},
    )
    assert [r.reason for r in result.rejected] == ["e1_context_line"]
    assert result.text_by_id == {}


def test_an_unknown_line_keeps_its_own_accusation() -> None:
    """The other half: the two must not collapse back into one code.

    A producer inventing ``l9`` is a different failure from a producer
    correcting a line it was shown for context, and an operator reading a
    refusal rate needs to tell them apart.
    """
    result = apply_edit_script(
        _script("l9"),
        {"l1": "aaa bbb", "l2": "ccc ddd"},
        chunk_line_ids={"l1"},
    )
    assert [r.reason for r in result.rejected] == ["e1_unknown_line"]


def test_an_unknown_line_is_unknown_even_when_every_line_is_a_target() -> None:
    """`chunk_line_ids=None` means "no target filtering", not "everything is
    fine": an id with no canonical text is still an invention."""
    result = apply_edit_script(_script("l9"), {"l1": "aaa bbb"}, chunk_line_ids=None)
    assert [r.reason for r in result.rejected] == ["e1_unknown_line"]


def test_a_target_line_is_still_edited() -> None:
    """The control. A guard that refused targets too would pass every
    assertion above while correcting nothing at all."""
    result = apply_edit_script(
        _script("l1"),
        {"l1": "aaa bbb", "l2": "ccc ddd"},
        chunk_line_ids={"l1"},
    )
    assert result.rejected == []
    assert result.text_by_id == {"l1": "xyz bbb"}
