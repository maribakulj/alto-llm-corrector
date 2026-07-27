"""A line's break mark is read once, verbatim — never doubled, never swapped.

``reconstruct_textline`` walks a TextLine's String/SP/HYP children and rebuilds
its logical text. Both the parser (building ``ocr_text``) and the rewriter (its
UNTOUCHED comparison) go through it, so whatever it gets wrong, it gets wrong
identically on both sides — and the projection invariant, which compares those
two, is blind to it by construction. That is what made this defect silent: it
altered the text the model saw and the text written back, with no counter and
no error.

**Doubling (L2).** The de-duplication that stops ``String "Ober-"`` + ``HYP
"-"`` from yielding ``Ober--`` tested for the ASCII hyphen alone. Every other
mark in the repertoire doubled: ``Ober⸗⸗``, ``Ober¬¬``. The Fraktur ``⸗`` is
not exotic here — it is 24 of the 94 break marks in ``corpus/37-GT-BNL``.

**Not a defect: the U+00AD collapse.** A ``HYP CONTENT="\\u00ad"`` still reads
back as ``-``, and that is deliberate. A soft hyphen is a hyphen *variant* that
must not reach an ALTO CONTENT attribute (``clean_content`` strips it on the way
out for the same reason); 115 lines of ``examples/X0000002.xml`` carry their
break mark in the ``<HYP>`` alone as U+00AD, and the collapse is what makes them
pair at all. The bytes are unaffected either way — the rewrite paths re-emit the
original HYP element with its own CONTENT. Pinned below so a future pass does
not "fix" it.
"""

from __future__ import annotations

import pytest
from lxml import etree

from corrigenda.formats.alto._text import _DEDUP_MARKS, reconstruct_textline

_NS = "http://www.loc.gov/standards/alto/ns-v3#"


def _textline(children: str) -> etree._Element:
    xml = f'<TextLine xmlns="{_NS}" ID="L1">{children}</TextLine>'
    return etree.fromstring(xml.encode("utf-8"))


def _rebuild(children: str) -> str:
    return reconstruct_textline(_textline(children), _NS)


class TestTheMarkIsNeverDoubled:
    """L2 — the String already carries it; the HYP is the same mark rendered."""

    @pytest.mark.parametrize("mark", _DEDUP_MARKS)
    def test_no_repertoire_mark_doubles(self, mark: str) -> None:
        rebuilt = _rebuild(f'<String CONTENT="Ober{mark}"/><HYP CONTENT="{mark}"/>')
        assert rebuilt == f"Ober{mark}", f"{mark!r} (U+{ord(mark):04X}) doubled"

    def test_the_ascii_case_that_always_worked_still_works(self) -> None:
        assert _rebuild('<String CONTENT="Ober-"/><HYP CONTENT="-"/>') == "Ober-"

    def test_a_hyp_alone_still_contributes_its_mark(self) -> None:
        # Nothing to de-duplicate against: the String does not carry it.
        assert _rebuild('<String CONTENT="Ober"/><HYP CONTENT="⸗"/>') == "Ober⸗"

    def test_a_mark_outside_the_repertoire_is_still_appended(self) -> None:
        # An en dash is not a word-break mark here (see L6); no special case
        # should silently swallow it.
        assert _rebuild('<String CONTENT="Ober"/><HYP CONTENT="–"/>') == "Ober–"


class TestTheSoftHyphenCollapseIsDeliberate:
    """Not a defect — a decision, and one a real corpus depends on."""

    def test_a_soft_hyphen_hyp_reads_back_as_an_ascii_hyphen(self) -> None:
        # The shape 115 lines of examples/X0000002.xml actually have: the
        # mark lives in the HYP alone. Without the collapse they would not
        # end in a break character and would not pair.
        assert _rebuild('<String CONTENT="néces"/><HYP CONTENT="­"/>') == "néces-"

    def test_u00ad_is_not_in_the_de_duplication_set(self) -> None:
        # Admitting it would put a soft hyphen into ocr_text that the
        # round-trip cannot carry.
        assert "­" not in _DEDUP_MARKS
        assert set(_DEDUP_MARKS) == {"-", "¬", "⸗"}

    def test_a_hyp_with_no_content_still_defaults_to_ascii(self) -> None:
        # ALTO allows a bare <HYP/>; there is no source character to
        # preserve, so the conventional "-" is the only honest choice.
        assert _rebuild('<String CONTENT="Ober"/><HYP/>') == "Ober-"


class TestUnrelatedReconstructionIsUnchanged:
    def test_plain_words_and_spaces(self) -> None:
        assert (
            _rebuild('<String CONTENT="Le"/><SP/><String CONTENT="chat"/>') == "Le chat"
        )

    def test_an_empty_line(self) -> None:
        assert _rebuild("") == ""

    def test_a_trailing_mark_with_no_hyp_element(self) -> None:
        # Heuristic PART1: the mark lives in CONTENT and there is no HYP.
        assert _rebuild('<String CONTENT="Ober⸗"/>') == "Ober⸗"
