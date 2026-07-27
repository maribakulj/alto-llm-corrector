"""ADR-010 (first slice) — ONE derivation of hyphen groups.

Cross-validated against the rich generator: every structure the
generator encodes (pair, chain, cross-page seam) must surface as
exactly one group with the right members in the right order — and
nothing else may group.
"""

from __future__ import annotations

from hypothesis import given, settings

from corrigenda.core.identity import LineRef
from corrigenda.core.units import derive_hyphen_groups, hyphen_group_by_line
from corrigenda.formats.alto.parser import build_document_manifest

from tests._alto_gen import rich_alto_documents
from tests.test_properties_hypothesis import _write_tmp


def _all_lines(path):
    doc = build_document_manifest([(path, path.name)])
    return [lm for page in doc.pages for lm in page.lines]


@settings(max_examples=40, deadline=None)
@given(doc_and_roles=rich_alto_documents())
def test_groups_match_the_generated_structures(doc_and_roles) -> None:
    doc, expected = doc_and_roles
    path = _write_tmp(doc)
    try:
        lines = _all_lines(path)
        groups = derive_hyphen_groups(lines)
        by_line = hyphen_group_by_line(groups)
        role_of = expected  # line_id → generated role
        ref_of = {
            lm.line_id: LineRef(page_id=lm.page_id, line_id=lm.line_id) for lm in lines
        }

        # 1. Membership is exactly the non-plain lines.
        grouped_ids = {ref.line_id for ref in by_line}
        expected_ids = {lid for lid, role in role_of.items() if role != "plain"}
        assert grouped_ids == expected_ids

        # 2. Every group is one generated structure, members in reading
        #    order: pair = 2 members, chain = 3 (PART1, BOTH, PART2),
        #    seam = 2 members spanning both pages.
        for group in groups:
            roles = [role_of[m.line_id] for m in group.members]
            assert roles in (
                ["part1", "part2"],
                ["part1", "both", "part2"],
                ["seam1", "seam2"],
            ), f"unexpected group shape: {roles}"
            assert group.spans_pages == (roles == ["seam1", "seam2"])
            # The generator emits only explicit SUBS hyphenation.
            assert group.explicit

        # 3. Groups partition their members (no line in two groups).
        seen: set[LineRef] = set()
        for group in groups:
            for member in group.members:
                assert member not in seen
                seen.add(member)
        assert seen == {ref_of[lid] for lid in expected_ids}
    finally:
        path.unlink(missing_ok=True)


@settings(max_examples=25, deadline=None)
@given(doc_and_roles=rich_alto_documents())
def test_page_local_derivation_drops_the_severed_seam(doc_and_roles) -> None:
    """A page-scoped consumer (the chunk planner) derives groups from ONE
    page's lines: a cross-page pair contributes only its on-page member,
    which must NOT form a group — the join is reconciled, never planned."""
    doc, expected = doc_and_roles
    path = _write_tmp(doc)
    try:
        manifest = build_document_manifest([(path, path.name)])
        for page in manifest.pages:
            for group in derive_hyphen_groups(page.lines):
                roles = [expected[m.line_id] for m in group.members]
                assert "seam1" not in roles and "seam2" not in roles, (
                    "a severed cross-page pair must not group page-locally"
                )
                assert not group.spans_pages
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# split_forward_link — the unit SPLIT operation (ADR-010, slice 2)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from corrigenda.core.schemas import HyphenRole, HyphenSplit  # noqa: E402
from corrigenda.core.units import split_forward_link  # noqa: E402

