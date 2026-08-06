"""The order of the finalisation passes decides what ships — and nothing
enforces it (`RM-01`).

``core/finalize.py`` runs three document-wide passes and its docstring says
outright that "their ORDER is the whole content of this module". That is an
honest statement of a real contract, and it is the only thing holding it: no
type, no assertion, no test. A contributor who inserts a fourth pass, or who
reorders two while moving code between modules, breaks a rule that exists
only in prose — and the suite stays green, because every other test in this
package checks the FINAL state of a run that used the right order.

These two tests split that into what is true today and what should be true.

:func:`test_pass_order_changes_the_delivered_text` PASSES. It is the
evidence: permuting two passes changes the corrected text of a line, not
merely a counter or a reason.

:func:`test_wrong_pass_order_is_refused` XFAILS. It is the property `RM-01`
owes: a wrong order should be refused rather than silently producing
different output. It is ``strict``, so the day the guard lands this test
turns XPASS and fails — which is how the marker retires itself instead of
being forgotten.
"""

from __future__ import annotations

import pytest

from corrigenda.core.acceptance import _global_adjacency_pass, _loss_policy_pass
from corrigenda.core.finalize import _preserve_break_chars
from corrigenda.core.schemas import GuardConfig, LossPolicy

from tests.decision._state import document, line, snapshot

#: A gate that is OFF by default (`RM-04` territory) but on a supported
#: setting. It is the cheapest way to make the loss pass do something on
#: ALTO: ``strict`` needs ``word_count``, which only the PAGE parser fills.
_GATED = LossPolicy(min_alignment_score=0.6)
_GUARDS = GuardConfig()


def _two_lines_one_gated():
    """Two adjacent lines proposing the SAME correction from clearly
    different sources — an adjacent duplicate — where only the first one's
    correction changes its word count and so trips the token_realign gate.

    That asymmetry is what makes the interaction visible: whichever pass
    runs first removes the other's evidence.
    """
    return document(
        [
            # 3 source words -> 4 corrected: the realign gate fires.
            line(1, "le chat noir", "LE CHAT GRIS TRES"),
            # 4 source words -> 4 corrected: the gate does NOT fire, so this
            # line only ever reverts as somebody's duplicate.
            line(2, "une souris grise ici", "LE CHAT GRIS TRES"),
        ]
    )


def _run_canonical():
    manifest, all_lines, traces = _two_lines_one_gated()
    _global_adjacency_pass(
        guard_config=_GUARDS,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _preserve_break_chars(manifest)
    sidecar = _loss_policy_pass(
        loss_policy=_GATED,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    return snapshot(manifest, traces), sidecar


def _run_loss_first():
    """The loss gate before the adjacency pass — one swap, nothing else."""
    manifest, all_lines, traces = _two_lines_one_gated()
    sidecar = _loss_policy_pass(
        loss_policy=_GATED,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _global_adjacency_pass(
        guard_config=_GUARDS,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _preserve_break_chars(manifest)
    return snapshot(manifest, traces), sidecar


def test_pass_order_changes_the_delivered_text() -> None:
    """Swapping two passes changes what the file says, not just what the
    report counts.

    Canonical order — the adjacency pass sees both lines still holding
    their pre-revert corrections, recognises the duplicate, and reverts
    BOTH. Neither correction ships, and neither is preserved: a duplicate
    is discarded, not set aside.

    Loss-first — the gate reverts ``L1`` before the adjacency pass runs.
    ``L1`` now presents its source text, so the two lines no longer look
    like the same correction, the duplicate is never detected, and ``L2``
    SHIPS a correction the canonical order rejects.

    That is the shape of the defect: not a wrong number in a report, a
    different sentence in the delivered XML.
    """
    canonical, canonical_sidecar = _run_canonical()
    loss_first, loss_first_sidecar = _run_loss_first()

    # Canonical: both lines fall back, as duplicates of each other.
    assert canonical["L1"] == (
        "le chat noir",
        "fallback",
        "adjacent_duplicate_detected",
    )
    assert canonical["L2"] == (
        "une souris grise ici",
        "fallback",
        "adjacent_duplicate_detected",
    )
    assert canonical_sidecar == []

    # Loss-first: L1 is gated, and its revert hides the duplicate, so L2
    # keeps a correction the canonical order threw away.
    assert loss_first["L1"][0] == "le chat noir"
    assert loss_first["L1"][1] == "fallback"
    assert loss_first["L1"][2] is not None
    assert loss_first["L1"][2].startswith("token_realign:")
    assert loss_first["L2"] == ("LE CHAT GRIS TRES", "corrected", None)
    assert [entry.line_id for entry in loss_first_sidecar] == ["L1"]

    # Stated once, plainly, so a reader does not have to diff the two dicts.
    assert canonical["L2"][0] != loss_first["L2"][0], (
        "the two orders must differ in delivered text — if they no longer "
        "do, this scenario stopped demonstrating anything and needs "
        "rebuilding, not deleting"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RM-01 — the order of the finalisation passes is a contract held by "
        "a docstring in core/finalize.py and by nothing else. Calling them "
        "out of order is not refused, not detected, and not reported: it "
        "just produces different output. Remove this marker when the guard "
        "exists."
    ),
)
def test_wrong_pass_order_is_refused() -> None:
    """A wrong order should fail loudly, not ship different bytes.

    The assertion below is the property, not a description of today: run
    the loss gate before the adjacency pass and *something* should object.
    Nothing does, which is the whole of `RM-01`'s first half.

    What "refused" ends up meaning is `RM-01`'s design call — a sequencing
    token the passes consume, a state flag on the manifest, or a single
    entry point that owns the order and is the only way to call them. This
    test pins the requirement, not the mechanism, so it stays valid
    whichever is chosen.
    """
    with pytest.raises(Exception):
        _run_loss_first()
