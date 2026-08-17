"""The similarity a guard decides on must not depend on a length threshold.

``difflib`` has a heuristic called *autojunk*, on by default: once the second
sequence reaches **200 elements**, any element occurring in more than 1% of it
is treated as junk and can no longer anchor a match. It exists to keep
``SequenceMatcher`` fast when comparing *files* — long sequences of whole
lines, where a repeated line really is noise. Applied to a string, every
element is a character, so in any 200-character stretch of prose the space and
the common letters all become junk.

Measured on 2026-08-17, on a line shaped like a newspaper price column — which
is ordinary ALTO content, not a contrivance:

=========  =========  ==============  ==============  ==========================
length     corrected  ratio's own     what it         verdict
           chars      lower bound     returned
=========  =========  ==============  ==============  ==========================
107        4          0.9626          0.9626          accepted
**215**    **8**      **0.9628**      **0.0837**      **too_different_from_source**
323        12         0.9628          0.0557          too_different_from_source
=========  =========  ==============  ==============  ==========================

The same correction, on the same repeated text, accepted below 200 characters
and refused above it. Nothing about the proposal changed.

**Why the bound is exact rather than a tuned number.** ``ratio()`` is
``2M/T``: matches doubled over total length. Substituting ``k`` characters of
``n`` without changing the length leaves at least ``n - k`` matching, so the
ratio is at least ``1 - k/n``. That inequality is arithmetic, and autojunk
violates it by 0.88.

**Two costs, and the second is the one that lasts.** The refusal throws away a
good correction. But ``source_similarity`` is also *published* on every line
of the report, and it is the natural signal for deciding how strict a run
should be on a given corpus — so a caller calibrating on it is calibrating on
a number that silently collapses past a length threshold they were never told
about. A wrong measurement outlives a wrong decision.

Measured before changing anything: over **27108 pairs** formed from every line
of every real corpus here, under three producers of differing violence,
turning autojunk off changes **zero** ratios and costs **+0.7%** — noise. It
cannot be otherwise: the corpora's longest line is 85 characters, so the
heuristic never engaged on anything this repository had measured. That is
exactly why nothing caught it.

Also settled here, because it is the same three lines of code: guard 3 passes
its operands in the opposite order to guards 1 and 2, and autojunk is the only
thing that ever made ``ratio()`` asymmetric. With it off the argument order
cannot matter, so the inconsistency the audit flagged stops being latent
rather than being tidied away.
"""

from __future__ import annotations

from difflib import SequenceMatcher

import pytest

from saknussemm.core.guards import DEFAULT_GUARD_CONFIG, check_line

#: A row as a price column or a classified-ads block sets it. Repetition is
#: the point: it is what makes ordinary characters "popular" enough to junk.
_ROW = "Aigues-Mortes 12 fr. 50 c. "


def _substituted(text: str) -> tuple[str, int]:
    """``(corrected text, characters changed)`` for one OCR error class.

    ``fr.`` read as ``ff.`` — the long s. Same length, so the arithmetic
    bound below applies without an insertion to account for.
    """
    corrected = text.replace("fr.", "ff.")
    changed = sum(1 for a, b in zip(text, corrected) if a != b)
    return corrected, changed


@pytest.mark.parametrize("repeats", [4, 8, 12, 40])
def test_the_ratio_respects_its_own_arithmetic_bound(repeats: int) -> None:
    """``ratio() >= 1 - k/n`` for ``k`` substitutions in ``n`` characters.

    Not a tuned floor: it follows from ``ratio() == 2M/T``. A measurement
    that breaks arithmetic is not a strict measurement, it is a wrong one.
    """
    source = (_ROW * repeats).strip()
    corrected, changed = _substituted(source)
    assert len(corrected) == len(source), "the case needs a pure substitution"
    assert changed, "nothing was corrected; the parametrisation stopped biting"

    bound = 1 - changed / len(source)
    result = check_line(source, corrected)
    assert result.features is not None
    measured = result.features.source_similarity
    assert measured is not None

    assert measured >= bound - 1e-4, (
        f"a {len(source)}-character line with {changed} character(s) corrected "
        f"scored {measured} where the ratio cannot arithmetically be below "
        f"{bound:.4f}. difflib's autojunk heuristic is treating the common "
        "characters of a *string* as noise, which is what it is for when the "
        "elements are whole lines of a file. source_similarity is published "
        "on every line and is the natural signal for calibrating strictness, "
        "so this is a wrong number before it is a wrong verdict."
    )


def test_the_same_correction_is_not_accepted_short_and_refused_long() -> None:
    """The cliff itself, stated as the thing a reader would not believe.

    Below 200 characters this proposal is accepted; above, refused. Only the
    length of the surrounding text differs, and the guard's contract says
    nothing about length.
    """
    below = (_ROW * 4).strip()
    above = (_ROW * 8).strip()
    assert len(below) < 200 <= len(above), "the fixture no longer straddles 200"

    verdicts = {}
    for label, source in (("short", below), ("long", above)):
        corrected, _ = _substituted(source)
        result = check_line(source, corrected)
        verdicts[label] = (result.accepted, result.reason)

    assert verdicts["short"][0], (
        f"the short case was already refused ({verdicts['short'][1]}), so this "
        "comparison proves nothing. Pick a correction the guards accept."
    )
    assert verdicts["long"][0], (
        f"the identical correction on the same repeated text was accepted at "
        f"{len(below)} characters and refused at {len(above)} with reason "
        f"{verdicts['long'][1]!r}. Crossing 200 characters is not a property of "
        "the proposal."
    )


def test_the_ratio_cannot_depend_on_which_operand_is_first() -> None:
    """Guard 3 passes its operands the other way round to guards 1 and 2.

    ``ratio()`` is symmetric in every respect except autojunk, which applies
    to the second sequence alone. This pins the symmetry rather than the
    calling convention: with the heuristic off, the inconsistency cannot
    reach a verdict, and a future edit that reintroduces it fails here
    instead of being found by reading.
    """
    source = (_ROW * 8).strip()
    corrected, _ = _substituted(source)
    concatenation = source + " " + corrected  # guard 3's long operand
    for a, b in ((source, corrected), (corrected, concatenation)):
        forward = SequenceMatcher(None, a, b).ratio()
        backward = SequenceMatcher(None, b, a).ratio()
        assert forward == backward, (
            f"ratio() is asymmetric on operands of length {len(a)} and "
            f"{len(b)}: {forward} one way, {backward} the other. Guard 1 puts "
            "the correction second and guard 3 puts it first, so an "
            "asymmetric ratio means the two guards measure different things "
            "while reading as though they measure the same one."
        )


def test_the_threshold_the_cliff_would_cross_is_the_configured_one() -> None:
    """Guard the guard: the case above must be refused *for this reason*.

    If ``min_source_similarity`` were ever raised above the bound the
    corrections here clear legitimately, the test above would fail for a
    reason that has nothing to do with autojunk and would be read as a
    regression in this file.
    """
    source = (_ROW * 8).strip()
    _, changed = _substituted(source)
    bound = 1 - changed / len(source)
    assert bound > DEFAULT_GUARD_CONFIG.min_source_similarity, (
        f"the arithmetic bound {bound:.4f} no longer clears "
        f"min_source_similarity={DEFAULT_GUARD_CONFIG.min_source_similarity}. "
        "This fixture's correction must be one the guards accept on the "
        "merits, or the cliff it demonstrates is indistinguishable from "
        "policy."
    )
