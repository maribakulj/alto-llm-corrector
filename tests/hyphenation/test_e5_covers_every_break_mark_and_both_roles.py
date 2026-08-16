"""E5 must hold for every break mark in the repertoire, and for ``BOTH``.

`E5` says a hyphenated line edited by span keeps its trailing break mark:
severing the mark would leave a pair whose two halves no longer announce
that they belong together, and `E6` reconciliation runs too late to
notice.

The guard is written against the whole repertoire —
``result_text.rstrip().endswith(HYPHEN_CHARS)`` over
``("-", "¬", "⸗", "\\u00ad", "‐", "‑")`` — and against both opening roles.
**The tests were written against one of each**: an ASCII ``-`` on a
``PART1`` line (``tests/test_editing.py``).

`L5` had already swept the repertoire across five guard sites — see
``test_break_mark_repertoire_in_guards.py``, which counted 32 of 363
hyphenated lines falling outside ASCII-only checks. **E5 was not one of
the five.** That sweep covers pairing and reconciliation; this one covers
the edit protocol, whose ``apply_edit_script`` path those tests never
enter. The role that carries a three-line chain, ``BOTH``, was unexercised
on either side.

That mattered on measurement rather than in principle: the two paired
PAGE/ALTO fixtures in ``examples/page/`` mark every one of their hyphens
with ``¬`` (U+00AC), not with ``-``. The one mark the suite exercised was
the one the corpus does not use.

Proven by mutation on 2026-08-16: narrowing the guard's repertoire to
``"-"`` fails this and leaves ``test_editing.py`` green, as does dropping
``BOTH`` from the roles E5 applies to.
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

#: The roles that open a hyphen unit — the ones whose forward side must
#: keep its mark. ``BOTH`` is the middle of a chain: it closes one unit and
#: opens the next, so it is a forward side too.
_OPENING_ROLES = [HyphenRole.PART1, HyphenRole.BOTH]


def _line(role: HyphenRole) -> LineManifest:
    return LineManifest(
        line_id="l1",
        page_id="p",
        block_id="b",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=10, height=10),
        ocr_text="x",
        hyphen_role=role,
    )


def _edit(canonical: str, role: HyphenRole, start: int, end: int, text: str):
    return apply_edit_script(
        EditScript(
            ops=[
                ReplaceSpan(
                    line_id="l1", anchor=RangeAnchor(start=start, end=end), text=text
                )
            ]
        ),
        {"l1": canonical},
        line_by_id={"l1": _line(role)},
    )


def test_the_repertoire_is_what_this_file_thinks_it_is() -> None:
    """A repertoire trimmed to one mark would make the sweep below vacuous."""
    assert len(HYPHEN_CHARS) >= 5, (
        f"HYPHEN_CHARS is now {HYPHEN_CHARS!r}. This file sweeps it to prove "
        "E5 covers more than the ASCII dash; a shortened repertoire would "
        "shrink the sweep silently rather than fail it."
    )
    assert "-" in HYPHEN_CHARS and "¬" in HYPHEN_CHARS


@pytest.mark.parametrize("mark", HYPHEN_CHARS)
@pytest.mark.parametrize("role", _OPENING_ROLES)
def test_severing_the_break_mark_is_rejected(mark: str, role: HyphenRole) -> None:
    canonical = f"word{mark}"
    result = _edit(canonical, role, len(canonical) - 1, len(canonical), "")
    assert result.text_by_id == {}, (
        f"an edit removing the trailing {mark!r} from a {role.value} line was "
        "applied. E5 exists so a pair cannot lose the mark that announces it "
        "continues on the next line; E6 reconciliation runs too late to "
        "catch it."
    )
    assert any(r.reason == "e5_hyphen" for r in result.rejected), (
        f"the edit was rejected but not by E5 — {[r.reason for r in result.rejected]}. "
        "A rejection for the wrong reason would still pass a weaker assertion "
        "while leaving E5 itself unexercised."
    )


@pytest.mark.parametrize("mark", HYPHEN_CHARS)
@pytest.mark.parametrize("role", _OPENING_ROLES)
def test_an_edit_that_keeps_the_break_mark_goes_through(
    mark: str, role: HyphenRole
) -> None:
    """The other half: E5 must not reject edits that respect it.

    Without this, a guard that rejected every span edit on a hyphenated
    line would satisfy the assertions above.
    """
    result = _edit(f"word{mark}", role, 0, 2, "Wo")
    assert result.text_by_id == {"l1": f"Word{mark}"}, (
        f"a span edit that leaves the trailing {mark!r} intact on a "
        f"{role.value} line was rejected — {result.rejected}. E5 guards the "
        "mark, not the line."
    )


@pytest.mark.parametrize("mark", HYPHEN_CHARS)
def test_a_line_that_opens_no_unit_may_lose_a_trailing_mark(mark: str) -> None:
    """The control: E5 applies to hyphen units, not to every trailing dash.

    A line ending in ``-`` for its own reasons — a dash, a rule, an OCR
    artefact — is not a pair, and editing it away is legitimate.
    """
    canonical = f"word{mark}"
    result = _edit(canonical, HyphenRole.NONE, len(canonical) - 1, len(canonical), "")
    assert result.text_by_id == {"l1": "word"}, (
        f"removing a trailing {mark!r} from a line with no hyphen role was "
        f"rejected — {result.rejected}. E5 is about pairs; applying it to "
        "every line would forbid legitimate edits."
    )
