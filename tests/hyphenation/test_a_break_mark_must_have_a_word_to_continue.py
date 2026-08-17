"""A span may not erase the word a break mark continues.

`E5` promises that a span-edited hyphen line keeps its trailing mark
**and** a non-empty boundary word. Only the first half was checked, and
the docstring said the second was "guaranteed by the non-empty result
check". It was not — the result is non-empty precisely because the mark is
still there.

Measured on 2026-08-17, before the guard:

    canonical : 'Le peuple att-'
    span [10,13) -> ''
    result    : {'L1': 'Le peuple -'}   rejected: []

A break mark with nothing in front of it, accepted, and the ALTO carries
``<String CONTENT="-"/>`` — a ``String`` holding a bare hyphen. The
control is what makes this a hole rather than an oversight: erasing the
mark *itself* was correctly refused all along. The guard watched the
punctuation and not the word.

`_part1_text_migrated` bounds how much a PART1 line may **grow** — words,
last word, length. **Nothing bounded how much it may shrink**, anywhere.

The rule here is exact, not heuristic: if the parser called this line
PART1, a word ended at the mark. A mark with only whitespace before it is
not a continuation, it is a dash. So no legitimate correction is refused —
none of them leaves a mark dangling.

**The backward side is deliberately not closed here.** A ``PART2`` line
can still lose its boundary word when the following word survives; the
etage-B guard compares first words and is bypassed when the next word
shares two leading characters. Closing that needs a similarity threshold,
which is a contract decision (`E5b` in the plan), not a defect fix. No
test in this file pins the bypass as expected behaviour — that is the
mistake this repository made three times on 2026-08-16.
"""

from __future__ import annotations

import pytest

from saknussemm.core.editing import (
    EditScript,
    RangeAnchor,
    ReplaceSpan,
    apply_edit_script,
)
from saknussemm.core.pairing import HYPHEN_CHARS
from saknussemm.core.schemas import Coords, HyphenRole, LineManifest

#: Both roles whose forward side carries a mark. ``BOTH`` is the middle of
#: a chain: it continues onto the next line too.
_FORWARD_ROLES = [HyphenRole.PART1, HyphenRole.BOTH]


def _line(role: HyphenRole, text: str) -> LineManifest:
    return LineManifest(
        line_id="L1",
        page_id="P1",
        block_id="B1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=10, height=10),
        ocr_text=text,
        hyphen_role=role,
    )


def _edit(canonical: str, role: HyphenRole, start: int, end: int, text: str):
    return apply_edit_script(
        EditScript(
            ops=[
                ReplaceSpan(
                    line_id="L1", anchor=RangeAnchor(start=start, end=end), text=text
                )
            ]
        ),
        {"L1": canonical},
        line_by_id={"L1": _line(role, canonical)},
    )


@pytest.mark.parametrize("mark", HYPHEN_CHARS)
@pytest.mark.parametrize("role", _FORWARD_ROLES)
def test_erasing_the_boundary_word_is_refused(mark: str, role: HyphenRole) -> None:
    canonical = f"Le peuple att{mark}"
    result = _edit(canonical, role, 10, 13, "")
    assert result.text_by_id == {}, (
        f"{canonical!r} on a {role.value} line became "
        f"{result.text_by_id.get('L1')!r}: the mark survived and the word it "
        "continues did not. The pair stays structurally present and becomes "
        "semantically incoherent, and the rewriter emits a String holding a "
        "bare break mark."
    )
    assert any(r.reason == "e5_hyphen" for r in result.rejected), (
        f"refused, but not by E5 — {[r.reason for r in result.rejected]}. A "
        "rejection for another reason would satisfy a weaker assertion while "
        "leaving this hole open."
    )


@pytest.mark.parametrize("mark", HYPHEN_CHARS)
@pytest.mark.parametrize("role", _FORWARD_ROLES)
def test_the_mark_itself_was_already_protected(mark: str, role: HyphenRole) -> None:
    """The control that makes the above a hole rather than an oversight.

    Erasing the mark was refused before this guard existed. Keeping this
    green is what says the two halves are complementary: one watches the
    punctuation, the other the word.
    """
    canonical = f"Le peuple att{mark}"
    result = _edit(canonical, role, len(canonical) - 1, len(canonical), "")
    assert result.text_by_id == {} and any(
        r.reason == "e5_hyphen" for r in result.rejected
    ), f"erasing the trailing {mark!r} was accepted — {result.text_by_id}"


@pytest.mark.parametrize("mark", HYPHEN_CHARS)
@pytest.mark.parametrize("role", _FORWARD_ROLES)
def test_an_edit_that_keeps_both_goes_through(mark: str, role: HyphenRole) -> None:
    """The other half: a guard that refused every span would satisfy the above."""
    canonical = f"Le peuple att{mark}"
    result = _edit(canonical, role, 0, 2, "La")
    assert result.text_by_id == {"L1": f"La peuple att{mark}"}, (
        f"a span leaving both the word and the {mark!r} intact was refused — "
        f"{result.rejected}. E5 guards the continuation, not the line."
    )


@pytest.mark.parametrize("mark", HYPHEN_CHARS)
@pytest.mark.parametrize("role", _FORWARD_ROLES)
def test_shortening_the_boundary_word_is_still_allowed(
    mark: str, role: HyphenRole
) -> None:
    """The precise scope: the word must survive, not survive unchanged.

    Deleting OCR noise from the boundary word — a stray character before
    the mark — is a legitimate correction, and the rule must not forbid it.
    This is where a rule written on the *op* rather than the *result*
    would have over-refused: it would have seen an empty replacement
    covering the last character before the mark and stopped there.
    """
    canonical = f"Le peuple att.{mark}"
    result = _edit(canonical, role, 13, 14, "")
    assert result.text_by_id == {"L1": f"Le peuple att{mark}"}, (
        f"removing a stray {'.'!r} from the boundary word was refused — "
        f"{result.rejected}. The word still ends at the mark; only noise left."
    )
