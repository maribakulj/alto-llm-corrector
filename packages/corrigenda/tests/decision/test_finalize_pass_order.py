"""The order of the finalisation passes decides what ships, and is now
enforced (`RM-01`).

``core/finalize.py`` runs three document-wide passes and its docstring says
outright that "their ORDER is the whole content of this module". Until
`RM-01` that was the only thing holding it: no type, no assertion, no test.
A contributor who inserted a fourth pass, or reordered two while moving
code between modules, broke a rule that existed only in prose — and the
suite stayed green, because every other test in this package checks the
FINAL state of a run that used the right order.

:func:`test_pass_order_changes_the_delivered_text` is why that mattered.
Permuting two passes does not renumber a report: it changes the corrected
TEXT of a line, and ships a correction the canonical order rejects.

:func:`test_wrong_pass_order_is_refused` is the guard. It was written as a
strict ``xfail`` in session 3, held the requirement while the mechanism was
undecided, and the marker came off when
:class:`~corrigenda.core.acceptance._FinalizeOrder` landed — which is what
``strict`` was for.

The demonstration and the guard coexist because the token is OPTIONAL:
``order=None`` means unchecked, which is the only way a test can still run
the wrong order on purpose and show what the guard prevents. Production
never passes ``None`` — :func:`test_finalize_document_threads_the_order`
reads the source and fails if any pass is called without it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from corrigenda.core.acceptance import (
    _FinalizeOrder,
    _global_adjacency_pass,
    _loss_policy_pass,
)
from corrigenda.core.finalize import _preserve_break_chars
from corrigenda.core.schemas import GuardConfig, LossPolicy

from tests.decision._state import document, line, snapshot

SRC = Path(__file__).parent.parent.parent / "src" / "corrigenda"

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


def _run_canonical(order: _FinalizeOrder | None = None):
    manifest, all_lines, traces = _two_lines_one_gated()
    _global_adjacency_pass(
        guard_config=_GUARDS,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
        order=order,
    )
    _preserve_break_chars(manifest, order)
    sidecar = _loss_policy_pass(
        loss_policy=_GATED,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
        order=order,
    )
    return snapshot(manifest, traces), sidecar


def _run_loss_first(order: _FinalizeOrder | None = None):
    """The loss gate before the adjacency pass — one swap, nothing else."""
    manifest, all_lines, traces = _two_lines_one_gated()
    sidecar = _loss_policy_pass(
        loss_policy=_GATED,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
        order=order,
    )
    _global_adjacency_pass(
        guard_config=_GUARDS,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
        order=order,
    )
    _preserve_break_chars(manifest, order)
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


def test_wrong_pass_order_is_refused() -> None:
    """A wrong order fails loudly instead of shipping different bytes.

    The loss gate declares that adjacency and break-char preservation must
    have run; asked to go first, it refuses. ``RuntimeError`` rather than a
    ``CorrigendaError`` on purpose — a wrong pass order is an engine bug,
    and ``CorrigendaError`` is the family the chunk loop is allowed to
    absorb (ADR-008).
    """
    with pytest.raises(RuntimeError, match="ran before"):
        _run_loss_first(_FinalizeOrder())


def test_the_canonical_order_is_accepted() -> None:
    """The guard must not be a guard against everything."""
    canonical, sidecar = _run_canonical(_FinalizeOrder())
    assert canonical["L1"][1] == "fallback"
    assert sidecar == []


def test_a_pass_cannot_run_twice_in_one_run() -> None:
    """Each pass reverts against what the previous left behind, so a repeat
    is not idempotent — running the whole sequence twice on one token is a
    bug, not a no-op."""
    order = _FinalizeOrder()
    _run_canonical(order)
    with pytest.raises(RuntimeError, match="ran twice"):
        _run_canonical(order)


def test_finalize_document_threads_the_order() -> None:
    """The token is optional so a test can opt out; production may not.

    Reads ``_finalize_document`` and fails if it calls a pass without an
    ``order``. Without this, the escape hatch that lets
    :func:`test_pass_order_changes_the_delivered_text` exist would also let
    a future edit drop the guard silently.
    """
    import ast

    source = (SRC / "core" / "finalize.py").read_text(encoding="utf-8")
    fn = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "_finalize_document"
    )
    called = {
        node.func.id: node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for name in (
        "_global_adjacency_pass",
        "_preserve_break_chars",
        "_loss_policy_pass",
    ):
        call = called.get(name)
        assert call is not None, f"_finalize_document no longer calls {name}"
        passes_order = any(kw.arg == "order" for kw in call.keywords) or any(
            isinstance(a, ast.Name) and a.id == "order" for a in call.args
        )
        assert passes_order, (
            f"_finalize_document calls {name} without an order token — the "
            "production path must always be checked; only tests may opt out."
        )