# PART1 → BOTH → PART2 chain: 'porte' split over L0/L1, 'fondation' over
# L1/L2 — every role the split has to migrate, with explicit SUBS.
_CHAIN_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"><Layout>
<Page ID="P1" WIDTH="1000" HEIGHT="1000">
<PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextLine ID="L0" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20">
<String ID="S0" CONTENT="por" HPOS="10" VPOS="10" WIDTH="60" HEIGHT="20" \
SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/><HYP CONTENT="-"/></TextLine>
<TextLine ID="L1" HPOS="10" VPOS="40" WIDTH="900" HEIGHT="20">
<String ID="S1" CONTENT="te" HPOS="10" VPOS="40" WIDTH="40" HEIGHT="20" \
SUBS_TYPE="HypPart2" SUBS_CONTENT="porte"/>
<String ID="S2" CONTENT="fon" HPOS="60" VPOS="40" WIDTH="60" HEIGHT="20" \
SUBS_TYPE="HypPart1" SUBS_CONTENT="fondation"/><HYP CONTENT="-"/></TextLine>
<TextLine ID="L2" HPOS="10" VPOS="70" WIDTH="900" HEIGHT="20">
<String ID="S3" CONTENT="dation" HPOS="10" VPOS="70" WIDTH="90" HEIGHT="20" \
SUBS_TYPE="HypPart2" SUBS_CONTENT="fondation"/></TextLine>
</TextBlock></PrintSpace></Page></Layout></alto>"""


def _chain_lines():
    path = _write_tmp(_CHAIN_ALTO)
    try:
        return _all_lines(path)
    finally:
        path.unlink(missing_ok=True)


def test_split_severs_at_the_both_tail() -> None:
    """Cut L1→L2: the BOTH tail keeps its backward pair (it is still
    PART2 of 'porte'), the PART2 head becomes a plain line."""
    lines = _chain_lines()
    l0, l1, l2 = lines
    record = split_forward_link(l1, l2)
    assert record == HyphenSplit(page_id="P1", tail_line_id="L1", head_line_id="L2")
    assert l1.hyphen_role is HyphenRole.PART2
    assert l1.hyphen_pair_line_id == "L0"
    assert l1.hyphen_subs_content == "porte"
    assert l1.hyphen_forward_pair_id is None
    assert l1.hyphen_forward_subs_content is None
    assert l2.hyphen_role is HyphenRole.NONE
    assert l2.hyphen_pair_line_id is None
    assert l2.hyphen_subs_content is None
    assert [lm.ocr_text for lm in lines] == ["por-", "tefon-", "dation"]
    groups = derive_hyphen_groups(lines)
    assert [[m.line_id for m in g.members] for g in groups] == [["L0", "L1"]]


def test_split_severs_at_the_both_head() -> None:
    """Cut L0→L1: the BOTH head becomes PART1 of ITS OWN forward word —
    the forward link/subs migrate into the plain pair fields, where
    PART1 carries them."""
    lines = _chain_lines()
    l0, l1, l2 = lines
    record = split_forward_link(l0, l1)
    assert record == HyphenSplit(page_id="P1", tail_line_id="L0", head_line_id="L1")
    assert l0.hyphen_role is HyphenRole.NONE
    assert l0.hyphen_pair_line_id is None
    assert l0.hyphen_subs_content is None
    assert l1.hyphen_role is HyphenRole.PART1
    assert l1.hyphen_pair_line_id == "L2"
    assert l1.hyphen_subs_content == "fondation"
    assert l1.hyphen_source_explicit
    assert l1.hyphen_forward_pair_id is None
    groups = derive_hyphen_groups(lines)
    assert [[m.line_id for m in g.members] for g in groups] == [["L1", "L2"]]
    assert groups[0].explicit


def test_split_of_a_plain_pair_clears_both_sides() -> None:
    """After the chain is fully severed no group remains and every line
    is plain — the conservative degenerate end state."""
    lines = _chain_lines()
    l0, l1, l2 = lines
    split_forward_link(l0, l1)
    split_forward_link(l1, l2)  # now a plain PART1→PART2 pair
    assert [lm.hyphen_role for lm in lines] == [
        HyphenRole.NONE,
        HyphenRole.NONE,
        HyphenRole.NONE,
    ]
    assert derive_hyphen_groups(lines) == ()


def test_split_refuses_an_absent_link() -> None:
    """Severing a link that is not there is an engine bug, not a no-op."""
    lines = _chain_lines()
    l0, l1, l2 = lines
    with pytest.raises(RuntimeError, match="does not continue onto"):
        split_forward_link(l0, l2)


# ---------------------------------------------------------------------------
# `complete` — is the unit I can see the WHOLE unit?
# ---------------------------------------------------------------------------
#
# A consumer that moves a unit as a whole (the router escalating to a second
# producer, the image-cap batcher) has to distinguish "this is the entire
# unit" from "this is the part of it that happens to be in front of me".
# Moving the visible half is precisely the split atomicity forbids. The
# question is answered by the one derivation that already reads the pointers;
# a caller re-reading them to ask it again is how the fifth parallel resolver
# appeared in the first place.


def test_a_wholly_resolvable_chain_is_complete() -> None:
    lines = _chain_lines()
    groups = derive_hyphen_groups(lines)
    assert groups, "fixture must produce a group"
    assert all(g.complete for g in groups)


def test_a_dangling_pointer_makes_the_group_incomplete() -> None:
    lines = _chain_lines()
    head = next(lm for lm in lines if lm.hyphen_pair_line_id)
    head.hyphen_pair_line_id = "TL_NOT_HERE"

    groups = derive_hyphen_groups(lines)
    by_line = hyphen_group_by_line(groups)
    group = by_line.get(LineRef(page_id=head.page_id, line_id=head.line_id))
    assert group is None or not group.complete


def test_a_page_scoped_derivation_marks_a_cross_page_unit_incomplete() -> None:
    """The distinction the router depends on: derived over ONE page, a unit
    that continues onto the next is incomplete — not merely absent, and not
    silently a smaller unit."""
    lines = _chain_lines()
    tail = (
        next(lm for lm in lines if lm.hyphen_forward_pair_id)
        if any(lm.hyphen_forward_pair_id for lm in lines)
        else next(lm for lm in lines if lm.hyphen_pair_line_id)
    )
    tail.hyphen_pair_page_id = "NEXT_PAGE"
    tail.hyphen_forward_pair_page_id = (
        "NEXT_PAGE" if tail.hyphen_forward_pair_id else None
    )

    groups = derive_hyphen_groups(lines)
    by_line = hyphen_group_by_line(groups)
    group = by_line.get(LineRef(page_id=tail.page_id, line_id=tail.line_id))
    assert group is None or not group.complete


def test_completeness_is_a_property_of_the_derivation_set() -> None:
    """Derived over the whole document a cross-page unit is complete; over
    one page it is not. Same pointers, different question — which is why the
    caller must not answer it from the pointers."""
    lines = _chain_lines()
    # Chain L0 -PART1-> L1 -BOTH-> L2. Move the TAIL onto a second page and
    # qualify both halves of the seam, so the unit is genuinely cross-page
    # rather than merely broken.
    _, l1, l2 = lines
    l2.page_id = "P2"
    l1.hyphen_forward_pair_page_id = "P2"
    l2.hyphen_pair_page_id = "P1"

    document_wide = derive_hyphen_groups(lines)
    spanning = [g for g in document_wide if g.spans_pages]
    assert spanning, "the seam must produce one cross-page group"
    assert all(g.complete for g in spanning), (
        "every pointer resolves when the whole document is in view"
    )

    page_only = derive_hyphen_groups([lm for lm in lines if lm.page_id == "P1"])
    by_line = hyphen_group_by_line(page_only)
    group = by_line.get(LineRef(page_id="P1", line_id=l1.line_id))
    assert group is not None, "L0-L1 still group on their own page"
    assert not group.complete, (
        "but the unit continues off-page, so what this page can see is not "
        "the whole unit — the router must not move it"
    )
