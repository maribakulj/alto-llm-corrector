"""What the payload tells the model must be true of the manifest.

``enrich_chunk_lines`` builds the per-line hints the producer sees. Two of
them are assertions about the document, not hints:

    ``hyphen_join_with_next``  your word continues onto another line
    ``hyphen_join_with_prev``  another line's word continues onto you

They were set from the ROLE alone. A line's role is read off its own text —
a trailing break mark makes it PART1 — while the LINK is established in a
second pass that can legitimately fail to find a partner: the partner is on
a page the run does not have, an empty page severed the seam (fixed
2026-07-27), the pairing policy refused the candidate. The role then says
PART1 and there is nobody there.

So the engine told the model "this word continues onto the next line" about
a line whose continuation does not exist. The model is being asked to leave
a word unfinished for a partner that will never arrive, and the reconciler
that would have caught an incoherent join never runs, because there is no
pair. Nothing downstream can detect it — the payload is not compared against
anything.

The invariant is the obvious one, and it is only expressible now that both
directions have a name (``backward_partner_ref`` landed with the cross-page
ownership fix):

    the payload claims a forward join iff the line HAS a forward partner,
    and a backward join iff it has a backward one.
"""

from __future__ import annotations

import pytest

from lidenbrock.core.hyphenation import enrich_chunk_lines
from lidenbrock.core.pairing import backward_partner_ref, forward_partner_ref
from lidenbrock.core.schemas import Coords, HyphenRole, LineManifest

from tests._paths import EXAMPLES


def _line(
    line_id: str,
    text: str,
    *,
    role: HyphenRole = HyphenRole.NONE,
    pair: str | None = None,
    forward: str | None = None,
) -> LineManifest:
    return LineManifest(
        line_id=line_id,
        page_id="P1",
        block_id="B1",
        line_order_global=int(line_id[-1]),
        line_order_in_block=int(line_id[-1]),
        coords=Coords(hpos=0, vpos=0, width=100, height=10),
        ocr_text=text,
        hyphen_role=role,
        hyphen_pair_line_id=pair,
        hyphen_forward_pair_id=forward,
    )


def assert_payload_matches_the_manifest(contexts, lines: list[LineManifest]) -> None:
    """The invariant, over any enrichment result."""
    by_id = {lm.line_id: lm for lm in lines}
    for ctx in contexts:
        lm = by_id[ctx.line_id]
        has_forward = forward_partner_ref(lm) is not None
        has_backward = backward_partner_ref(lm) is not None

        assert bool(ctx.hyphen_join_with_next) == has_forward, (
            f"{lm.line_id}: payload says join_with_next="
            f"{ctx.hyphen_join_with_next!r} but the line "
            f"{'has' if has_forward else 'has NO'} forward partner. The model "
            "is being told about a continuation that does not exist."
        )
        assert bool(ctx.hyphen_join_with_prev) == has_backward, (
            f"{lm.line_id}: payload says join_with_prev="
            f"{ctx.hyphen_join_with_prev!r} but the line "
            f"{'has' if has_backward else 'has NO'} backward partner."
        )


def _enrich(lines: list[LineManifest]):
    return enrich_chunk_lines(lines, {lm.line_id: lm for lm in lines})


# ---------------------------------------------------------------------------
# Linked pairs — the payload must keep saying what it always said
# ---------------------------------------------------------------------------


def test_a_linked_pair_still_announces_both_directions() -> None:
    tail = _line("L1", "administra-", role=HyphenRole.PART1, pair="L2")
    head = _line("L2", "tif du conseil", role=HyphenRole.PART2, pair="L1")
    contexts = _enrich([tail, head])

    assert_payload_matches_the_manifest(contexts, [tail, head])
    assert contexts[0].hyphen_join_with_next is True
    assert not contexts[0].hyphen_join_with_prev
    assert contexts[1].hyphen_join_with_prev is True


