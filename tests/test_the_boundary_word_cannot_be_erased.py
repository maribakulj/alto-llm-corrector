"""`E5b` — the word that continues a broken word may not be erased.

A ``PART2`` line opens on the second half of a word cut at the previous
line's edge. Erase that word and the pair reads ``plu-`` + ``et le reste``:
the line survives, so the non-emptiness check is satisfied, and the word the
mark pointed at is gone. ``_e5_hyphen_ok``'s docstring claimed the non-empty
result covered this; it does not, and ``docs/promises.md`` graded the row
"aucune, et la garde n'existe pas".

**Why "erased" and not "changed"** — measured on a real Mistral run over
1 433 ``PART2``/``BOTH`` lines, not chosen:

============================  =======  ======
what the model did to it      lines    share
============================  =======  ======
left it alone                     900   62.8%
corrected it (recognisable)       170   11.9%
replaced it (unrecognisable)      362   25.3%
erased it                           1    0.1%
============================  =======  ======

The 25% matter. A ``PART2``'s first word is where OCR is worst, often
reduced to one stray character, so a *correct* restoration scores near-zero
similarity: ``'•'`` → ``'seil'``, ``';'`` → ``'dré'``, ``'j'`` →
``'parole'``. A minimum-similarity rule would refuse **23–31%** of real
corrections depending on the threshold — and refuse them precisely where
correction is worth most. Refusing only ERASURE costs **0** of those lines
(the single erasure was the model returning an empty line, which the
non-emptiness check already refuses).

So this guard is insurance, and says so: it names the one gesture no
legitimate correction makes, and carries no threshold to recalibrate.

**The hole it closes is narrow and real.** Three protections already stand —
the reconciler validates the join on explicit pairs (92.6% of the corpus's
``PART2`` lines), a boundary-word comparison covers the plain heuristic case,
and an empty line is refused outright. What is left needs all three of:
heuristic pair, boundary word erased, AND the following word sharing two
leading characters with it (which bypasses the second). Measured across
4 752 real ``PART2`` lines: **0 occurrences**. Reproducible on a constructed
line, which is why it is worth closing at zero cost rather than documenting.
"""

from __future__ import annotations

from saknussemm.core.editing import (
    EditScript,
    RangeAnchor,
    ReplaceSpan,
    apply_edit_script,
)
from saknussemm.core.schemas import HyphenRole, LineManifest
from saknussemm.core.schemas.manifest import Coords

_SOURCE = "sieurs siennes et le reste"


def _line(role: HyphenRole) -> LineManifest:
    return LineManifest(
        line_id="l1",
        page_id="P1",
        block_id="B1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=100, height=10),
        ocr_text=_SOURCE,
        hyphen_role=role,
    )


def _apply(text: str, *, role: HyphenRole, end: int = 6):
    return apply_edit_script(
        EditScript(
            ops=[
                ReplaceSpan(
                    line_id="l1", anchor=RangeAnchor(start=0, end=end), text=text
                )
            ]
        ),
        {"l1": _SOURCE},
        line_by_id={"l1": _line(role)},
    )


def test_erasing_the_boundary_word_is_refused() -> None:
    """The gesture the guard exists for, on the shape that reaches it.

    ``'siennes'`` shares two leading characters with ``'sieurs'``, which is
    what bypasses the heuristic boundary-word comparison downstream. Without
    this guard the pair reads ``plu-`` + ``siennes et le reste``.
    """
    result = _apply("", role=HyphenRole.PART2)
    assert [r.reason for r in result.rejected] == ["e5_boundary_word"]
    assert result.text_by_id == {}


def test_whitespace_is_not_a_replacement() -> None:
    """Erasure dressed as a substitution is still erasure."""
    assert [r.reason for r in _apply("   ", role=HyphenRole.PART2).rejected] == [
        "e5_boundary_word"
    ]


def test_replacing_it_with_something_unrecognisable_is_ALLOWED() -> None:
    """The measured half, and the reason there is no similarity threshold.

    On real data the boundary word is replaced by something unrecognisable
    25% of the time, and those are good corrections — ``'•'`` → ``'seil'``.
    A rule that refused them would refuse a quarter of the corrections on the
    lines where OCR is worst.
    """
    result = _apply("xyz", role=HyphenRole.PART2)
    assert result.rejected == []
    assert result.text_by_id == {"l1": "xyz siennes et le reste"}


def test_correcting_it_is_allowed() -> None:
    result = _apply("sieurs", role=HyphenRole.PART2)
    assert result.rejected == []


def test_a_span_that_does_not_cover_the_whole_word_is_allowed() -> None:
    """The rule is about ERASING the word, not about touching its letters.

    Deleting one character of it is an ordinary correction — ``'ſieurs'`` →
    ``'sieurs'`` deletes and inserts inside the word — and a rule that
    refused any deletion overlapping it would catch those too.
    """
    result = _apply("", role=HyphenRole.PART2, end=3)
    assert result.rejected == []
    assert result.text_by_id == {"l1": "urs siennes et le reste"}


def test_a_line_that_continues_nothing_is_not_guarded() -> None:
    """A plain line's first word is just a word. Guarding it would refuse
    ordinary edits for a reason that only applies to a broken word."""
    assert _apply("", role=HyphenRole.NONE).rejected == []


def test_a_BOTH_line_is_guarded_too() -> None:
    """A ``BOTH`` line is the middle of a chain: it continues a word AND
    breaks one, so both halves of `E5` apply to it.

    Its source has to END in a mark, or the forward check fires first and
    this test passes for the wrong reason — which is what the first version
    did.
    """
    source = "sieurs siennes et le re-"
    line = _line(HyphenRole.BOTH)
    line.ocr_text = source
    result = apply_edit_script(
        EditScript(
            ops=[ReplaceSpan(line_id="l1", anchor=RangeAnchor(start=0, end=6), text="")]
        ),
        {"l1": source},
        line_by_id={"l1": line},
    )
    assert [r.reason for r in result.rejected] == ["e5_boundary_word"]
