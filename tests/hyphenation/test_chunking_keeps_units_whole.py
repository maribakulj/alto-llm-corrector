"""No chunk boundary may separate a still-linked pair (L7).

Pair atomicity is the invariant the whole planner exists to serve: the
validator skips a pair that is not wholly in-chunk, and the reconciler could
write across the boundary. There are exactly two legitimate outcomes for a
linked pair at planning time — **together in one chunk**, or **severed with a
``HyphenSplit`` on the plan**. A pair that is neither is a silent hole.

The LINE planner's chain follow required the partner to be the literally NEXT
line. That is a different question from "where is my partner?", and it answers
it wrongly whenever anything sits between the two. It answered it wrongly
*more often* the moment the linker learned to step over blank lines (L5): a
pair linked L0 → L2 failed the adjacency test, the chain stopped at L0, the
two members landed in different chunks, and the link stayed live with no
record. Measured before the fix:

    chunks: [['L0'], ['L1'], ['L2'], ['L3']]
    splits: []
    L0 still linked to: L2

So the test is the invariant itself, not the shape of the fix, and it runs
over several page shapes rather than the one that exposed it.
"""

from __future__ import annotations

import pytest

from saknussemm.core.pairing import forward_partner_id, link_hyphen_pairs
from saknussemm.core.planner import plan_page
from saknussemm.core.schemas import (
    ChunkGranularity,
    ChunkPlannerConfig,
    Coords,
    LineManifest,
    PageManifest,
    PairingPolicy,
)
from saknussemm.formats.page.parser import _assign_hyphen_roles


def _page(texts: list[str]) -> PageManifest:
    return PageManifest(
        page_id="P1",
        page_index=0,
        source_file="f.xml",
        page_width=600,
        page_height=800,
        blocks=[],
        lines=[
            LineManifest(
                line_id=f"L{i}",
                page_id="P1",
                block_id="B1",
                line_order_global=i,
                line_order_in_block=i,
                coords=Coords(hpos=0, vpos=i * 40, width=300, height=30),
                ocr_text=text,
            )
            for i, text in enumerate(texts)
        ],
    )


def _plan(texts: list[str], cap: int = 5):
    """Roles, links, then a LINE plan — the real order a run goes through."""
    page = _page(texts)
    _assign_hyphen_roles(page.lines)
    link_hyphen_pairs(page.lines, PairingPolicy(geometric_checks=False))
    plan = plan_page(
        page,
        "d1",
        ChunkPlannerConfig(
            max_input_chars_per_request=10_000, max_lines_per_request=cap
        ),
        force_granularity=ChunkGranularity.LINE,
    )
    return page, plan


def assert_no_live_link_crosses_a_chunk(page: PageManifest, plan) -> None:
    """THE invariant. Read after planning, because planning may sever."""
    chunk_of: dict[str, int] = {}
    for index, chunk in enumerate(plan.chunks):
        for line_id in chunk.line_ids:
            chunk_of[line_id] = index

    on_page = {lm.line_id for lm in page.lines}
    for lm in page.lines:
        partner = forward_partner_id(lm)
        if not partner or partner not in on_page:
            continue  # no link, or a cross-page one this plan cannot own
        assert chunk_of[lm.line_id] == chunk_of[partner], (
            f"{lm.line_id} is still linked to {partner} but they are in "
            f"chunks {chunk_of[lm.line_id]} and {chunk_of[partner]}. A pair "
            "must be together or severed with a HyphenSplit — never split "
            "while linked."
        )


def assert_every_line_is_in_exactly_one_chunk(page: PageManifest, plan) -> None:
    """The other half: a chain follow that SKIPS the lines between a break
    and its continuation would leave them in no chunk at all."""
    seen: list[str] = [lid for chunk in plan.chunks for lid in chunk.line_ids]
    assert sorted(seen) == sorted(lm.line_id for lm in page.lines)
    assert len(seen) == len(set(seen)), f"a line is in two chunks: {seen}"


#: Page shapes worth running the invariant over. Each is a sentence about
#: what the planner has to survive, not a regression fixture.
_SHAPES: dict[str, list[str]] = {
    "adjacent pair": ["une admini-", "stration complète"],
    "pair across one blank": ["une admini-", "", "stration complète"],
    "pair across three blanks": ["une admini-", "", "  ", "", "stration"],
    "chain of three": ["une admini-", "stra-", "tion complète"],
    "chain of three with blanks": ["une admini-", "", "stra-", "", "tion"],
    "two independent pairs": ["admini-", "stration", "encore admi-", "nistration"],
    "pair then plain lines": ["admini-", "stration", "du texte", "encore"],
    "plain lines then pair": ["du texte", "encore", "admini-", "stration"],
    "break with nothing after it": ["du texte", "admini-"],
    "break followed only by a blank": ["du texte", "admini-", ""],
    "long chain over the cap": [f"mot{chr(97 + i)}-" for i in range(12)],
    "long chain over the cap, with blanks": [
        text for i in range(8) for text in (f"mot{chr(97 + i)}-", "")
    ],
}


