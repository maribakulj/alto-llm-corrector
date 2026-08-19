"""`F2a` — the slow path keeps three attributes and nothing else.

``docs/promises.md`` graded this row **partial** because only ONE attribute
outside the list was ever read back from the output. One is enough to show a
particular attribute is dropped; it is not enough to show the rule is a
WHITELIST. A blacklist naming that single attribute passes the same test, and
so does a whitelist someone widened by a fourth name.

The difference is not academic. The rule exists because a slow-path rebuild
re-segments the line: the source ``String`` a token came from may have carried
a confidence describing glyphs that are gone, a dialect attribute from a
producer nobody modelled, or an ``xml:lang`` on a word that is now three
words. Carrying any of them over states something about the output that is
not true, and the conservative default —
:func:`~saknussemm.formats.alto.losses.fate_of` — says an attribute nobody
thought about is SEMANTIC and DROPPED for exactly that reason.

So this file asserts the CLOSURE: after a rebuild, the emitted ``String``
carries the whitelist, the recomputed geometry, its new ``CONTENT``, and
nothing else — whatever the source threw at it.

**Sensitivity measured on three mutations of the rewriter.** Widening the
whitelist by a fourth name (``LANG``) fails the closure and the by-name
assertions. Emptying it to ``ID`` alone fails the control — which is the one
that exists because a rewriter dropping *everything* satisfies both halves of
"nothing beyond the whitelist survived". And making identity follow POSITION
instead of the alignment fails the control too, which is right: the styling
would then ride a word it never belonged to.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from lxml import etree

from saknussemm.core.schemas import LineStatus
from saknussemm.formats.alto.parser import parse_alto_file
from saknussemm.formats.alto.rewriter import rewrite_alto_file

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'

#: Attributes a rebuilt String is allowed to carry. Recomputed geometry, the
#: new text, and the §6.1 whitelist — identity and styling, the two things a
#: text change does not invalidate.
_ALLOWED = {"ID", "STYLEREFS", "STYLE", "CONTENT", "HPOS", "VPOS", "WIDTH", "HEIGHT"}

#: What the source String carries beyond that. Real ALTO attributes the
#: rewriter must invalidate (`WC`, `CC`), one the spec defines but this
#: rewriter does not model (`LANG`), and two invented ones standing for a
#: producer dialect — the case `fate_of`'s default exists for.
_INTRUDERS = {
    "WC": "0.87",
    "CC": "000",
    "LANG": "fra",
    "TAGREFS": "TAG_1",
    "VENDORATTR": "something",
}


def _document() -> str:
    extra = " ".join(f'{k}="{v}"' for k, v in _INTRUDERS.items())
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><alto {_NS}><Layout>'
        '<Page ID="P1" WIDTH="1000" HEIGHT="200"><PrintSpace>'
        '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="100">'
        '<TextLine ID="TL1" HPOS="0" VPOS="10" WIDTH="900" HEIGHT="40">'
        f'<String ID="S1" CONTENT="motdorigine" HPOS="0" VPOS="10" WIDTH="300" '
        f'HEIGHT="30" STYLEREFS="TS_1" STYLE="bold" {extra}/>'
        "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
    )


def _rebuilt() -> tuple[list[etree._Element], dict[str, int]]:
    """The Strings of a line pushed through the SLOW path, and its losses.

    One source word becoming two changes the word count, which is what
    routes the line to the rebuild rather than the in-place update — the
    fast path recycles the element untouched and would prove nothing here.
    """
    path = Path(tempfile.mkdtemp()) / "w.xml"
    path.write_bytes(_document().encode("utf-8"))
    pages, _ = parse_alto_file(path, path.name)
    line = pages[0].lines[0]
    line.corrected_text = "mot dorigine"
    line.status = LineStatus.CORRECTED
    result = rewrite_alto_file(path, pages, "test", "mock")

    root = etree.fromstring(result.xml_bytes)
    ns = root.tag.split("}")[0].strip("{")
    strings = list(root.iter(f"{{{ns}}}String"))
    assert len(strings) == 2, f"the line must have gone through the rebuild: {strings}"
    return strings, result.losses


def _names(element: etree._Element) -> set[str]:
    return {etree.QName(k).localname.upper() for k in element.attrib}


def test_no_rebuilt_string_carries_anything_beyond_the_whitelist() -> None:
    """The closure assertion, which one spot check cannot make.

    A blacklist naming a single attribute, or a whitelist widened by a fourth
    name, both survive a test that only asks about ``WC``.
    """
    strings, _ = _rebuilt()
    for rebuilt in strings:
        carried = _names(rebuilt)
        assert carried <= _ALLOWED, (
            f"attributes outside the whitelist survived: {carried - _ALLOWED}"
        )


def test_each_intruder_is_gone_by_name() -> None:
    """Named individually, so a failure says WHICH one leaked.

    A set difference tells you something escaped; it reads badly in a diff six
    months later, and both assertions are cheap.
    """
    strings, _ = _rebuilt()
    for rebuilt in strings:
        for intruder in _INTRUDERS:
            assert intruder not in _names(rebuilt), f"{intruder} survived the rebuild"


def test_what_was_dropped_is_counted() -> None:
    """Dropping is only half the contract; the other half is saying so.

    The conservative default calls an unmodelled attribute SEMANTIC and
    DROPPED precisely so it surfaces in the loss report instead of vanishing
    quietly. A rewriter that dropped the dialect attributes and counted
    nothing would pass every other assertion here.
    """
    _, losses = _rebuilt()
    assert losses.get("lang_dropped") == 1
    assert losses.get("tagrefs_dropped") == 1
    assert losses.get("vendorattr_dropped") == 1, (
        "an unmodelled attribute must be counted, not just removed"
    )
    assert losses.get("confidence_invalidated") == 1


def test_the_whitelist_survives_on_the_string_the_alignment_matched() -> None:
    """The control, and the half that would go unnoticed.

    A rewriter that dropped EVERYTHING passes both assertions above. Identity
    and styling must come through — measured on the real corpus, dropping
    ``STYLE`` destroyed 45 of the 47 styled Strings in ``X0000002.xml``.

    And it must come through on the RIGHT String. One source word becoming two
    leaves one token matched and one inserted; the styling belongs to the word
    the alignment matched, never to whatever sits at the same position. Here
    ``motdorigine`` aligns to ``dorigine``, so ``mot`` is the insertion and
    gets a generated identity — recycling ``S1`` onto it would attach a word's
    identity to text it never carried.
    """
    strings, _ = _rebuilt()
    inserted, matched = strings
    assert matched.get("ID") == "S1"
    assert matched.get("STYLEREFS") == "TS_1"
    assert matched.get("STYLE") == "bold"
    assert inserted.get("ID") and inserted.get("ID") != "S1"
    assert inserted.get("STYLE") is None, "styling must not ride a generated identity"
