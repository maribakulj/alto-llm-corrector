"""What made the pair site safe to translate (`RM-01`, site 7/7).

``reconcile._reconcile_one_pair`` wrote four decision fields at once —
both members of a pair, text and status — with a status computed from a
classification and a text computed by the reconciler. Turning that into
``decide.accept`` / ``decide.fall_back`` rests on a coincidence that is
not a coincidence:

    **``classify_reconcile_outcome`` returns ``"fallback"`` only when
    ``final_part1 == part1_ocr`` AND ``final_part2 == part2_ocr``.**

The classifier does not observe a fallback and report it; it *defines*
one as "the reconciler put both sides back". So on the branch where the
status becomes ``FALLBACK``, the text the site used to write
(``final_p1``) and the text ``decide.fall_back`` writes (``ocr_text``)
are the same string by construction, not by luck.

That guarantee is worth a test because it is invisible at the call site.
A future edit that made the classifier report ``"fallback"`` on a partial
revert — one side back, one side kept — would leave the code reading
exactly as it does now while ``fall_back`` quietly discarded a
correction the reconciler had chosen to keep.

Two things this file deliberately does NOT touch, because they are `S1`
territory and the freeze in ``docs/PLAN.md`` says so: how a partner is
resolved, and the ``hyphen_subs_content`` the pair agrees on. `RM-01`
migrated the decision WRITE at this site and nothing else.
"""

from __future__ import annotations

import pytest

from saknussemm.core.hyphenation import classify_reconcile_outcome

_P1_OCR = "par-"
_P2_OCR = "tir"


@pytest.mark.parametrize(
    ("corrected1", "corrected2", "final1", "final2"),
    [
        # both reverted, something had been proposed → fallback
        ("PAR-", "TIR", _P1_OCR, _P2_OCR),
        ("par-", "TIR", _P1_OCR, _P2_OCR),
        ("PAR-", "tir", _P1_OCR, _P2_OCR),
    ],
)
def test_fallback_is_only_ever_both_sides_back_at_source(
    corrected1: str, corrected2: str, final1: str, final2: str
) -> None:
    outcome = classify_reconcile_outcome(
        _P1_OCR, _P2_OCR, corrected1, corrected2, final1, final2, None
    )
    assert outcome == "fallback"
    assert (final1, final2) == (_P1_OCR, _P2_OCR)


@pytest.mark.parametrize(
    ("final1", "final2"),
    [
        ("PAR-", "TIR"),  # neither reverted
        (_P1_OCR, "TIR"),  # only part1 reverted — a partial
        ("PAR-", _P2_OCR),  # only part2 reverted — a partial
    ],
)
def test_a_partial_revert_is_never_classified_fallback(
    final1: str, final2: str
) -> None:
    """The half that matters: if either side kept its correction, the
    outcome is NOT "fallback", so ``decide.fall_back`` is never reached
    with a text it would have to discard."""
    outcome = classify_reconcile_outcome(
        _P1_OCR, _P2_OCR, "PAR-", "TIR", final1, final2, None
    )
    assert outcome != "fallback"


def test_an_identity_pair_is_not_a_fallback() -> None:
    """Nothing was proposed, so nothing was thrown away — the pair is
    coherent or neutralised, and ``decide.accept`` is the right verb."""
    outcome = classify_reconcile_outcome(
        _P1_OCR, _P2_OCR, _P1_OCR, _P2_OCR, _P1_OCR, _P2_OCR, None
    )
    assert outcome == "neutralised"


def test_the_translation_is_exhaustive_over_the_three_outcomes() -> None:
    """``_reconcile_one_pair`` branches on ``outcome == "fallback"`` and
    sends everything else to ``accept``. That is only complete while the
    classifier's vocabulary stays three words, all of which are either a
    fallback or an acceptance."""
    produced = {
        classify_reconcile_outcome(_P1_OCR, _P2_OCR, c1, c2, f1, f2, subs)
        for c1 in (_P1_OCR, "PAR-")
        for c2 in (_P2_OCR, "TIR")
        for f1 in (_P1_OCR, "PAR-")
        for f2 in (_P2_OCR, "TIR")
        for subs in (None, "partir")
    }
    assert produced <= {"fallback", "coherent", "neutralised"}, (
        f"classify_reconcile_outcome grew a fourth outcome: {produced}. "
        "_reconcile_one_pair treats everything that is not 'fallback' as an "
        "acceptance — a new outcome needs a decision, not a default."
    )
