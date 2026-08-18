"""An invisible character the writer declares it removes is not corruption.

Found by a real Mistral run over 15 Gallica newspaper pages on 2026-08-17:
**two pages produced no output at all**, killed by ``ProjectionError``.

    rewritten XML for 'alto.xml' diverges from the run's decision on line
    'PAG_3_TL000027': decided "si authen\\xadticité que l'intuition assure
    plus" but the artefact contains "si authenticité que l'intuition assure
    plus"

Nothing was corrupted. ``clean_content`` strips U+00AD on write **on
purpose**, and says so where it does it: *"emitted by some OCR engines as a
hyphen variant; the hyphenation reconciler reconstructs it from manifest
state, so the raw CONTENT must not carry it."* The model returned a soft
hyphen inside a word, the writer removed it as designed — and then the
projection classifier failed the page.

**The gap was in the scale, not in the writer.**
``classify_projection_fidelity`` grades whitespace differences and nothing
else: same words → a level, different words → ``None``, and ``None`` means
"a corrupted deliverable" which the caller must raise on. A soft hyphen sits
*inside* a token, so ``split()`` sees two different words and the page dies.

The scale already has the right name for this: ``NORMALIZED`` means a
character is gone from the file. A declared, bounded, documented removal is
exactly that. The difference between grading it and refusing it is a page
delivered or a page lost, and two of fifteen were lost.

**What this deliberately does NOT rescue**, because the same run produced it
and it is genuine corruption:

    decided 'à la révision des jugements et d -' but the artefact contains
    'à la révision des jugements et d-'

There the writer welded a word to the break mark — the file says something
the run did not decide, and refusing it is correct. That page's failure is a
separate defect, and this fix leaves it failing.
"""

from __future__ import annotations

import pytest

from saknussemm.core._norm import clean_content, strip_invisibles
from saknussemm.core.fidelity import ProjectionFidelity, classify_projection_fidelity

#: The exact pair from the failing page, kept verbatim rather than reduced:
#: a reduced fixture would not prove the real one is covered.
_DECIDED = "si authen­ticité que l'intuition assure plus"
_DELIVERED = "si authenticité que l'intuition assure plus"


def test_the_real_page_that_died_now_grades_instead() -> None:
    assert classify_projection_fidelity(_DECIDED, _DELIVERED) is (
        ProjectionFidelity.NORMALIZED
    ), (
        "a soft hyphen inside a word still fails the page. The writer removes "
        "U+00AD by design and says so; a declared removal is a level of this "
        "scale, and `None` here costs the whole document."
    )


@pytest.mark.parametrize(
    ("name", "decided"),
    [
        ("soft hyphen", "un mot cou­pé ici"),
        ("zero width space", "un mot cou​pé ici"),
        ("zero width non-joiner", "un mot cou‌pé ici"),
        ("zero width joiner", "un mot cou‍pé ici"),
        ("byte order mark", "un mot cou﻿pé ici"),
    ],
)
def test_every_invisible_the_writer_strips_is_graded(name: str, decided: str) -> None:
    """The whole declared set, not just the one that happened to surface.

    ``clean_content`` removes five invisible characters. Rescuing only the
    soft hyphen would leave four ways for a page to die for the same reason,
    and the next one would be found the same expensive way.
    """
    delivered = clean_content(decided)
    assert delivered != decided, f"{name}: the fixture no longer exercises removal"
    assert classify_projection_fidelity(decided, delivered) is (
        ProjectionFidelity.NORMALIZED
    ), f"{name} still fails the page"


def test_a_welded_word_is_still_refused() -> None:
    """The other page from the same run, and it must keep failing.

    ``'et d -'`` delivered as ``'et d-'`` is the writer joining a word to the
    break mark: the file says something the run did not decide. That is what
    ``None`` is for, and widening the rescue to cover it would turn this fix
    into a hole in the projection invariant.
    """
    assert classify_projection_fidelity("et d -", "et d-") is None


@pytest.mark.parametrize(
    ("decided", "delivered"),
    [
        ("chat noir", "chien noir"),
        ("trois mots ici", "trois mots"),
        ("abc", "abd"),
        # An invisible removed AND a word changed: the invisible must not
        # launder the word.
        ("un mot cou­pé ici", "un mot coupé là"),
    ],
)
def test_a_real_text_change_is_never_laundered(decided: str, delivered: str) -> None:
    """The rescue compares against the removal alone, deliberately.

    Running the full ``clean_content`` here instead would let NFC folding and
    control stripping hide a genuine divergence behind a normalisation, which
    is why ``strip_invisibles`` exists as its own step.
    """
    assert classify_projection_fidelity(decided, delivered) is None


def test_the_rescue_is_exactly_the_writers_own_removal() -> None:
    """Guard the seam: the classifier and the writer must not drift apart.

    If ``clean_content`` learns to strip a sixth character and
    ``strip_invisibles`` does not, a page starts dying again for a reason
    nobody changed on purpose.
    """
    sample = "a­b​c‌d‍e﻿f\ng\rh\ti"
    assert strip_invisibles(sample) == clean_content(sample), (
        "clean_content removes something strip_invisibles does not (or NFC "
        "moved). The projection rescue is defined as 'exactly what the writer "
        "declares it removes', so the two must stay the same set."
    )


def test_the_untouched_levels_did_not_move() -> None:
    """The scale's other verdicts are unchanged — this widens one branch only."""
    assert classify_projection_fidelity("abc def", "abc def") is (
        ProjectionFidelity.EXACT
    )
    assert classify_projection_fidelity("a  b", "a b") is (
        ProjectionFidelity.TOKEN_EQUIVALENT
    )
