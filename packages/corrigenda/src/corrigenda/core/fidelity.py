"""How faithfully the rewritten artefact carries the run's decision.

The projection invariant compares the decided text against the text
re-extracted from the rewritten XML. It used to do so in whitespace normal
form — ``" ".join(text.split())`` — which made it blind to a whitespace
SUBSTITUTION: a line decided as ``"M.\\xa0Dupont"`` and written back as
``"M. Dupont"`` compared equal, so the non-breaking space died with no
counter, no error and no trace. That is the one class of corruption the
invariant exists to catch, and it was the one class it could not see.

The answer is not a stricter invariant. ``EXACT`` is **unreachable in
ALTO**: ``<SP>`` carries no content, so a doubled space, a tab and a
no-break space are the same element once written, and whitespace at a line
edge has no representation at all. The engine was always going to lose some
of this. What was missing is that it picked a fidelity level implicitly and
never said which one.

So the level becomes a value. Three of them, ordered, each meaning something
a reader can act on:

``EXACT``
    The artefact says the decision, character for character.

``TOKEN_EQUIVALENT``
    Same words, and every whitespace character that mattered survived; only
    runs collapsed or edges were trimmed. This is what the format costs and
    it costs it on every line — a doubled space cannot round-trip through
    ``<SP>``. Nothing a reader of the text would notice.

``NORMALIZED``
    Same words, but a whitespace character was **replaced by a different
    one** — a no-break space, a narrow no-break space or a tab became an
    ordinary space. The line still reads the same to a machine that splits
    on whitespace, and no longer reads the same to a typographer: French
    typography puts U+202F before ``%``, ``;``, ``!``, ``?`` and ``:``, and
    a no-break space is the difference between ``M. Dupont`` on one line and
    ``M.`` orphaned at the end of another.

Below the scale there is no level: if the WORDS differ, the artefact does
not say what the run decided, and that is corruption rather than a fidelity
grade. :func:`classify_projection_fidelity` returns ``None`` and the caller
fails the run, exactly as before.

Pure: no lxml, no format import, nothing from the rest of the package.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import Enum

#: Splits a string on its word runs, yielding the whitespace between them.
#: ``re.split(r"\\S+", "a  b\\xa0c")`` → ``['', '  ', '\\xa0', '']``.
_WORDS = re.compile(r"\S+")


class ProjectionFidelity(str, Enum):
    """The level at which a rewritten line carries its decision.

    Ordered best to worst. ``str``-valued so a report round-trips through
    JSON as ``"exact"`` / ``"token_equivalent"`` / ``"normalized"``.
    """

    EXACT = "exact"
    TOKEN_EQUIVALENT = "token_equivalent"
    NORMALIZED = "normalized"


#: Best to worst — for aggregating a run down to its weakest line.
FIDELITY_ORDER: tuple[ProjectionFidelity, ...] = (
    ProjectionFidelity.EXACT,
    ProjectionFidelity.TOKEN_EQUIVALENT,
    ProjectionFidelity.NORMALIZED,
)


def _interior_gaps(text: str) -> list[str]:
    """The whitespace runs BETWEEN the words of ``text``, in order.

    Edges are excluded: a format that cannot store leading or trailing
    whitespace is not substituting anything, it is declining to represent
    something that has no representation. ``n`` words always yield exactly
    ``n - 1`` gaps, which is what lets the caller zip two same-word strings
    together without a length check.
    """
    parts = _WORDS.split(text.strip())
    return parts[1:-1] if len(parts) > 2 else []


def classify_projection_fidelity(
    decided: str, extracted: str
) -> ProjectionFidelity | None:
    """Highest fidelity level at which ``extracted`` carries ``decided``.

    ``None`` means the two diverge in their words — not a level, a
    corrupted deliverable. The caller must fail the run on ``None``; every
    other return value is a legitimate outcome to be recorded, not raised
    on.
    """
    if decided == extracted:
        return ProjectionFidelity.EXACT
    if decided.split() != extracted.split():
        return None
    # Same words, so the difference is whitespace alone. Separate what the
    # format merely collapsed from what it swapped: a gap is degraded when
    # it used a character the artefact's gap does not contain at all.
    for decided_gap, extracted_gap in zip(
        _interior_gaps(decided), _interior_gaps(extracted), strict=True
    ):
        if set(decided_gap) - set(extracted_gap):
            return ProjectionFidelity.NORMALIZED
    return ProjectionFidelity.TOKEN_EQUIVALENT


def weakest(levels: Iterable[ProjectionFidelity | None]) -> ProjectionFidelity | None:
    """The worst level in ``levels``, or ``None`` if it holds none.

    A run is only as faithful as its least faithful line: reporting the
    average, or the best, would hide the single normalised line that is the
    reason this scale exists.
    """
    seen = {level for level in levels if level is not None}
    for level in reversed(FIDELITY_ORDER):
        if level in seen:
            return level
    return None


__all__ = [
    "FIDELITY_ORDER",
    "ProjectionFidelity",
    "classify_projection_fidelity",
    "weakest",
]
