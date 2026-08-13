"""What happens to each ALTO ``String`` attribute when a line is rewritten.

The table, and the four predicates that read it. Lived in
``core/losses.py`` until `RM-07`, which is the defect it was: a module
whose whole point is that the pure core knows no format was the module
naming ``HPOS``, ``SUBS_CONTENT`` and ``WC``. Nothing imported ``lxml``
because of it and the import contract stayed green, so the violation was
never a broken rule — it was a true statement about the architecture that
the architecture did not make.

What stayed behind in :mod:`corrigenda.core.losses` is what BOTH formats
read and neither owns: the two fates an attribute can have
(:class:`~corrigenda.core.losses.AttributeClass`,
:class:`~corrigenda.core.losses.AttributeFate`), the decision to count
invalidation per line, and the single counter key the two formats share.
PAGE imports exactly two names from there and never needed this table;
that asymmetry is what made the split obvious once it was measured.

**Written from measurement, not from belief.** Every fate below was
observed on ``examples/sample.xml`` and ``examples/X0000002.xml`` across
all three write paths; the numbers in the comments are what those files
actually do. `RM-07` moved the table without touching a value —
``tests/test_loss_accounting_is_real.py`` is the differential that says
so, and it checks the rewriter against this table rather than against
anyone's memory.
"""

from __future__ import annotations

from corrigenda.core.losses import (
    COUNTS_INVALIDATION,
    AttributeClass,
    AttributeFate,
)


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
#: for one attribute is exactly the double-count this table exists to
#: prevent, so the split is named here rather than left implicit in
#: whichever list each site happens to carry.
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
    sites counting one attribute is precisely the double-count to avoid:

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
    "ALIGNMENT_SCOPED",
    "ALTO_STRING_ATTRIBUTES",
    "INVALIDATED_ATTRIBUTES",
    "fate_of",
    "is_countable_loss",
    "is_invalidated",
    "is_unconditional_loss",
]
