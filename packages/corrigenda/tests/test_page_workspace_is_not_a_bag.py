"""``PageWorkspace`` holds indices, and must not become a bag (`RM-03`).

Grouping three parameters into an object is a good trade exactly once.
The failure mode is what happens next: the object is already threaded
everywhere, so the cheapest place to put ANY new per-run value is inside
it, and three commits later it carries a counter, a metric and a cache —
which is the per-run mutable state `ADR-011` spent a slice removing from
the engine.

So the rule is written down and mechanical rather than left to taste:

  1. exactly the three indices, no fourth field;
  2. frozen — a field cannot be rebound;
  3. no method that writes anything.

Rule 3 is the one with the subtle boundary. The dicts inside ARE the
run's live state: ``traces`` is written by :mod:`corrigenda.core.decide`,
and the manifests in ``line_by_id`` are what a run mutates. The workspace
does not make them immutable and never claimed to. What it must not do is
offer a door of its own — the moment it grows ``def record(...)`` it has
become the writer, and `RM-01` put the writer somewhere else on purpose.

Run state — counters, metrics, usage, the abort probe — belongs to
:class:`~corrigenda.core.context.RunContext`. That separation is the
whole reason two objects exist instead of one.
"""

from __future__ import annotations

import dataclasses

from corrigenda.core.workspace import PageWorkspace

#: The three indices, and nothing else. Adding a field here is a design
#: decision that has to be argued in a diff, not a convenience.
_EXPECTED_FIELDS = {"line_by_id", "cross_page_partners", "traces"}


def test_the_workspace_carries_exactly_the_three_indices() -> None:
    fields = {f.name for f in dataclasses.fields(PageWorkspace)}
    assert fields == _EXPECTED_FIELDS, (
        f"PageWorkspace carries {sorted(fields)}. It groups the three "
        "INDICES a page's work reads; anything a run accumulates belongs "
        "to RunContext. A fourth field is how this becomes the mutable bag "
        "ADR-011 removed."
    )


def test_the_workspace_is_frozen() -> None:
    """Not deep immutability — the dicts are live — but no rebinding."""
    params = getattr(PageWorkspace, "__dataclass_params__")
    assert params.frozen, "PageWorkspace must stay a frozen dataclass"


def test_the_workspace_offers_no_way_to_write() -> None:
    """It exposes indices. It does not expose a door.

    Decisions are written by ``core/decide.py`` and nothing else
    (``tests/decision/test_decision_write_exclusivity.py``). A method here
    that mutated anything would be a second writer wearing an object's
    clothes — invisible to that ratchet, which scans for attribute
    assignment rather than for intent.
    """
    public = {
        name
        for name in vars(PageWorkspace)
        if not name.startswith("_") and callable(getattr(PageWorkspace, name, None))
    }
    assert not public, (
        f"PageWorkspace grew method(s) {sorted(public)}. Reading is what it "
        "is for; writing goes through core/decide.py."
    )


def test_a_workspace_cannot_be_rebound_in_place() -> None:
    """The frozen guarantee, exercised rather than introspected."""
    workspace = PageWorkspace(line_by_id={}, cross_page_partners=None, traces=None)
    try:
        workspace.line_by_id = {}  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("PageWorkspace allowed a field to be rebound")
