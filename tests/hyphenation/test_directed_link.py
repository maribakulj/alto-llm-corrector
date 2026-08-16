"""One place reads the hyphen pointer fields (ADR-010, S1).

A line carries two link slots and their names are a trap:

    ``hyphen_pair_*``     the PAIR slot
    ``hyphen_forward_*``  the FORWARD slot

"Forward" names the SLOT, not the reading direction. A **PART1** line's word
continues onto the line in its **PAIR** slot; only a **BOTH** line — tail of one
hyphenated word and head of the next — continues through its FORWARD slot.

Every site that re-derived "which slot holds my continuation?" from the role got
a chance to get that backwards, and one did have it spelled out inline right
next to a helper that already knew. These tests pin the mapping so the next
reader does not have to re-infer it, and so a regression is a red test rather
than a mis-reconciled word.
"""

from __future__ import annotations

import pytest

from saknussemm.core.identity import LineRef
from saknussemm.core.pairing import (
    forward_partner_id,
    forward_partner_ref,
    forward_ref,
    pair_ref,
)
from saknussemm.core.schemas import Coords, HyphenRole, LineManifest


def _line(**kw) -> LineManifest:
    base = dict(
        line_id="L1",
        page_id="P1",
        block_id="B1",
        ocr_text="mot-",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=100, height=20),
    )
    base.update(kw)
    return LineManifest(**base)


class TestSlotReaders:
    def test_pair_slot_defaults_to_the_lines_own_page(self):
        lm = _line(hyphen_pair_line_id="L2")
        assert pair_ref(lm) == LineRef(page_id="P1", line_id="L2")

    def test_pair_slot_honours_an_explicit_page(self):
        lm = _line(hyphen_pair_line_id="L2", hyphen_pair_page_id="P9")
        assert pair_ref(lm) == LineRef(page_id="P9", line_id="L2")

    def test_forward_slot_defaults_to_the_lines_own_page(self):
        lm = _line(hyphen_forward_pair_id="L3")
        assert forward_ref(lm) == LineRef(page_id="P1", line_id="L3")

    def test_forward_slot_honours_an_explicit_page(self):
        lm = _line(hyphen_forward_pair_id="L3", hyphen_forward_pair_page_id="P9")
        assert forward_ref(lm) == LineRef(page_id="P9", line_id="L3")

    def test_an_empty_slot_is_none(self):
        lm = _line()
        assert pair_ref(lm) is None
        assert forward_ref(lm) is None

    def test_the_slots_are_read_independently(self):
        lm = _line(hyphen_pair_line_id="L0", hyphen_forward_pair_id="L2")
        assert pair_ref(lm).line_id == "L0"
        assert forward_ref(lm).line_id == "L2"


class TestTheRoleToSlotMap:
    """The trap, pinned. Only PART1 and BOTH continue anywhere, and they use
    DIFFERENT slots to do it."""

    def test_part1_continues_through_its_pair_slot(self):
        lm = _line(
            hyphen_role=HyphenRole.PART1,
            hyphen_pair_line_id="L2",
            hyphen_forward_pair_id="DECOY",
        )
        assert forward_partner_ref(lm) == LineRef(page_id="P1", line_id="L2")

    def test_both_continues_through_its_forward_slot(self):
        lm = _line(
            hyphen_role=HyphenRole.BOTH,
            hyphen_pair_line_id="DECOY",
            hyphen_forward_pair_id="L3",
        )
        assert forward_partner_ref(lm) == LineRef(page_id="P1", line_id="L3")

    @pytest.mark.parametrize("role", [HyphenRole.PART2, HyphenRole.NONE])
    def test_part2_and_none_continue_nowhere(self, role):
        # Even with both slots populated: PART2's pair slot points BACKWARD,
        # and treating it as a continuation would join a word to its own head.
        lm = _line(
            hyphen_role=role,
            hyphen_pair_line_id="L1",
            hyphen_forward_pair_id="L3",
        )
        assert forward_partner_ref(lm) is None
        assert forward_partner_id(lm) is None

    def test_a_role_with_an_empty_slot_continues_nowhere(self):
        lm = _line(hyphen_role=HyphenRole.PART1)
        assert forward_partner_ref(lm) is None


class TestTheBareIdIsTheRefsLineId:
    """``forward_partner_id`` exists for lookups already scoped to one page;
    it must never disagree with the qualified answer."""

    @pytest.mark.parametrize(
        ("role", "kw"),
        [
            (HyphenRole.PART1, {"hyphen_pair_line_id": "L2"}),
            (HyphenRole.BOTH, {"hyphen_forward_pair_id": "L3"}),
            (HyphenRole.PART2, {"hyphen_pair_line_id": "L1"}),
            (HyphenRole.NONE, {}),
        ],
    )
    def test_the_two_agree(self, role, kw):
        lm = _line(hyphen_role=role, **kw)
        ref = forward_partner_ref(lm)
        assert forward_partner_id(lm) == (None if ref is None else ref.line_id)

    def test_the_bare_id_drops_the_page_it_was_qualified_with(self):
        # Why the ref form is preferred document-wide: this id alone cannot
        # tell you which file's L2 it means.
        lm = _line(
            hyphen_role=HyphenRole.PART1,
            hyphen_pair_line_id="L2",
            hyphen_pair_page_id="P9",
        )
        assert forward_partner_id(lm) == "L2"
        assert forward_partner_ref(lm).page_id == "P9"
