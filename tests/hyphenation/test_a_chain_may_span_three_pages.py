"""A hyphen chain across three pages, which the suite had never built.

Measured on 2026-08-17 by instrumenting ``derive_hyphen_groups`` for a whole
suite run — 1604 tests, every call recorded: **``max pages = 2``**. Every
multi-page test in this repository uses exactly two pages, which is the
*minimal* multi-page case, and it has one seam. So no test had ever produced
a group whose members sit on three pages, and ``spans_pages`` is a boolean —
a two-page group and a three-page group are indistinguishable through it.

That leaves one question open that the whole suite could not answer: does the
union-find in :func:`~saknussemm.core.units.derive_hyphen_groups` join across
*two* seams, or does it stop at one and hand back two overlapping pairs? The
answer, measured before this file existed, is that it joins — one group, three
members, three pages. **Nothing was broken**, so this is a regression guard,
which is worth saying plainly: a test file that reads like a bug report and
contains no bug teaches the next reader the wrong thing.

Here rather than in ``tests/`` because the subject is the hyphen unit and
`S1` will look for it here — the net in ``test_the_net_is_bounded.py`` caught
the first placement, which is the net working.

The same measurement refuted a neighbouring claim, recorded because the shape
recurs: the audit listed *a chain of four* among the property generator's
structural impossibilities. It is one — and the suite reaches chains of up to
**twelve members, 476 times**, through hand-built cases and the real corpora.
Teaching the generator to draw one would have added nothing. A gap in a
generator is not a gap in coverage, and the difference is one measurement
away.
"""

from __future__ import annotations

from saknussemm.core.units import derive_hyphen_groups, split_forward_link
from saknussemm.formats.loader import build_document_manifest

from tests._alto_pages import THREE_PAGE_CHAIN, written


def _pool() -> list:
    path = written(THREE_PAGE_CHAIN)
    manifest = build_document_manifest([(path, path.name)])
    return [line for page in manifest.pages for line in page.lines]


def test_the_chain_derives_as_one_group_of_three_on_three_pages() -> None:
    groups = derive_hyphen_groups(_pool())
    assert len(groups) == 1, (
        f"expected ONE group, got {len(groups)}: "
        f"{[(len(g.members), g.spans_pages) for g in groups]}. A derivation "
        "that stops at the first seam shows up here as two groups of two."
    )
    group = groups[0]
    assert len(group.members) == 3, f"members: {group.members}"
    assert group.spans_pages
    assert len({ref.page_id for ref in group.members}) == 3, (
        f"the members sit on {len({r.page_id for r in group.members})} page(s): "
        f"{group.members}. The point of the fixture is three."
    )


def test_severing_one_seam_leaves_two_members_together() -> None:
    """Guard the guard, and a badly aimed mutation worth recording.

    The first attempt at this proof cleared the tail's forward fields by hand
    and the chain still derived as one group of three — which read exactly
    like a vacuous guard. It was a bad mutation, not a bad guard: the seam is
    encoded **twice**, forward on ``P2_L0.hyphen_forward_pair_id`` and
    backward on ``P3_L0.hyphen_pair_line_id``, and the derivation unions on
    both, so a one-sided clear is invisible to it.

    ``split_forward_link`` is the only operation that severs a link, and it
    clears both sides. Through it, the group becomes two — which is what says
    the assertion above is load-bearing.

    A side effect worth naming: nothing detects a *one-sided* pointer. Two
    encodings that disagree are silently reconciled by taking their union.
    That is the conservative direction — members stay together — and it is
    also why `S1` making the groups authoritative is the fix rather than a
    check here.
    """
    pool = _pool()
    by_ref = {(line.page_id, line.line_id): line for line in pool}
    assert len(derive_hyphen_groups(pool)) == 1, "the fixture stopped chaining"

    split_forward_link(by_ref[("P2", "P2_L0")], by_ref[("P3", "P3_L0")])

    groups = derive_hyphen_groups(pool)
    sizes = sorted(len(group.members) for group in groups)
    assert sizes == [2], (
        f"after severing the second seam the derivation reports groups of "
        f"{sizes}. Expected the first pair to survive alone: P1→P2 is "
        "untouched, and P3's line is now linked to nothing."
    )
