"""A hyphen link must agree with itself from both ends.

Every consumer picks its own end of a link. The reconciler walks forward
from the tail; the router and the fallback walk the whole unit in both
directions; the payload now asks each line about the direction it faces.
They agree only because the two slots are written as a matching pair —
nothing checks it.

    if A says its word continues onto B, B must say its word is continued
    from A, and vice versa.

An asymmetric link is not a cosmetic inconsistency. A tail that points at a
head which does not point back is reconciled from one side and treated as
unrelated from the other: the joined word is rewritten on one line and kept
verbatim on the next — the exact corruption the hyphen machinery exists to
prevent, arrived at through the bookkeeping instead of through the model.

Run over the generated corpus (chains, seams, every structure the generator
encodes) and both real fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings

from lidenbrock.core.identity import LineRef, line_ref
from lidenbrock.core.pairing import backward_partner_ref, forward_partner_ref
from lidenbrock.core.schemas import HyphenRole, LineManifest, PageManifest

from tests._alto_gen import rich_alto_documents
from tests.test_properties_hypothesis import _write_tmp

from tests._pipeline_harness import EXAMPLES as _EXAMPLES


def assert_links_are_symmetric(pages: list[PageManifest]) -> None:
    """The invariant, over any parsed document."""
    by_ref: dict[LineRef, LineManifest] = {
        line_ref(lm): lm for page in pages for lm in page.lines
    }

    for ref, lm in by_ref.items():
        forward = forward_partner_ref(lm)
        if forward is not None and forward in by_ref:
            head = by_ref[forward]
            back = backward_partner_ref(head)
            assert back == ref, (
                f"{ref} says its word continues onto {forward}, but {forward} "
                f"says it is continued from {back}. One end of this link will "
                "be reconciled and the other treated as unrelated."
            )

        backward = backward_partner_ref(lm)
        if backward is not None and backward in by_ref:
            tail = by_ref[backward]
            fwd = forward_partner_ref(tail)
            assert fwd == ref, (
                f"{ref} says it is continued from {backward}, but {backward} "
                f"says its word continues onto {fwd}."
            )


def assert_roles_match_their_links(pages: list[PageManifest]) -> None:
    """A weaker companion: a line that carries a link must carry the role
    that makes the link readable.

    ``forward_partner_ref`` returns nothing for a PART2, so a PART2 holding a
    forward link is a link no consumer can see — it exists in the fields and
    not in the document.
    """
    for page in pages:
        for lm in page.lines:
            if lm.hyphen_forward_pair_id:
                assert lm.hyphen_role is HyphenRole.BOTH, (
                    f"{lm.line_id}: holds a FORWARD-slot link while role is "
                    f"{lm.hyphen_role.value}. Only BOTH reads that slot, so "
                    "this link is invisible to every consumer."
                )
            if lm.hyphen_role is HyphenRole.NONE:
                assert not lm.hyphen_pair_line_id, (
                    f"{lm.line_id}: role NONE but carries a pair link — no "
                    "consumer will follow it."
                )


def _pages_of(path: Path) -> list[PageManifest]:
    from lidenbrock.formats.alto.parser import build_document_manifest

    return list(build_document_manifest([(path, path.name)]).pages)


# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(doc_and_roles=rich_alto_documents())
def test_links_are_symmetric_on_generated_documents(doc_and_roles) -> None:
    doc, _ = doc_and_roles
    path = _write_tmp(doc)
    try:
        pages = _pages_of(path)
        assert_links_are_symmetric(pages)
        assert_roles_match_their_links(pages)
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize("name", ["sample.xml", "X0000002.xml"])
def test_links_are_symmetric_on_the_real_fixtures(name: str) -> None:
    pages = _pages_of(_EXAMPLES / name)
    assert_links_are_symmetric(pages)
    assert_roles_match_their_links(pages)


def test_a_multi_file_document_keeps_its_seam_symmetric(tmp_path: Path) -> None:
    """The cross-page seam is where the two slots are written by different
    passes — ``link_cross_page_hyphens`` rather than ``link_hyphen_pairs``."""
    from lidenbrock.formats.alto.parser import build_document_manifest

    alto = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"><Layout>'
        '<Page ID="{pid}" WIDTH="800" HEIGHT="600">'
        '<PrintSpace HPOS="0" VPOS="0" WIDTH="800" HEIGHT="600">'
        '<TextBlock ID="TB{pid}" HPOS="0" VPOS="0" WIDTH="800" HEIGHT="100">'
        '<TextLine ID="{lid}" HPOS="0" VPOS="0" WIDTH="800" HEIGHT="20">'
        '<String ID="S{lid}" CONTENT="{c}" HPOS="0" VPOS="0" WIDTH="700"'
        ' HEIGHT="20"/></TextLine>'
        "</TextBlock></PrintSpace></Page></Layout></alto>"
    )
    f1 = tmp_path / "p1.xml"
    f2 = tmp_path / "p2.xml"
    f1.write_text(alto.format(pid="PAGE1", lid="L1", c="administra-"), "utf-8")
    f2.write_text(alto.format(pid="PAGE2", lid="L2", c="tif du conseil"), "utf-8")

    pages = list(build_document_manifest([(f1, "p1.xml"), (f2, "p2.xml")]).pages)
    assert_links_are_symmetric(pages)
    assert_roles_match_their_links(pages)
    # Precondition: the seam actually linked, or the assertions above are
    # vacuous.
    tail = pages[0].lines[0]
    assert forward_partner_ref(tail) == LineRef(page_id="PAGE2", line_id="L2")


def test_the_invariant_catches_a_one_sided_link() -> None:
    """Guard the guard."""
    from lidenbrock.core.schemas import Coords

    def _line(lid: str, **kw) -> LineManifest:
        return LineManifest(
            line_id=lid,
            page_id="P1",
            block_id="B1",
            line_order_global=int(lid[-1]),
            line_order_in_block=int(lid[-1]),
            coords=Coords(hpos=0, vpos=0, width=10, height=10),
            ocr_text="x",
            **kw,
        )

    tail = _line("L1", hyphen_role=HyphenRole.PART1, hyphen_pair_line_id="L2")
    head = _line("L2", hyphen_role=HyphenRole.PART2)  # points nowhere back
    page = PageManifest(
        page_id="P1",
        page_index=0,
        source_file="f.xml",
        page_width=10,
        page_height=10,
        blocks=[],
        lines=[tail, head],
    )
    with pytest.raises(AssertionError, match="says it is continued from"):
        assert_links_are_symmetric([page])
