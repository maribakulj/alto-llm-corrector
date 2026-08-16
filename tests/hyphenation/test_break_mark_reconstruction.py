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
mark in the repertoire doubled: ``Ober⸗⸗``, ``Ober¬¬``. No document in either
corpus carries a mark in both places, so this pins a latent path rather than a
measured one — which is exactly why it needs a test: nothing else would catch
a regression.

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

from saknussemm.formats.alto._text import _DEDUP_MARKS, reconstruct_textline

from tests._pipeline_harness import EXAMPLES

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

    def test_u00ad_is_the_only_mark_outside_the_de_duplication_set(self) -> None:
        # The property, not a frozen list: the de-dup set is the break-mark
        # repertoire minus U+00AD, so widening the repertoire (L6) widens
        # this too and only the soft hyphen stays out. Admitting it would
        # put a soft hyphen into ocr_text that the round-trip cannot carry.
        from saknussemm.core.pairing import HYPHEN_CHARS

        assert "­" not in _DEDUP_MARKS
        assert set(_DEDUP_MARKS) == set(HYPHEN_CHARS) - {"­"}

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


# ---------------------------------------------------------------------------
# Mixed-role lines: backward explicit, forward heuristic, on ONE line
# ---------------------------------------------------------------------------


class TestAMixedRoleLineKeepsItsForwardMark:
    """``PAG_00000002_TL000454`` of the real BnF fixture is BOTH: it opens
    with an explicit ``SUBS_TYPE="HypPart2"`` and ends on a bare heuristic
    dash with no ``<HYP>``.

    The writer decided whether to strip that trailing mark from the String
    by reading ``hyphen_source_explicit`` — which describes the BACKWARD
    link. It answered "explicit", so the dash was dropped on the assumption
    a ``<HYP>`` would render it. There is none: the mark vanished from the
    delivered file. Found by the status-truthfulness invariant
    (``test_status_truthfulness.py``), not by reading.
    """

    def test_the_two_explicitness_flags_can_disagree(self) -> None:
        from saknussemm.core.pairing import forward_break_is_explicit
        from saknussemm.core.schemas import HyphenRole
        from saknussemm.formats.alto.parser import parse_alto_file

        path = EXAMPLES / "X0000002.xml"
        pages, _ = parse_alto_file(path, path.name)
        line = next(
            lm
            for page in pages
            for lm in page.lines
            if lm.line_id == "PAG_00000002_TL000454"
        )
        assert line.hyphen_role is HyphenRole.BOTH
        assert line.hyphen_source_explicit is True  # the backward link
        assert line.hyphen_forward_explicit is False  # the forward break
        # The role→slot map must read the forward one.
        assert forward_break_is_explicit(line) is False

    def test_the_forward_mark_survives_the_rewrite(self) -> None:
        from saknussemm.core.schemas import LineStatus
        from saknussemm.formats.alto.parser import parse_alto_file
        from saknussemm.formats.alto.rewriter import rewrite_alto_file

        path = EXAMPLES / "X0000002.xml"
        pages, _ = parse_alto_file(path, path.name)
        target = "PAG_00000002_TL000454"
        for page in pages:
            for lm in page.lines:
                # Uppercase the first word: a real change, so the line takes
                # a write path rather than UNTOUCHED, with the word count
                # and the trailing mark both preserved.
                head, sep, rest = lm.ocr_text.partition(" ")
                lm.corrected_text = head.upper() + sep + rest
                lm.status = LineStatus.CORRECTED

        result = rewrite_alto_file(path, pages, "test", "mock")
        assert result.texts[target].endswith("-"), (
            f"the forward break mark was dropped: {result.texts[target]!r}"
        )


class TestTheRepertoireIsJustifiedByEvidence:
    """L6 — widening the repertoire makes lines pair that did not, on real
    documents, so each member is there on measurement rather than on the
    grounds that it looks like a hyphen."""

    def test_the_unambiguous_unicode_hyphens_pair(self) -> None:
        from saknussemm.core.pairing import HYPHEN_CHARS, trailing_hyphen_char

        for mark in ("‐", "‑"):  # U+2010 HYPHEN, U+2011 NON-BREAKING HYPHEN
            assert trailing_hyphen_char(f"administra{mark}", HYPHEN_CHARS) == mark

    def test_the_ambiguous_marks_stay_out(self) -> None:
        # `=` is an equals sign; U+2013 is a dialogue dash or a range. Both
        # appear ZERO times in the 40 corpus files, so there is no evidence
        # they are needed and a known reason they would misfire.
        from saknussemm.core.pairing import HYPHEN_CHARS

        assert "=" not in HYPHEN_CHARS
        assert "–" not in HYPHEN_CHARS

    def test_a_year_range_still_does_not_pair(self) -> None:
        # The alphabetic-char requirement is what keeps the repertoire safe
        # to widen at all.
        from saknussemm.core.pairing import HYPHEN_CHARS, trailing_hyphen_char

        assert trailing_hyphen_char("en 1789-", HYPHEN_CHARS) is None
        assert trailing_hyphen_char("n°5‐", HYPHEN_CHARS) is None