def test_a_linked_chain_announces_both_on_its_middle() -> None:
    a = _line("L1", "in-", role=HyphenRole.PART1, pair="L2")
    b = _line("L2", "ter-", role=HyphenRole.BOTH, pair="L1", forward="L3")
    c = _line("L3", "vention", role=HyphenRole.PART2, pair="L2")
    contexts = _enrich([a, b, c])

    assert_payload_matches_the_manifest(contexts, [a, b, c])
    assert contexts[1].hyphen_join_with_prev is True
    assert contexts[1].hyphen_join_with_next is True


def test_an_ordinary_line_announces_neither() -> None:
    plain = _line("L1", "le conseil municipal")
    contexts = _enrich([plain])
    assert_payload_matches_the_manifest(contexts, [plain])


# ---------------------------------------------------------------------------
# Orphans — the payload must stop asserting a partner that is not there
# ---------------------------------------------------------------------------


def test_an_orphan_part1_does_not_promise_a_continuation() -> None:
    """The defect. Its role says PART1 because its text ends in a dash; the
    linking pass found nobody. Announcing a join asks the model to leave a
    word unfinished for a partner that will never arrive."""
    orphan = _line("L1", "administra-", role=HyphenRole.PART1, pair=None)
    contexts = _enrich([orphan])

    assert_payload_matches_the_manifest(contexts, [orphan])
    assert not contexts[0].hyphen_join_with_next


def test_an_orphan_part2_does_not_claim_an_antecedent() -> None:
    orphan = _line("L1", "tif du conseil", role=HyphenRole.PART2, pair=None)
    contexts = _enrich([orphan])

    assert_payload_matches_the_manifest(contexts, [orphan])
    assert not contexts[0].hyphen_join_with_prev


@pytest.mark.parametrize(
    ("pair", "forward"),
    [(None, "L3"), ("L0", None), (None, None)],
)
def test_a_half_linked_both_announces_only_the_side_it_has(
    pair: str | None, forward: str | None
) -> None:
    """A BOTH line has two independent links and can lose either one."""
    line = _line("L2", "ter-", role=HyphenRole.BOTH, pair=pair, forward=forward)
    contexts = _enrich([line])

    assert_payload_matches_the_manifest(contexts, [line])
    assert bool(contexts[0].hyphen_join_with_prev) == (pair is not None)
    assert bool(contexts[0].hyphen_join_with_next) == (forward is not None)


def test_an_orphan_is_still_flagged_as_a_hyphen_candidate() -> None:
    """Dropping the false promise must not drop the true information.

    The line does end in a break mark, and the model still needs to know
    that so it does not read the dash as punctuation and 'fix' it.
    """
    orphan = _line("L1", "administra-", role=HyphenRole.PART1, pair=None)
    ctx = _enrich([orphan])[0]

    assert ctx.hyphen_candidate is True
    assert ctx.hyphenation_role == HyphenRole.PART1.value


def test_the_invariant_catches_a_false_promise() -> None:
    """Guard the guard: hand it a context that lies and it must fail."""
    from lidenbrock.core.schemas import LineContext

    orphan = _line("L1", "administra-", role=HyphenRole.PART1, pair=None)
    lying = [
        LineContext(
            line_id="L1",
            ocr_text="administra-",
            hyphenation_role="HypPart1",
            hyphen_candidate=True,
            hyphen_join_with_next=True,
        )
    ]
    with pytest.raises(AssertionError, match="continuation that does not exist"):
        assert_payload_matches_the_manifest(lying, [orphan])


# ---------------------------------------------------------------------------
# What actually reaches the provider
# ---------------------------------------------------------------------------


def test_a_linked_pairs_payload_is_byte_identical_to_before() -> None:
    """The producer serialises with ``exclude_none=True``, so a linked pair's
    payload must be unchanged: the flags are still ``True``, present, same
    keys. Only the false promise disappears."""
    tail = _line("L1", "administra-", role=HyphenRole.PART1, pair="L2")
    head = _line("L2", "tif du conseil", role=HyphenRole.PART2, pair="L1")
    payloads = [c.model_dump(exclude_none=True) for c in _enrich([tail, head])]

    assert payloads[0]["hyphen_join_with_next"] is True
    assert "hyphen_join_with_prev" not in payloads[0]
    assert payloads[1]["hyphen_join_with_prev"] is True
    assert "hyphen_join_with_next" not in payloads[1]


