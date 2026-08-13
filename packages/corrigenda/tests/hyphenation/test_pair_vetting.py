"""Which candidate pairs are pairs at all.

Before anything is reconciled the linker has to decide that two lines
belong to one broken word, and ``PairingPolicy`` is the injectable seam
that answers it. Both failures here are silent by nature: a policy that
refuses a real pair simply stops correcting it, and nothing in the output
says so.
"""

from __future__ import annotations

from corrigenda.core.pairing import link_hyphen_pairs
from corrigenda.core.schemas import Coords, HyphenRole, LineManifest, PairingPolicy

from tests.hyphenation._lines import _line


def test_same_block_only_forbids_cross_page_even_with_reused_block_id():
    policy = PairingPolicy(same_block_only=True, geometric_checks=False)
    part1 = _line(
        "TL9", "mot-", page_id="pA", block_id="TextBlock1", role=HyphenRole.PART1
    )
    # Cross-page candidate reusing the SAME block id (both pages export
    # "TextBlock1"). The documented guarantee: cross-page pairing forbidden.
    candidate = _line(
        "TL1", "suite", page_id="pB", block_id="TextBlock1", role=HyphenRole.PART2
    )
    assert policy.can_pair(part1, candidate) is False


def test_same_block_only_still_allows_intra_block_same_page():
    policy = PairingPolicy(same_block_only=True, geometric_checks=False)
    part1 = _line("TL1", "mot-", page_id="pA", block_id="TB1", role=HyphenRole.PART1)
    candidate = _line(
        "TL2", "suite", page_id="pA", block_id="TB1", role=HyphenRole.PART2
    )
    assert policy.can_pair(part1, candidate) is True


def test_identical_boxes_are_treated_as_synthetic_geometry():
    """Block coords copied onto every line (a common lazy export) must not
    silently disable hyphen pairing."""

    def lm(lid: str) -> LineManifest:
        return LineManifest(
            line_id=lid,
            page_id="p1",
            block_id="b1",
            line_order_global=0,
            line_order_in_block=0,
            coords=Coords(hpos=0, vpos=100, width=800, height=200),
            ocr_text="mot coupe-",
        )

    part1, part2 = lm("l1"), lm("l2")
    part1.hyphen_role = HyphenRole.PART1
    link_hyphen_pairs([part1, part2])
    assert part1.hyphen_pair_line_id == "l2"
