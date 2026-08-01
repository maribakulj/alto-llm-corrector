"""The projection invariant must SEE a whitespace substitution.

Before this, ``_verify_projection`` compared decided vs extracted through
``" ".join(text.split())``. Two strings differing only by a no-break space
compared equal, so the engine could crush U+00A0 or U+202F into an ordinary
space and leave no counter, no error and no trace — the one corruption class
the invariant exists to catch was the one it could not express.

These tests pin the scale itself. The end-to-end pinning (that a run's report
carries the level) lives in ``test_projection_fidelity_report.py``.
"""

from __future__ import annotations

import pytest

from corrigenda.core.fidelity import (
    FIDELITY_ORDER,
    ProjectionFidelity,
    classify_projection_fidelity,
    weakest,
)

EXACT = ProjectionFidelity.EXACT
SPELLED = ProjectionFidelity.SOURCE_SPELLING
TOKEN = ProjectionFidelity.TOKEN_EQUIVALENT
NORM = ProjectionFidelity.NORMALIZED


class TestExact:
    def test_identical_text_is_exact(self):
        assert classify_projection_fidelity("Le chat", "Le chat") is EXACT

    def test_empty_matches_empty(self):
        assert classify_projection_fidelity("", "") is EXACT

    def test_a_preserved_nbsp_is_exact_not_merely_equivalent(self):
        # The whole point: when the artefact DOES keep the character, the
        # scale must say so rather than shrug at "close enough".
        assert classify_projection_fidelity("M.\xa0Dupont", "M.\xa0Dupont") is EXACT


class TestTokenEquivalent:
    """What the format costs on every line, and never more than that."""

    def test_collapsed_run_of_ordinary_spaces(self):
        # <SP> is one element; a doubled space cannot round-trip. Not a
        # substitution — nothing a reader would notice.
        assert classify_projection_fidelity("Le  chat", "Le chat") is TOKEN

    def test_trailing_edge_whitespace_dropped(self):
        # rewriter.py strips edges deliberately: an edge SP token would land
        # the trailing HYP on top of the SP's HPOS range.
        assert classify_projection_fidelity("Le chat ", "Le chat") is TOKEN

    def test_leading_edge_whitespace_dropped(self):
        assert classify_projection_fidelity("  Le chat", "Le chat") is TOKEN

    def test_an_all_whitespace_line_trimmed_to_empty(self):
        assert classify_projection_fidelity("   ", "") is TOKEN

    def test_an_edge_nbsp_is_not_a_substitution(self):
        # It was dropped, not swapped: the format has nowhere to put it, and
        # a no-break space at a line edge binds nothing to anything.
        assert classify_projection_fidelity("\xa0Le chat", "Le chat") is TOKEN


class TestNormalized:
    """The defect this scale was built to make visible."""

    def test_nbsp_becomes_an_ordinary_space(self):
        assert classify_projection_fidelity("M.\xa0Dupont", "M. Dupont") is NORM

    def test_narrow_nbsp_becomes_an_ordinary_space(self):
        # U+202F: French typography before % ; ! ? : — the most frequent
        # significant space in the corpus this library targets, and the one
        # named in no earlier finding.
        assert classify_projection_fidelity("12 %", "12 %") is NORM

    def test_tab_becomes_an_ordinary_space(self):
        assert classify_projection_fidelity("a\tb", "a b") is NORM

    def test_substitution_in_the_other_direction_still_counts(self):
        assert classify_projection_fidelity("a b", "a\xa0b") is NORM

    def test_one_degraded_gap_among_many_intact_ones_wins(self):
        decided = "a b c d\xa0e"
        assert classify_projection_fidelity(decided, "a b c d e") is NORM

    def test_a_collapsed_run_that_also_loses_a_character(self):
        # "\xa0 " -> " ": the run collapsed AND the no-break space is gone.
        assert classify_projection_fidelity("a\xa0 b", "a b") is NORM


class TestDivergence:
    """No level at all — the artefact does not say what was decided."""

    @pytest.mark.parametrize(
        ("decided", "extracted"),
        [
            ("Le chat", "Le chien"),
            ("Le chat", "Le chat noir"),
            ("Le chat", ""),
            ("", "Le chat"),
            ("Le chat", "Lechat"),  # a lost space is a lost WORD boundary
        ],
    )
    def test_word_divergence_has_no_fidelity_level(self, decided, extracted):
        assert classify_projection_fidelity(decided, extracted) is None


class TestWeakest:
    def test_worst_level_wins(self):
        assert weakest([EXACT, TOKEN, NORM]) is NORM
        assert weakest([EXACT, TOKEN]) is TOKEN
        assert weakest([EXACT]) is EXACT

    def test_one_normalized_line_sinks_a_clean_run(self):
        # A run is only as faithful as its least faithful line; an average
        # would hide exactly the line worth looking at.
        assert weakest([EXACT] * 999 + [NORM]) is NORM

    def test_empty_and_all_none_yield_none(self):
        assert weakest([]) is None
        assert weakest([None, None]) is None

    def test_none_entries_are_ignored_not_counted_as_worst(self):
        assert weakest([EXACT, None]) is EXACT


def test_the_order_is_best_to_worst():
    assert FIDELITY_ORDER == (EXACT, SPELLED, TOKEN, NORM)


def test_levels_serialize_as_their_string_value():
    # The report is JSON; a consumer dispatches on these strings.
    assert [level.value for level in FIDELITY_ORDER] == [
        "exact",
        "source_spelling",
        "token_equivalent",
        "normalized",
    ]


class TestSourceSpelling:
    """L8 — a substitution on a character that is not whitespace.

    ``EXACT`` claims the artefact says the decision *character for
    character*. On 115 lines of the repo's own BnF fixture that was false
    and unprovable at the same time: the file spells its break mark U+00AD,
    the reconstruction reads it back as ``-``, and the invariant compared
    two strings that had both been through that collapse. Feeding it the
    verbatim reading is what makes the difference expressible at all.
    """

    def test_a_mark_the_file_spells_its_own_way_is_not_exact(self):
        # decided/extracted agree (both collapsed); the file says U+00AD.
        assert classify_projection_fidelity("tra-", "tra-", "tra\xad") is SPELLED

    def test_no_verbatim_reading_means_no_claim_either_way(self):
        # A format that substitutes nothing passes None and keeps EXACT —
        # the level must not degrade just because the argument is absent.
        assert classify_projection_fidelity("tra-", "tra-") is EXACT
        assert classify_projection_fidelity("tra-", "tra-", "tra-") is EXACT

    def test_it_is_better_than_a_collapsed_space_and_worse_than_exact(self):
        # The ordering claim, as an assertion: a source-spelled mark loses
        # NOTHING from the file, a collapsed whitespace run does.
        assert weakest([EXACT, SPELLED]) is SPELLED
        assert weakest([SPELLED, TOKEN]) is TOKEN

    def test_a_line_can_be_both_source_spelled_and_lossy(self):
        # Two independent defects on one line: a doubled space the format
        # cannot store AND a source-spelled mark. The run must hear the
        # worse of the two, not whichever was tested first.
        assert classify_projection_fidelity("a  b-", "a b-", "a b\xad") is TOKEN
        assert classify_projection_fidelity("a\xa0b-", "a b-", "a b\xad") is NORM

    def test_divergent_words_are_still_corruption_not_a_spelling(self):
        # The floor must never rescue a line whose words moved.
        assert classify_projection_fidelity("chat", "chien", "chien") is None