def test_an_orphans_payload_simply_omits_the_claim() -> None:
    """``exclude_none`` drops the key entirely rather than sending
    ``false`` — the model is not told a continuation exists, and is not told
    one is impossible either. It is not told."""
    orphan = _line("L1", "administra-", role=HyphenRole.PART1, pair=None)
    payload = _enrich([orphan])[0].model_dump(exclude_none=True)

    assert "hyphen_join_with_next" not in payload
    assert payload["hyphen_candidate"] is True
    assert payload["hyphenation_role"] == "HypPart1"


def test_a_subs_authority_never_travels_without_its_link() -> None:
    """``forward_join_candidate`` is the SUBS_CONTENT the model should join
    towards. Sending it for a link that does not exist would hand over a
    target word with nothing to join to it."""
    orphan = _line("L1", "administra-", role=HyphenRole.PART1, pair=None)
    orphan.hyphen_subs_content = "administratif"
    payload = _enrich([orphan])[0].model_dump(exclude_none=True)

    assert "forward_join_candidate" not in payload


def test_a_both_line_offers_the_forward_slots_authority() -> None:
    """A BOTH line's two links carry two different SUBS_CONTENTs; the forward
    candidate must come from the FORWARD slot, the same role→slot map the
    refs use."""
    both = _line("L2", "ter-", role=HyphenRole.BOTH, pair="L1", forward="L3")
    both.hyphen_subs_content = "hiver"
    both.hyphen_forward_subs_content = "intervention"
    ctx = _enrich([both])[0]

    assert ctx.backward_join_candidate == "hiver"
    assert ctx.forward_join_candidate == "intervention"


@pytest.mark.parametrize("name", ["sample.xml", "X0000002.xml"])
def test_the_invariant_holds_on_the_real_fixtures(name: str) -> None:
    """Hand-built manifests can miss a shape the parser really produces."""

    from lidenbrock.formats.alto.parser import parse_alto_file

    path = EXAMPLES / name
    pages, _ = parse_alto_file(path, path.name)
    for page in pages:
        by_id = {lm.line_id: lm for lm in page.lines}
        assert_payload_matches_the_manifest(
            enrich_chunk_lines(page.lines, by_id), page.lines
        )


# ---------------------------------------------------------------------------
# The run admits the breaks it could not pair
# ---------------------------------------------------------------------------


def test_the_report_counts_a_break_with_no_partner() -> None:
    """Refusing to pair is a decision, and it was made in silence.

    ``PairingPolicy.can_pair`` returning False just `continue`s; a partner on
    an absent page, or a dangling pointer, are equally quiet. The line still
    ends mid-word, is corrected alone, and never reaches the reconciler — so
    its pair-drift guards never run. A host reading "0 fallback" had no way
    to learn any of that happened.
    """

    from lidenbrock.core.pairing import unpaired_break_refs
    from lidenbrock.formats.alto.parser import build_document_manifest

    path = EXAMPLES / "X0000002.xml"
    doc = build_document_manifest([(path, path.name)])

    orphans = unpaired_break_refs(doc.pages)
    assert orphans, "the real fixture is expected to carry at least one"
    assert all(
        doc_line.hyphen_role is not HyphenRole.NONE
        for ref in orphans
        for page in doc.pages
        for doc_line in page.lines
        if doc_line.line_id == ref.line_id and doc_line.page_id == ref.page_id
    ), "only a line announcing a break can be an unpaired break"


def test_a_fully_paired_document_reports_nothing() -> None:
    """The counter must stay quiet when there is nothing to admit."""

    from lidenbrock.core.pairing import unpaired_break_refs
    from lidenbrock.formats.alto.parser import build_document_manifest

    path = EXAMPLES / "sample.xml"
    doc = build_document_manifest([(path, path.name)])
    assert unpaired_break_refs(doc.pages) == []
