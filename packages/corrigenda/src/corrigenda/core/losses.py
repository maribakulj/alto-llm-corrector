"""What a format loss IS, for both formats (`RM-07`).

The loss counters grew one fix at a time: someone noticed an attribute
disappearing, added a counter, moved on. Nothing ever stated what each
attribute is *supposed* to do, so "every loss is counted" was a claim with
no referent — and it was false in both directions at once. The report
claimed 229 dropped ``SUBS_CONTENT`` on a file that kept every one of them,
while 3339 ``WC`` left the same file uncounted.

The referent is a table per format, saying for every attribute which of
four things happens to it, and separately whether that thing is something
the report counts. **The tables are not here.** ALTO's lives in
:mod:`corrigenda.formats.alto.losses`; PAGE counts its own equivalent in
its rewriter. What is here is the vocabulary they share and neither owns:
the two classes, the four fates, and the three constants that make the
two formats say the same thing about the same event.

`RM-07` made that split. Before it, this module carried ALTO's table —
``HPOS``, ``SUBS_CONTENT``, ``WC`` — inside the package whose stated
property is that the pure core knows no format. No test failed, because
nothing imported ``lxml``: the violation was semantic, and a true
statement about the architecture that the architecture did not make. PAGE
imports exactly two names from this module and never needed the table,
which is what made the boundary obvious once it was measured.

The distinction that makes the table work, and that the counters missed:

``STRUCTURAL``
    The attribute belongs to the ``String`` element, one per token. When a
    correction re-segments a line the token count changes and so does the
    attribute count — the slow path on X0000002 goes from 3395 ``HPOS`` to
    3963 because it wrote MORE words, not because it lost any. Counting
    that delta as loss (or gain) is a category error: nothing was lost, the
    line was re-tokenised, and the re-tokenisation is the correction.

``SEMANTIC``
    The attribute carries information the source engine asserted about a
    specific reading — a confidence, a style, a tag reference. It does not
    follow the tokens, and when it goes, something an archive cared about
    is gone.

Only SEMANTIC attributes can be lost. That is the whole of the false
half above: SUBS_TYPE and SUBS_CONTENT were being counted as lost when
they are re-established from the manifest on the very same pass.
"""

from __future__ import annotations

from enum import Enum

#: Bump when a fate changes meaning or an attribute moves between fates —
#: the report's consumers key their expectations to this, not to the
#: library version.
#:
#: ``"2"`` (2026-07-28): ``INVALIDATED`` attributes are now
#: counted, per line, under one key shared by both formats. No attribute
#: changed fate; what changed is what the report says about a fate, which
#: is the same thing to a consumer reading counters.
LOSS_MATRIX_VERSION = "2"


class AttributeClass(str, Enum):
    """Does the attribute belong to the token, or to the reading?"""

    #: One per ``String``; its count follows re-segmentation. Cannot be
    #: "lost" — only redistributed.
    STRUCTURAL = "structural"
    #: An assertion about a reading. Its disappearance is a real loss.
    SEMANTIC = "semantic"


class AttributeFate(str, Enum):
    """What the rewriter does with the attribute."""

    #: Carried through untouched.
    PRESERVED = "preserved"
    #: Recomputed for the new tokens (geometry) or re-established from
    #: manifest state (the hyphenation attributes). Present in the output,
    #: possibly with a different value. NOT a loss.
    REWRITTEN = "rewritten"
    #: Deliberately removed because a correction made it false. The source
    #: engine's per-word confidence does not survive someone changing the
    #: word. Removing it is right; saying nothing about it is the open
    #: question — see ``COUNTS_INVALIDATION`` below.
    INVALIDATED = "invalidated"
    #: Removed because it cannot be re-attached to a re-segmented word
    #: without guessing. A real loss, and counted.
    DROPPED = "dropped"


#: Whether the report carries a counter when an ``INVALIDATED`` attribute
#: goes. **Settled 2026-07-28**, after being left explicit rather than
#: decided by silence: yes — but counted **per line, not per occurrence**.
#:
#: The two arguments were both right about different units. FOR counting: an
#: archive wants to know its OCR confidence is gone, and format parity is a
#: stated goal (§6.3) — ALTO said nothing while PAGE counted its equivalent
#: as ``conf_dropped``, so the two formats disagreed, which was its own
#: defect whichever way it resolved. AGAINST: per occurrence it fires on
#: every changed String — 3339 on one real page — drowning the four-digit
#: signal that matters in a five-digit one that does not, and varying with
#: how wordy a line is rather than with anything an archivist decides on.
#:
#: Per line answers both. "412 lines lost their OCR confidence" is the fact
#: an archive acts on; how many Strings each of those lines held is not.
#: It is also the unit the rest of the report already speaks — every other
#: entry in ``format_losses`` is attributable to a line (ADR-012), and a
#: per-occurrence counter could not be.
COUNTS_INVALIDATION = True

#: The unit :data:`COUNTS_INVALIDATION` counts in. Named because "3339" and
#: "412" are both plausible readings of the same counter and the difference
#: is the whole decision above; a consumer must not have to guess.
INVALIDATION_UNIT = "line"

#: The single key both formats emit for it. ALTO had none and PAGE called it
#: ``conf_dropped``; one name, one unit, in both, is the parity half of
#: the same decision.
#: "invalidated" rather than "dropped" on purpose — the attribute did not
#: fall through a gap, it was removed because a correction made it false.
INVALIDATION_COUNTER = "confidence_invalidated"


__all__ = [
    "COUNTS_INVALIDATION",
    "INVALIDATION_COUNTER",
    "INVALIDATION_UNIT",
    "LOSS_MATRIX_VERSION",
    "AttributeClass",
    "AttributeFate",
]
