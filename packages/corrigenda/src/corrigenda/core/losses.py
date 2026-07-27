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
LOSS_MATRIX_VERSION = "1"


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


#: Whether an ``INVALIDATED`` attribute is reported per occurrence.
#:
#: **This is the one genuinely open decision in the table, and it is left
#: explicit rather than settled by silence** (R4). Today: ALTO says
#: nothing, PAGE counts its equivalent as ``conf_dropped`` — the two
#: formats disagree, which is its own defect whichever way it is resolved.
#:
#: The case FOR counting: an archive wants to know its OCR confidence is
#: gone, and format parity is a stated goal (§6.3).
#: The case AGAINST: it fires on every changed String — 3339 on one real
#: page — and is a deterministic function of how many lines were rewritten,
#: which the report already carries per line as ``rewriter_path``. A
#: counter that can be derived from another counter is noise.
#:
#: Whoever settles it must change BOTH formats in the same commit. Flipping
#: this flag is the ALTO half.
COUNTS_INVALIDATION = False


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


def is_unconditional_loss(attribute: str) -> bool:
    """Does the per-String counter own this attribute's loss?

    False for :data:`ALIGNMENT_SCOPED` attributes — the alignment-aware
    pass owns those, and counting them here too would report a loss on
    every rebuilt String that kept them.
    """
    if attribute.rsplit("}", 1)[-1].upper() in ALIGNMENT_SCOPED:
        return False
    return is_countable_loss(attribute)


def is_countable_loss(attribute: str) -> bool:
    """Does the report carry a counter when this attribute disappears?"""
    _cls, fate = fate_of(attribute)
    if fate is AttributeFate.DROPPED:
        return True
    if fate is AttributeFate.INVALIDATED:
        return COUNTS_INVALIDATION
    return False


__all__ = [
    "ALTO_STRING_ATTRIBUTES",
    "COUNTS_INVALIDATION",
    "LOSS_MATRIX_VERSION",
    "AttributeClass",
    "AttributeFate",
    "ALIGNMENT_SCOPED",
    "fate_of",
    "is_countable_loss",
    "is_unconditional_loss",
]
