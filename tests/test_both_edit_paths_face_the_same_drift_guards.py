"""`E6b` — the same result gets the same verdict, whichever op proposed it.

`E4` and `E5` were span-only. The default LLM producer emits whole-line
replacements, so the two drift guards applied to the rarer vocabulary and not
to the common one: a line reaching acceptance was judged on meaning alone,
while the identical text arriving as a span faced two more checks first.
``docs/promises.md`` graded the row **aucune**.

**Closed after measuring the cost**, on 1 796 real proposals from
``mistral-small-latest`` over 3 135 lines:

- `E4` refuses **0**. Median corrected line changes 20 characters, worst 168,
  against a budget of 200. Free.
- `E5` refuses **205**, of which **204 were already refused** by downstream
  guards — it rejects earlier and names why, not more.
- The 205th is why `E5`'s forward rule was refined at the same time, and it
  is the subject of the last test here.

Applied to the run's own data afterwards: **204 refused, 0 verdicts
changed.** The parity is literally free.
"""

from __future__ import annotations

from saknussemm.core.editing import EditScript, ReplaceLine, apply_edit_script
from saknussemm.core.schemas import GuardConfig, HyphenRole, LineManifest
from saknussemm.core.schemas.manifest import Coords


def _line(text: str, role: HyphenRole) -> LineManifest:
    return LineManifest(
        line_id="l1",
        page_id="P1",
        block_id="B1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=100, height=10),
        ocr_text=text,
        hyphen_role=role,
    )


def _apply(
    source: str, proposed: str, role: HyphenRole, guard: GuardConfig | None = None
):
    return apply_edit_script(
        EditScript(ops=[ReplaceLine(line_id="l1", text=proposed)]),
        {"l1": source},
        line_by_id={"l1": _line(source, role)},
        **({"guard_config": guard} if guard else {}),
    )


def test_a_whole_line_that_loses_its_break_mark_is_refused() -> None:
    """The commonest of the 204, and it reached acceptance before.

    A ``PART1`` line promises a continuation. Drop its mark and the pair
    stops being a pair — measured on real data as
    ``'…les memb/os. du bu-'`` → ``'…les membres du bu'``.
    """
    result = _apply("les memb/os. du bu-", "les membres du bu", HyphenRole.PART1)
    assert [r.reason for r in result.rejected] == ["e5_hyphen"]


def test_a_whole_line_answering_with_the_NEXT_lines_text_is_refused() -> None:
    """The gravest shape found, and the one a text guard cannot see alone.

    ``'…dans la-'`` came back as ``'galerie des Fêtes.'`` — the following
    line's content on this line's identity. It is refusable here for a
    precise reason (the mark is gone) rather than as a generic dissimilarity.
    """
    result = _apply("douré du cercle dans la-", "galerie des Fêtes.", HyphenRole.PART1)
    assert [r.reason for r in result.rejected] == ["e5_hyphen"]


def test_a_whole_line_rewrite_past_the_budget_is_refused() -> None:
    """`E4`'s half of the parity.

    It refuses nothing on real data — the worst real correction changes 168
    characters against a budget of 200 — so the bound is exercised here with
    a budget small enough to reach, which is the only way to know it is
    wired in at all rather than merely present.
    """
    result = _apply(
        "une ligne ordinaire",
        "un texte entierement different",
        HyphenRole.NONE,
        GuardConfig(edit_line_max_changed_chars=5),
    )
    assert [r.reason for r in result.rejected] == ["e4_line_budget"]


def test_an_ordinary_whole_line_correction_still_lands() -> None:
    """The control, and the measured claim: the parity costs zero verdicts.

    Applied to the run's own 1 796 proposals afterwards, the two guards
    refused 204 and changed **no** verdict — every one was already refused
    downstream.
    """
    result = _apply("le roi de Frauce", "le roi de France", HyphenRole.NONE)
    assert result.rejected == []
    assert result.text_by_id == {"l1": "le roi de France"}


def test_a_space_before_the_mark_that_came_from_the_SOURCE_is_kept() -> None:
    """The 205th, and why `E5`'s forward rule was refined rather than applied.

    `E5` refuses a break mark with a space before it: a mark with nothing to
    continue is a dash. But on this real line the space is in the SOURCE, and
    the proposal is an excellent correction of it — this is `#126`, the line
    whose delivery cost a whole document until the rewriter learnt to carry
    that space.

    Judging the result alone punishes a producer for being faithful. Measured
    over 205 refusals: the gap is inherited once and introduced zero times.
    """
    source = "a la revision d: s juy<nnen!s e d -"
    proposed = "à la révision des jugements et d -"
    result = _apply(source, proposed, HyphenRole.PART1)
    assert result.rejected == [], result.rejected
    assert result.text_by_id == {"l1": proposed}


def test_a_space_before_the_mark_the_CORRECTION_introduced_is_refused() -> None:
    """The other half of the refinement, or it would excuse everything.

    A source whose mark follows its word directly, answered with one where a
    space has appeared, is the erasure `E5` exists for — the word went and
    the mark stayed.
    """
    result = _apply("le peuple att-", "le peuple -", HyphenRole.PART1)
    assert [r.reason for r in result.rejected] == ["e5_hyphen"]
