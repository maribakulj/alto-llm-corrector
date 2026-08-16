"""The same page in ALTO and in PAGE must hyphenate identically.

`SPECS_LIB_V2.md` §6.3 promises format equivalence: what the library
derives from a document must not depend on the schema it arrived in. Two
halves of that promise were guarded — canonical text, and reconstruction
parity. The third, **hyphen roles**, was not.

A test carrying that title exists. It compares
``parser._build_ocr_text`` with ``reconstruct_textline`` — two readers of
**the same format**. That is a worthwhile property and it is not this one:
nothing compared ALTO's hyphenation to PAGE's.

What the two formats do *not* share is detection: ALTO reads
``SUBS_TYPE``/``HYP`` elements and falls back to a vetted trailing-mark
heuristic, PAGE has neither element and must decide from the text alone.
Downstream of that they converge — ``core/pairing.py`` is one shared
linker, and it assigns the PART2 side for both. So this compares two
independent detections through a common linker, which is the part worth
comparing; a reader compared to another reader of its own format is not.

Measured on 2026-08-16 over the two paired fixtures — 44 shared lines,
**zero disagreements** on all four fields. The property held; what was
missing was anything that would notice if it stopped.

Proven by mutation: restricting PAGE's repertoire to ASCII ``-`` fails
this and leaves the same-format test green. Both fixtures mark hyphens
with ``¬`` (U+00AC), so the mutation is the realistic one — a repertoire
quietly narrowed — rather than a broken parser.

Two mutations were *inert*, which is the more interesting result:
replacing ``HyphenRole.BOTH`` with ``PART1`` in either parser changes no
observable role, because the shared linker re-derives ``BOTH`` afterwards.
On these two fixtures both parsers' ``BOTH`` branch is therefore dead. Not
acted on — two pages are not enough to call a branch unreachable — but it
is the parallel-encoding smell `S1` watches for.

**On the alignment.** The pairs are two transcriptions of one page, not
one file converted twice, so they do not segment identically: ALTO splits
the Descartes header into ``8`` and ``DISCOURS.`` where PAGE carries
``8 Discours.``, and PAGE drops the La Fayette signature mark ``Q``. Those
are provenance facts about the fixtures, not library behaviour, so lines
are matched by canonical text and the unmatched ones are excluded — with a
floor below, since an alignment that matched nothing would also be green.
"""

from __future__ import annotations

from saknussemm.core.schemas import HyphenRole
from saknussemm.formats.loader import build_document_manifest

from tests._paths import EXAMPLES

#: Same page, once per format. ``_page_raw`` rather than ``_page_corrected``:
#: the raw transcription is what an OCR engine emits, so it is where the
#: hyphenation actually has to be derived.
#:
#: Each carries its own floors — ``(stem, shared lines, hyphenated lines)``.
#: Below them the comparison would be green on an alignment that matched
#: nothing, or on a page with no hyphenation to disagree about.
#:
#: Per pair, not for the set: the first version of this file used the totals
#: (44 shared, 16 hyphenated) as a per-pair threshold, so both guards failed
#: on La Fayette, which is a third the size. Measured 2026-08-16 —
#: Descartes 31 and 11, La Fayette 13 and 4.
_PAIRS = [
    ("Descartes1637_Discours_btv1b86069594_corrected_0014", 28, 9),
    ("LaFayette1678_Cleves_btv1b8610820b_corrected_0011", 12, 4),
]


def _hyphen_state_by_text(xml_name: str) -> dict[str, tuple[object, ...]]:
    """``{canonical text: everything the parse concluded about hyphenation}``.

    The partner is recorded as its *text*, not its id: ids are assigned by
    each file and comparing them across formats would compare the fixtures
    rather than the derivation.
    """
    path = EXAMPLES / "page" / xml_name
    manifest = build_document_manifest([(path, xml_name)])
    by_ref = {
        (line.page_id, line.line_id): line
        for page in manifest.pages
        for line in page.lines
    }
    out: dict[str, tuple[object, ...]] = {}
    for line in by_ref.values():
        partner = by_ref.get(
            (line.hyphen_pair_page_id or line.page_id, line.hyphen_pair_line_id or "")
        )
        out[line.ocr_text] = (
            line.hyphen_role.value,
            partner.ocr_text if partner is not None else None,
            line.hyphen_subs_content,
            line.hyphen_source_explicit,
        )
    return out


def _aligned(
    stem: str,
) -> tuple[dict[str, tuple[object, ...]], dict[str, tuple[object, ...]], set[str]]:
    alto = _hyphen_state_by_text(f"{stem}_alto4.xml")
    page = _hyphen_state_by_text(f"{stem}_page_raw.xml")
    return alto, page, set(alto) & set(page)


def test_the_alignment_matches_enough_of_each_page() -> None:
    """A comparison over an empty intersection reports success."""
    for stem, minimum_shared, _ in _PAIRS:
        alto, page, shared = _aligned(stem)
        assert len(shared) >= minimum_shared, (
            f"{stem}: only {len(shared)} line(s) matched by text between the "
            f"two formats ({len(alto)} in ALTO, {len(page)} in PAGE). The "
            "comparison below would then hold over almost nothing."
        )


def test_the_pages_actually_contain_hyphenation() -> None:
    """And a comparison over pages with no hyphen roles agrees trivially."""
    for stem, _, minimum_hyphenated in _PAIRS:
        alto, _, shared = _aligned(stem)
        hyphenated = sum(1 for text in shared if alto[text][0] != HyphenRole.NONE.value)
        assert hyphenated >= minimum_hyphenated, (
            f"{stem}: only {hyphenated} shared line(s) carry a hyphen role; "
            "agreement on a page without hyphenation is not evidence."
        )


def test_both_formats_derive_the_same_hyphenation() -> None:
    for stem, _, _ in _PAIRS:
        alto, page, shared = _aligned(stem)
        disagreements = {
            text: (alto[text], page[text])
            for text in shared
            if alto[text] != page[text]
        }
        assert not disagreements, (
            f"{stem}: {len(disagreements)} line(s) hyphenate differently "
            f"depending on the format they arrived in — {disagreements}. "
            "§6.3 promises the derivation does not depend on the schema. "
            "ALTO reads SUBS_TYPE/HYP and falls back to a vetted trailing-"
            "dash heuristic; PAGE has neither element and must reach the "
            "same conclusion by its own route. Each tuple is (role, partner "
            "text, SUBS content, explicit?)."
        )
