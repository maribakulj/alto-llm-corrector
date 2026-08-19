"""Page-aligned mode's whole risk, stated as the thing it must never do.

Asking for a page in one call is 28 requests instead of ~2 000 and `$0.14`
instead of `$1.11`. The answer comes back as a list of lines carrying no
identities, and something has to say which returned line is which. Getting
that wrong writes a line's text onto a different line — worse than not
correcting at all, because the file then says something the scan does not, on
a line nobody flagged.

These tests are that guarantee. The measurements in them were taken on the
real Gallica corpus before `core/page_alignment.py` was written; the module
was shaped by them rather than the reverse.
"""

from __future__ import annotations

import pytest

from saknussemm.core.page_alignment import align_page_lines, line_similarity


def test_an_ordinary_correction_lands_on_its_own_line() -> None:
    """The base case, and the one that must never regress."""
    source = ["le chat dort", "sur le tapis rouge", "et il ronfle fort"]
    returned = ["le chat dort", "sur le tapis rouge", "et il ronfle fort"]
    assert align_page_lines(source, returned).matched == (0, 1, 2)


def test_a_line_the_model_corrected_still_matches_itself() -> None:
    """Jaccard over tokens: a fixed word costs one token out of several.

    `Frauce` → `France` changes one token in six, which leaves the line far
    closer to itself than to either neighbour — the property the whole
    mapping rests on, measured at 0.747 average margin on real lines.
    """
    source = ["le roi de Frauce est mort", "vive le roi nouveau"]
    returned = ["le roi de France est mort", "vive le roi nouveau"]
    assert align_page_lines(source, returned).matched == (0, 1)


def test_neither_half_of_a_merge_is_matched() -> None:
    """The failure page mode exists to guard against, and the near-miss.

    A model that folds two source lines into one returns fewer lines than it
    was given. Leaving the SWALLOWED line unmatched is not enough — that
    happens on its own, and the first version of this module stopped there.
    The line that DID match then received the merged text, so one physical
    line got its neighbour's words. That is exactly the corruption the mode
    may never produce, and it hid behind a passing test.

    Both lines are refused now, because the merged line looks like neither.
    Measured on eight real pages: the merged line was matched on 6 of 6
    before the gate and 0 of 6 after, with all 8 859 ordinary matches intact.
    """
    source = ["premier vers ici", "deuxieme vers la", "troisieme vers bas"]
    returned = ["premier vers ici deuxieme vers la", "troisieme vers bas"]
    alignment = align_page_lines(source, returned)
    assert alignment.unmatched == (0, 1), alignment.matched
    assert alignment.matched[2] == 1, "the lines after the merge must not shift"
    assert alignment.unclaimed == (0,), "the merged line belongs to nobody"


def test_a_correction_that_adds_or_drops_a_word_still_matches() -> None:
    """The other half of the gate: it must not unmatch ordinary lines.

    Measured on 8 859 matched pairs from eight real pages, a correction moves
    a line's token count by -1, 0 or +1 — 100% of the time, +0 alone being
    94%. A gate tighter than that would refuse real corrections by the
    thousand; this one leaves every single one of those 8 859 matched.
    """
    source = ["le roi de Frauce est mort", "vive le roi nouveau"]
    added = ["le roi de France est bien mort", "vive le roi nouveau"]
    dropped = ["le roi de France mort", "vive le roi nouveau"]
    assert align_page_lines(source, added).matched == (0, 1)
    assert align_page_lines(source, dropped).matched == (0, 1)


def test_a_line_split_in_two_claims_neither_half() -> None:
    """The mirror of a merge, and it must not invent a line for the surplus.

    Lines never split: a returned half has no physical line to live on, and
    promoting one would change the document's line structure — the thing the
    hyphen machinery, the reconciler and the rewriter all exist to protect.

    Matching ONE half would be the subtler failure: the source line would
    then be rewritten with half its own text, silently losing the rest. Both
    halves fall outside the token-count gate, so neither is claimed and the
    source line keeps its OCR.
    """
    source = ["un vers entier avec beaucoup de mots dedans", "et le suivant"]
    returned = ["un vers entier", "avec beaucoup de mots dedans", "et le suivant"]
    alignment = align_page_lines(source, returned)
    assert alignment.matched[0] is None, "half a line is not the line"
    assert alignment.unclaimed == (0, 1), alignment
    assert alignment.matched[1] == 2, "the line after the split must still match"


def test_a_line_sharing_no_token_is_left_unmatched_not_guessed() -> None:
    """ "Identity must never ride a zero-evidence match" — at page scale.

    On the worst real page, 17 of 1 035 lines came back unmatched this way,
    and **zero** were paired with the wrong line. The two facts are the same
    fact: refusing the evidence-free match is what makes the mis-pairing rate
    zero, and unmatched lines are the price. They are also free — an
    unmatched line keeps its OCR text.
    """
    source = ["alpha bravo charlie", "delta echo foxtrot"]
    returned = ["alpha bravo charlie", "zoulou yankee xray"]
    alignment = align_page_lines(source, returned)
    assert alignment.matched[0] == 0
    assert alignment.matched[1] is None


def test_the_mapping_never_crosses() -> None:
    """Monotonic by construction: a page cannot come back reordered.

    Even handed a reversal, the alignment may only leave lines unmatched — it
    can never report that line 3 answers line 1, because reordering a
    document's lines is not something this library is allowed to do.
    """
    source = [f"ligne numero {i} avec du texte" for i in range(12)]
    alignment = align_page_lines(source, list(reversed(source)))
    settled = [t for t in alignment.matched if t is not None]
    assert settled == sorted(settled), alignment.matched


def test_an_excursion_beyond_the_corridor_is_reported() -> None:
    """A band keeps a page affordable; it must also say when it was too narrow.

    Refuse the page on this. Widening the band until the flag goes quiet
    turns a guard into a formality.
    """
    head = [f"alpha{i} beta{i} gamma{i}" for i in range(30)]
    tail = [f"omega{i} psi{i} chi{i}" for i in range(30)]
    assert align_page_lines(head + tail, tail + head, band=3).band_exhausted is True


def test_an_empty_page_is_not_a_special_case() -> None:
    alignment = align_page_lines([], [])
    assert alignment.matched == ()
    assert alignment.unclaimed == ()
    assert alignment.band_exhausted is False


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("", "", 1.0),
        ("mot", "", 0.0),
        ("a b", "a b", 1.0),
        ("a b", "a c", pytest.approx(1 / 3)),
        # Jaccard alone would score this 0.5 and win the match — the exact
        # shape of a merged line, and why the gate is inside the similarity.
        ("a b c", "a b c d e f", 0.0),
    ],
)
def test_line_similarity_edges(left: str, right: str, expected: float) -> None:
    """Two empty lines ARE the same line; one empty against text is not.

    Returning 0.0 for the empty/empty pair would leave every blank line in a
    page unmatched, and a newspaper page has many.
    """
    assert line_similarity(left, right) == expected
