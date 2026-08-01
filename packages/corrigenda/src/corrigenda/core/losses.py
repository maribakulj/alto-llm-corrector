"""What happens to each source attribute when a line is rewritten (R0).

The loss counters grew one fix at a time: someone noticed an attribute
disappearing, added a counter, moved on. Nothing ever stated what each
attribute is *supposed* to do, so "every loss is counted" was a claim with
no referent — and it was false in both directions at once. The report
claimed 229 dropped ``SUBS_CONTENT`` on a file that kept every one of them,
while 3339 ``WC`` left the same file uncounted.

This module is the referent. One table, versioned, saying for every
attribute which of five things happens to it — and, separately, whether
that thing is something the report counts. The differential test
(``tests/test_loss_accounting_is_real.py``) checks the rewriter against
this table rather than against anyone's memory.

**Written from measurement, not from belief.** Every fate below was
observed on ``examples/sample.xml`` and ``examples/X0000002.xml`` across
all three write paths; the numbers in the comments are what those files
actually do.

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

Only SEMANTIC attributes can be lost. That is the whole of R1: SUBS_TYPE
and SUBS_CONTENT were being counted as lost when they are re-established
from the manifest on the very same pass.
"""

from __future__ import annotations

from enum import Enum

#: Bump when a fate changes meaning or an attribute moves between fates —
#: the report's consumers key their expectations to this, not to the
#: library version.
#:
#: ``"2"`` (2026-07-28): R4 settled. ``INVALIDATED`` attributes are now
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
#: goes. **Settled 2026-07-28** (R4), after being left explicit rather than
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
#: ``conf_dropped``; one name, one unit, in both, is the parity half of R4.
#: "invalidated" rather than "dropped" on purpose — the attribute did not
#: fall through a gap, it was removed because a correction made it false.
INVALIDATION_COUNTER = "confidence_invalidated"


#: ALTO ``String`` attributes. Anything absent is treated as SEMANTIC /
#: DROPPED — the conservative default, and the one that makes an
#: unrecognised dialect attribute show up in the report instead of
#: vanishing quietly.
ALTO_STRING_ATTRIBUTES: dict[str, tuple[AttributeClass, AttributeFate]] = {
    # --- structural: one per token, redistributed on re-segmentation ---
    # CONTENT is the payload the run exists to change. A rebuild REPLACES
    # the source reading with the correction; it does not lose it.
    "CONTENT": (AttributeClass.STRUCTURAL, AttributeFate.REWRITTEN),
    "ID": (AttributeClass.STRUCTURAL, AttributeFate.REWRITTEN),
    "HPOS": (AttributeClass.STRUCTURAL, AttributeFate.REWRITTEN),
    "VPOS": (AttributeClass.STRUCTURAL, AttributeFate.REWRITTEN),
    "WIDTH": (AttributeClass.STRUCTURAL, AttributeFate.REWRITTEN),
    "HEIGHT": (AttributeClass.STRUCTURAL, AttributeFate.REWRITTEN),
    # --- semantic, re-established from the manifest ---
    # ``_apply_subs`` runs on all three write paths and writes both from the
    # line's own hyphen state. Measured: 234 in, 234 out, on every path.
    "SUBS_TYPE": (AttributeClass.SEMANTIC, AttributeFate.REWRITTEN),
    "SUBS_CONTENT": (AttributeClass.SEMANTIC, AttributeFate.REWRITTEN),
    # --- semantic, carried through ---
    # Measured: 13 in, 13 out, on every path.
    "STYLEREFS": (AttributeClass.SEMANTIC, AttributeFate.PRESERVED),
    # --- semantic, invalidated by a content change ---
    # The engine's confidence in a word it no longer contains is not a fact
    # about the output. Measured: 3395 -> 2864 (fast), 3395 -> 0 (slow).
    "WC": (AttributeClass.SEMANTIC, AttributeFate.INVALIDATED),
    "CC": (AttributeClass.SEMANTIC, AttributeFate.INVALIDATED),
    # --- semantic, dropped only when the alignment loses their String ---
    # These two survive when their String is matched to a target token and
    # go when it is not, so their loss is CONDITIONAL and the rewriter has
    # an alignment-aware pass that counts them. The unconditional counter
    # must leave them alone or it double-counts. Measured: 47 STYLE -> 44,
    # with 3 counted as style_dropped. That pass was already honest.
    "STYLE": (AttributeClass.SEMANTIC, AttributeFate.DROPPED),
}