@pytest.mark.parametrize("shape", sorted(_SHAPES))
@pytest.mark.parametrize("cap", [2, 3, 5, 12])
def test_no_live_link_crosses_a_chunk_boundary(shape: str, cap: int) -> None:
    page, plan = _plan(_SHAPES[shape], cap=cap)
    assert_no_live_link_crosses_a_chunk(page, plan)
    assert_every_line_is_in_exactly_one_chunk(page, plan)


@pytest.mark.parametrize("shape", sorted(_SHAPES))
@pytest.mark.parametrize("cap", [2, 3, 5, 12])
def test_every_severed_link_is_recorded(shape: str, cap: int) -> None:
    """A cut is a unit operation, not a side effect: if the planner severed
    anything, the plan says so, and every record names a pair that really is
    unlinked afterwards."""
    page, plan = _plan(_SHAPES[shape], cap=cap)
    by_id = {lm.line_id: lm for lm in page.lines}
    for split in plan.hyphen_splits:
        assert split.page_id == "P1"
        tail = by_id[split.tail_line_id]
        assert forward_partner_id(tail) != split.head_line_id, (
            f"{split.tail_line_id} is recorded as severed from "
            f"{split.head_line_id} but still points at it"
        )


class TestTheCaseThatExposedIt:
    """Kept as its own test, with the numbers, because the general invariant
    above would also have passed on the day the adjacency test was written —
    nothing then produced a non-adjacent pair."""

    def test_a_pair_across_a_blank_line_travels_together(self) -> None:
        page, plan = _plan(["une admini-", "", "stration complète", "fin"])
        by_id = {lm.line_id: lm for lm in page.lines}
        # The link the L5 fix creates.
        assert by_id["L0"].hyphen_pair_line_id == "L2"
        # ...and the chunk that now holds both, with the blank riding along
        # rather than being dropped from every chunk.
        holding = [c for c in plan.chunks if "L0" in c.line_ids][0]
        assert holding.line_ids == ["L0", "L1", "L2"]
        assert plan.hyphen_splits == []

    def test_the_blank_is_not_lost_from_the_plan(self) -> None:
        page, plan = _plan(["une admini-", "", "stration"])
        assert_every_line_is_in_exactly_one_chunk(page, plan)

    def test_a_non_adjacent_pair_the_cap_cannot_hold_is_severed(self) -> None:
        """Cap 2 cannot fit L0+blank+L2, so the pair must be CUT — and the
        cut recorded. Before the fix the pair was neither held nor cut."""
        page, plan = _plan(["une admini-", "", "stration"], cap=2)
        by_id = {lm.line_id: lm for lm in page.lines}
        assert [(s.tail_line_id, s.head_line_id) for s in plan.hyphen_splits] == [
            ("L0", "L2")
        ]
        assert by_id["L0"].hyphen_pair_line_id is None
        assert_no_live_link_crosses_a_chunk(page, plan)


class TestWhatMustNotBeSevered:
    def test_a_cross_page_partner_is_left_alone(self) -> None:
        """A pointer to a line this page does not hold is a CROSS-PAGE pair,
        owned by the reconciler's cross-page join (L3). The planner must not
        sever it just because it cannot see the far side — that would undo
        the join and freeze the far member on its OCR text."""
        page = _page(["une admini-"])
        _assign_hyphen_roles(page.lines)
        # The shape link_cross_page_hyphens produces: a pointer off-page.
        page.lines[0].hyphen_pair_line_id = "P2_L0"
        page.lines[0].hyphen_pair_page_id = "P2"
        plan = plan_page(
            page,
            "d1",
            ChunkPlannerConfig(max_lines_per_request=5),
            force_granularity=ChunkGranularity.LINE,
        )
        assert plan.hyphen_splits == []
        assert page.lines[0].hyphen_pair_line_id == "P2_L0"

    def test_a_pointer_to_an_earlier_line_is_not_followed(self) -> None:
        """A backwards pointer is not a forward continuation. Following it
        would loop; severing it would destroy a link this planner does not
        understand. Leave it, and let the symmetry invariant complain."""
        page = _page(["admini-", "stration"])
        _assign_hyphen_roles(page.lines)
        page.lines[1].hyphen_pair_line_id = "L0"  # backwards
        page.lines[1].hyphen_role = page.lines[0].hyphen_role  # PART1-ish
        plan = plan_page(
            page,
            "d1",
            ChunkPlannerConfig(max_lines_per_request=5),
            force_granularity=ChunkGranularity.LINE,
        )
        assert_every_line_is_in_exactly_one_chunk(page, plan)


