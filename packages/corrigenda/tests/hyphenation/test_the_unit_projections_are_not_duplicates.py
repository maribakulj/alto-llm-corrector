"""Two projections of one derivation, and why they cannot be merged.

`RM-08` reads "five neighbouring projections of the hyphen unit
(``_page_local_units`` / ``_units_visible_on_page`` nearly identical)" and
files it as duplication to pay down. That description is **out of date**, and
this module is the measurement that closes it.

The two functions were parallel RESOLVERS once: each re-read the pointer
fields to ask "who is my partner?", which is exactly the shape `S1` spent the
year removing. They are not that any more. Both read **zero pointer fields**
and both go through the one shared derivation (``derive_hyphen_groups``,
ADR-010). What is left is not duplicated logic — it is one derivation seen
through two filters, for a reason written in each docstring:

  * the **router** may decline. Escalating half a unit to a second producer
    would split it, so an incomplete unit is left to the primary and its
    members stay together by doing nothing. ``_page_local_units`` therefore
    returns nothing for a unit that is not whole.
  * the **image-cap batcher** may not. It is slicing one chunk into several
    calls, so "leave them alone" is not on the menu — every line lands in
    some batch. Handed nothing, it treated each member as a singleton and
    could put a pair in two different calls, which is the one thing pair
    atomicity forbids. ``_units_visible_on_page`` therefore returns the
    members that ARE here, whole unit or not.

So the merge `RM-08` asks for would have to pick one behaviour and would
silently change the other. The test below is what makes that concrete rather
than arguable: it exhibits a document where the two genuinely disagree. If a
future change makes them agree everywhere, they ARE redundant and this test
says so by failing — which is the honest way for an item like `RM-08` to
reopen.

`docs/PLAN.md` carries the closure and the reason.
"""

from __future__ import annotations

import ast
import inspect
import re

from corrigenda.core.reconcile import _page_local_units, _units_visible_on_page
from corrigenda.core.schemas import HyphenRole

from tests.hyphenation._lines import _line

#: The storage of record. `S1` keeps it authoritative for now, and the point
#: of the shared derivation is that a projection never reads it.
_POINTER_FIELDS = re.compile(r"\.hyphen_\w+")


def _a_chain_that_leaves_the_page() -> dict[str, object]:
    """A → B on this page, B → C on the next. Two members here, unit not whole.

    The shape both docstrings describe, and the one where their answers have
    to differ: the router must see nothing to act on, the batcher must see
    two lines it may not separate.
    """
    part1 = _line("A", "mot-", role=HyphenRole.PART1)
    both = _line("B", "cou-", role=HyphenRole.BOTH)
    part1.hyphen_pair_line_id = "B"
    both.hyphen_pair_line_id = "A"
    both.hyphen_forward_pair_id = "C"
    both.hyphen_forward_pair_page_id = "p2"
    return {"A": part1, "B": both}


def test_the_router_declines_what_the_batcher_must_still_group() -> None:
    """The disagreement, exhibited. Merging the two would erase one side."""
    page = _a_chain_that_leaves_the_page()

    assert _page_local_units(page) == {}, (
        "the router was handed a unit that is not whole on this page. "
        "Escalating part of it would split the pair across producers; "
        "returning nothing is what leaves the members together."
    )
    assert _units_visible_on_page(page) == {"A": {"A", "B"}, "B": {"A", "B"}}, (
        "the batcher must still be told A and B belong in one call. It has "
        "no option to decline — every line lands in some batch — so an empty "
        "answer makes each member a singleton and lets a pair land in two "
        "different producer calls."
    )


def test_neither_projection_reads_a_pointer_field() -> None:
    """The `S1` property that turned them from resolvers into projections.

    A projection that re-reads the pointers is a parallel resolver wearing a
    different name, and five of those were the debt.
    """
    offenders = {
        function.__name__: sorted(
            set(_POINTER_FIELDS.findall(inspect.getsource(function)))
        )
        for function in (_page_local_units, _units_visible_on_page)
        if _POINTER_FIELDS.search(inspect.getsource(function))
    }
    assert not offenders, (
        f"a unit projection reads the pointer fields directly: {offenders}. "
        "That is a sixth resolver — the grouping question is answered once, "
        "by derive_hyphen_groups."
    )


def test_both_go_through_the_one_shared_derivation() -> None:
    """Same source of truth, or the agreement above means nothing."""
    for function in (_page_local_units, _units_visible_on_page):
        called = {
            node.func.id
            for node in ast.walk(ast.parse(inspect.getsource(function)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "derive_hyphen_groups" in called, (
            f"{function.__name__} no longer derives its groups from the "
            "shared derivation — whatever it returns is now its own opinion."
        )