#: Attributes whose loss depends on whether their ``String`` survived token
#: alignment, and which the rewriter counts in its alignment-aware pass.
#:
#: They are DROPPED in the table — that is their fate WHEN lost — but the
#: unconditional per-String counter must skip them, or every rebuilt line
#: reports a loss for an attribute that is still there. Two counting sites
#: for one attribute is exactly the shape of R1, so the split is named here
#: rather than left implicit in whichever list each site happens to carry.
ALIGNMENT_SCOPED: frozenset[str] = frozenset({"STYLE", "STYLEREFS"})


def fate_of(attribute: str) -> tuple[AttributeClass, AttributeFate]:
    """The declared fate of an ALTO ``String`` attribute.

    Unknown attributes — a producer's dialect extension, a namespace we do
    not model — are SEMANTIC and DROPPED. That default is deliberate: an
    attribute nobody thought about should surface in the loss report, not
    disappear on the assumption it did not matter.
    """
    return ALTO_STRING_ATTRIBUTES.get(
        attribute.rsplit("}", 1)[-1].upper(),
        (AttributeClass.SEMANTIC, AttributeFate.DROPPED),
    )


def is_invalidated(attribute: str) -> bool:
    """Is this attribute removed because a correction made it false?

    The rewriters use it to know what to watch for on a line; the report
    counts those removals once per line (:data:`INVALIDATION_UNIT`).
    """
    _cls, fate = fate_of(attribute)
    return fate is AttributeFate.INVALIDATED


def is_unconditional_loss(attribute: str) -> bool:
    """Does the per-String counter own this attribute's loss?

    False in two cases, both because another site already owns it, and two
    sites counting one attribute is precisely the shape of R1:

    * :data:`ALIGNMENT_SCOPED` — the alignment-aware pass owns those, and
      counting them here too would report a loss on every rebuilt String
      that kept them.
    * :data:`AttributeFate.INVALIDATED` — the per-LINE counter owns those.
      This is what keeps ``COUNTS_INVALIDATION = True`` from meaning "per
      occurrence": the decision was to count lines, so the per-String pass
      must stay out of it entirely.
    """
    local = attribute.rsplit("}", 1)[-1].upper()
    if local in ALIGNMENT_SCOPED or is_invalidated(local):
        return False
    return is_countable_loss(local)


def is_countable_loss(attribute: str) -> bool:
    """Does the report carry a counter when this attribute disappears?"""
    _cls, fate = fate_of(attribute)
    if fate is AttributeFate.DROPPED:
        return True
    if fate is AttributeFate.INVALIDATED:
        return COUNTS_INVALIDATION
    return False


#: The attributes :func:`is_invalidated` answers True for, as a set — the
#: rewriters need to look for their presence on an element, not ask about a
#: name they already hold.
INVALIDATED_ATTRIBUTES: frozenset[str] = frozenset(
    name
    for name, (_cls, fate) in ALTO_STRING_ATTRIBUTES.items()
    if fate is AttributeFate.INVALIDATED
)


__all__ = [
    "ALTO_STRING_ATTRIBUTES",
    "COUNTS_INVALIDATION",
    "INVALIDATED_ATTRIBUTES",
    "INVALIDATION_COUNTER",
    "INVALIDATION_UNIT",
    "LOSS_MATRIX_VERSION",
    "AttributeClass",
    "AttributeFate",
    "ALIGNMENT_SCOPED",
    "fate_of",
    "is_countable_loss",
    "is_invalidated",
    "is_unconditional_loss",
]