# ---------------------------------------------------------------------------
# The absorbed predicate's cases, restated as reach questions
# ---------------------------------------------------------------------------


class TestTheWindowReachesForItsWholeUnit:
    """``_unit_reach`` replaced ``should_stay_in_same_chunk``, whose three
    cases are kept here because they are still the right questions — asked of
    a window rather than of a pair, which is the level that decides anything.

    It was the third formulation of "who is my partner?" that S1 left
    standing, with exactly one production caller. Absorbing it retires it.
    """

    @staticmethod
    def _reach(texts: list[str], start: int, end: int) -> int:
        from saknussemm.core.planner import _unit_reach

        page = _page(texts)
        _assign_hyphen_roles(page.lines)
        link_hyphen_pairs(page.lines, PairingPolicy(geometric_checks=False))
        index_by_id = {lm.line_id: i for i, lm in enumerate(page.lines)}
        return _unit_reach(page.lines, index_by_id, start, end)

    def test_a_linked_pair_pulls_the_window_open(self) -> None:
        # Window holds L0 only; its partner is L1, so the reach is 2.
        assert self._reach(["por-", "te", "autre"], 0, 1) == 2

    def test_unrelated_lines_do_not(self) -> None:
        assert self._reach(["Bonjour monde.", "Autre ligne."], 0, 1) == 1

    def test_a_pair_already_whole_asks_for_nothing(self) -> None:
        # Both members inside: nothing leaves the window.
        assert self._reach(["por-", "te", "autre"], 0, 2) == 2

    def test_a_non_adjacent_partner_pulls_the_window_open_further(self) -> None:
        """The case the pairwise predicate could not express at all, and the
        one that made this a defect rather than a tidy-up."""
        assert self._reach(["por-", "", "te", "autre"], 0, 1) == 3

    def test_a_link_leaving_from_an_earlier_line_is_seen(self) -> None:
        """The pairwise predicate only ever looked at the window's LAST line.
        Here the link leaves from the FIRST one, over a blank."""
        assert self._reach(["por-", "", "te", "autre"], 0, 2) == 3

    def test_a_partner_behind_the_window_is_not_chased(self) -> None:
        page = _page(["por-", "te", "autre"])
        _assign_hyphen_roles(page.lines)
        link_hyphen_pairs(page.lines, PairingPolicy(geometric_checks=False))
        from saknussemm.core.planner import _unit_reach

        index_by_id = {lm.line_id: i for i, lm in enumerate(page.lines)}
        # Asking about a window that STARTS after the PART1: the link points
        # backwards from here and is none of this window's business.
        assert _unit_reach(page.lines, index_by_id, 1, 2) == 2

    def test_a_cross_page_partner_is_not_chased(self) -> None:
        page = _page(["por-"])
        _assign_hyphen_roles(page.lines)
        page.lines[0].hyphen_pair_line_id = "P2_L0"
        page.lines[0].hyphen_pair_page_id = "P2"
        from saknussemm.core.planner import _unit_reach

        assert _unit_reach(page.lines, {"L0": 0}, 0, 1) == 1


# ---------------------------------------------------------------------------
# The image-cap batcher must not dissolve a unit it can only partly see (L7)
# ---------------------------------------------------------------------------


