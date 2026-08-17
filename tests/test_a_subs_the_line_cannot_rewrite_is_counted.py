"""An attribute the rewrite destroys must be counted, whatever its name.

`R*` asks for one thing: every alteration is declared and counted. The
loss matrix classifies ``SUBS_TYPE`` and ``SUBS_CONTENT`` as **REWRITTEN**,
on the strength of a measurement written beside them — *"``_apply_subs``
runs on all three write paths and writes both from the line's own hyphen
state. Measured: 234 in, 234 out."*

That measurement was true and the conclusion did not follow. ALTO's
``SUBS_TYPE`` has **three** values, and the third — ``Abbreviation``, a word
that is a short form of another — has nothing to do with hyphenation. No
hyphen state can express it, so ``_apply_subs`` cannot write it back.

Measured on 2026-08-17, with a single
``<String CONTENT="Dr" SUBS_TYPE="Abbreviation" SUBS_CONTENT="Docteur"/>``:

============  ========  =========
path          survives  losses
============  ========  =========
identity      yes       —
fast          yes       —
**slow**      **no**    **None**
============  ========  =========

An attribute gone from the file and a report saying nothing — the `R*`
promise inverted, and classified ``REWRITTEN`` so no counter would ever
look.

**The rule keys on the value against what the line wants**, not on the
attribute's name and not on a guess about the rebuilt shape. That closes a
second case the first attempt missed: a ``HypPart1`` the line's role does
not reproduce — a misplaced one, or a heuristic pair with no SUBS content —
was equally destroyed and equally uncounted. Both are the same question:
*will this line write this value back?*

Two earlier attempts are worth recording, because both were the phantom
this file's sibling exists to catch. Counting *source occurrences minus
one* under-subtracted on a ``BOTH`` line, where ``_apply_subs`` writes
**two** — backward and forward — and reported a loss on a file that kept
every one. Predicting from the hyphen role alone had the same defect from
the other side.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from saknussemm.core.schemas import LineStatus
from saknussemm.formats.alto.parser import parse_alto_file
from saknussemm.formats.alto.rewriter import rewrite_alto_file


def _rewrite(first_attrs: str, second_attrs: str = "") -> tuple[str, dict[str, int]]:
    """``(hyphen role, losses)`` after a slow-path rewrite of a two-word line."""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>'
        '<Page ID="P1" WIDTH="1000" HEIGHT="200"><PrintSpace>'
        '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="100">'
        '<TextLine ID="TL1" HPOS="0" VPOS="10" WIDTH="900" HEIGHT="40">'
        f'<String ID="S1" CONTENT="Dr" HPOS="0" VPOS="10" WIDTH="200" '
        f'HEIGHT="40" {first_attrs}/>'
        '<SP WIDTH="20" HPOS="200" VPOS="10"/>'
        f'<String ID="S2" CONTENT="Fauft" HPOS="220" VPOS="10" WIDTH="300" '
        f'HEIGHT="40" {second_attrs}/>'
        "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
    )
    path = Path(tempfile.mkdtemp()) / "subs.xml"
    path.write_text(document, encoding="utf-8")
    pages, _ = parse_alto_file(path, path.name)
    role = pages[0].lines[0].hyphen_role.value
    for page in pages:
        for line in page.lines:
            # One more word: the slow path, the only one that rebuilds the
            # Strings and therefore the only one that can lose their SUBS.
            line.corrected_text = line.ocr_text + " encore"
            line.status = LineStatus.CORRECTED
    result = rewrite_alto_file(path, pages, "test", "mock")
    return role, result.losses_by_line.get("TL1") or {}


def test_an_abbreviation_is_counted_when_the_rebuild_drops_it() -> None:
    role, losses = _rewrite('SUBS_TYPE="Abbreviation" SUBS_CONTENT="Docteur"')
    assert role == "none", (
        f"the line parsed as {role!r}; this case needs a line whose hyphen "
        "state has nothing to say about the SUBS it carries."
    )
    assert losses == {"subs_type_dropped": 1, "subs_content_dropped": 1}, (
        f"the rewrite destroyed an Abbreviation and reported {losses}. The "
        "loss matrix calls SUBS_* REWRITTEN because `_apply_subs` re-writes "
        "it from the hyphen state — which cannot express an abbreviation, so "
        "nothing writes it back and no counter was looking."
    )


def test_a_hyphen_subs_the_line_does_not_reproduce_is_counted_too() -> None:
    """The second case, which keying on the attribute NAME would miss.

    A ``HypPart1`` on a String that is not the line's break point leaves the
    line parsed as ``none``, so nothing writes it back either. Its value is
    a hyphenation value, and that is not the question — the question is
    whether *this line* will write it.
    """
    role, losses = _rewrite('SUBS_TYPE="HypPart1" SUBS_CONTENT="X"')
    assert role == "none"
    assert losses == {"subs_type_dropped": 1, "subs_content_dropped": 1}, (
        f"a HypPart1 the line does not reproduce was dropped and reported "
        f"{losses}. Keying on the value alone would have called this "
        "re-established and counted nothing."
    )


def test_a_subs_the_line_does_reproduce_is_not_counted() -> None:
    """The phantom side, and the reason two earlier attempts were wrong.

    A properly placed ``HypPart1`` **is** re-written from the hyphen state.
    Counting it would report a loss on a file that kept every one of them —
    which is precisely what ``test_no_phantom_losses`` caught when this rule
    was "source occurrences minus one": on a ``BOTH`` line ``_apply_subs``
    writes two, not one.
    """
    role, losses = _rewrite("", 'SUBS_TYPE="HypPart1" SUBS_CONTENT="Fauftencore"')
    assert role == "HypPart1", f"expected the line to parse as PART1, got {role!r}"
    assert losses == {}, (
        f"a SUBS the line re-establishes was reported as lost — {losses}. A "
        "phantom loss is as dishonest as an uncounted one, and cheaper to "
        "introduce."
    )


@pytest.mark.parametrize(
    "name", ["X0000002.xml", "bnf-alto-prod-bpt6k5406037v-f40.xml"]
)
def test_the_real_corpora_report_no_subs_loss(name: str) -> None:
    """The corpus check, because the rule must not fire on real files.

    Every ``SUBS_TYPE`` in ``examples/`` and in the pinned Gallica pages is
    ``HypPart1`` or ``HypPart2`` — 115 of each in ``X0000002.xml`` alone —
    and all of them are re-established. A rule that counted them would turn
    a real corpus into a report full of phantom losses.
    """
    from tests._paths import EXAMPLES

    path = EXAMPLES / name
    pages, _ = parse_alto_file(path, path.name)
    for page in pages:
        for line in page.lines:
            line.corrected_text = line.ocr_text + " encore"
            line.status = LineStatus.CORRECTED
    result = rewrite_alto_file(path, pages, "test", "mock")
    phantom = {
        line_id: losses
        for line_id, losses in result.losses_by_line.items()
        if any(key.startswith("subs_") for key in losses)
    }
    assert not phantom, (
        f"{name} reports SUBS losses on {len(phantom)} line(s): "
        f"{list(phantom.items())[:3]}. Every SUBS in this corpus is a "
        "hyphenation one the rewrite re-establishes."
    )