class TestTheImageCapBatcherKeepsVisibleMembersTogether:
    """A vision producer crops every line it is sent, so a chunk's line count
    IS its image count and providers cap that per call. The batcher slices the
    chunk — which means "leave this unit alone" is not one of its options.

    Handed only COMPLETE units, it treated every member of an incomplete one
    as a singleton and could put a pair in two different calls. Two shapes
    reach it: a group whose last pointer dangles, and a group continuing onto
    another page whose members here still belong in one call.
    """

    @staticmethod
    def _lines(spec: dict[str, tuple[str, str | None, str | None]]):
        """Manifests from ``line_id -> (role, pair_id, forward_id)``.

        Spelled out rather than inferred: a PART1 carries its forward link in
        the PAIR slot and a BOTH in the FORWARD slot ("forward" names the
        slot, not the direction), and a fixture that gets that wrong builds
        lines the batcher skips for having role NONE — passing for a reason
        that has nothing to do with what is being tested.
        """
        from saknussemm.core.schemas import HyphenRole

        out: dict[str, LineManifest] = {}
        for index, (line_id, (role, pair, forward)) in enumerate(spec.items()):
            out[line_id] = LineManifest(
                line_id=line_id,
                page_id="P1",
                block_id="B1",
                line_order_global=index,
                line_order_in_block=index,
                coords=Coords(hpos=0, vpos=index * 40, width=300, height=30),
                ocr_text=f"mot{index}-",
                hyphen_role=HyphenRole(role),
                hyphen_pair_line_id=pair,
                hyphen_forward_pair_id=forward,
            )
        return out

    def _batches(self, line_by_id, cap: int) -> list[list[str]]:
        from saknussemm.core.batching import _split_for_image_cap
        from saknussemm.core.schemas import (
            ChunkGranularity,
            ChunkRequest,
            ModelCapabilities,
        )

        class _Capped:
            wants_geometry = False
            wants_image = True
            capabilities = ModelCapabilities(max_images=cap)

            async def produce(self, payload, *, options):  # pragma: no cover
                raise AssertionError("not called")

        class _Null:
            def on_event(self, *a, **k):
                pass

        producer = _Capped()
        chunk = ChunkRequest(
            chunk_id="c0",
            document_id="d",
            page_id="P1",
            granularity=ChunkGranularity.LINE,
            line_ids=list(line_by_id),
        )
        routed = _split_for_image_cap(routed=[(chunk, producer)], line_by_id=line_by_id)
        return [list(c.line_ids) for c, _p in routed]

    def test_a_dangling_chain_is_not_dissolved_into_singletons(self) -> None:
        """L0-L1-L2 is a chain whose last pointer dangles, so the group is
        INCOMPLETE — and its three members are still one unit as far as this
        page can see. With a cap of 3 they must share a call."""
        # Two plain lines FIRST, so the unit does not happen to start on a
        # batch boundary: without them a cap of 3 groups L0-L1-L2 by accident
        # and the test passes on the broken code.
        lines = self._lines(
            {
                "P0": ("none", None, None),
                "P1": ("none", None, None),
                "L0": ("HypPart1", "L1", None),
                "L1": ("HypBoth", "L0", "L2"),
                "L2": ("HypBoth", "L1", "L99"),  # dangles
                "P2": ("none", None, None),
            }
        )
        batches = self._batches(lines, cap=3)
        holding = [b for b in batches if "L0" in b][0]
        assert set(holding) >= {"L0", "L1", "L2"}, (
            f"the chain was split across calls: {batches}"
        )

    def test_a_unit_bigger_than_the_cap_fails_loudly(self) -> None:
        """The honest outcome when a unit cannot fit: refuse, with the reason.
        Before the fix an incomplete unit slipped past this check entirely and
        was quietly split — the failure mode the error exists to prevent."""
        from saknussemm.errors import ConfigurationError

        lines = self._lines(
            {
                "L0": ("HypPart1", "L1", None),
                "L1": ("HypBoth", "L0", "L2"),
                "L2": ("HypBoth", "L1", "L99"),  # dangling: group incomplete
                "L3": ("none", None, None),
            }
        )
        with pytest.raises(ConfigurationError, match="cannot be split across calls"):
            self._batches(lines, cap=2)

    def test_a_cross_page_units_local_members_stay_together(self) -> None:
        """The far member is on another page and cannot be here. The two that
        ARE here still belong in one call."""
        lines = self._lines(
            {
                "P0": ("none", None, None),
                "P1": ("none", None, None),
                "L0": ("HypPart1", "L1", None),
                "L1": ("HypBoth", "L0", "L2"),
                "L2": ("HypBoth", "L1", None),
                "P2": ("none", None, None),
            }
        )
        lines["L2"].hyphen_forward_pair_id = "P2_L0"
        lines["L2"].hyphen_forward_pair_page_id = "P2"
        batches = self._batches(lines, cap=3)
        holding = [b for b in batches if "L0" in b][0]
        assert set(holding) >= {"L0", "L1", "L2"}, (
            f"a cross-page unit's local members were split: {batches}"
        )

    def test_plain_lines_are_batched_freely(self) -> None:
        """No units, so the cap is the only constraint — the fix must not make
        the batcher conservative where it has nothing to protect."""
        lines = self._lines({f"L{i}": ("none", None, None) for i in range(5)})
        batches = self._batches(lines, cap=2)
        assert [len(b) for b in batches] == [2, 2, 1]
