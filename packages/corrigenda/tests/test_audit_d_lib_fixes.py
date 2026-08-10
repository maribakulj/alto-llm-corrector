"""Audit-D remediation (2026-07-12) — library correctness cluster.

Each test pins one confirmed audit finding in the pure-core library
(editing, guards, rules, _ns, parsers). Every test is written to FAIL on
the pre-fix code and pass after.

Shrinking on purpose: the seven hyphenation findings this file used to
hold moved to ``tests/hyphenation/`` (`RM-05b`), where the invariant they
protect is the subject rather than the date they were found. What is left
is what has no invariant-shaped home yet.
"""

from __future__ import annotations

import pytest

from corrigenda.core.editing import (
    EditScript,
    RangeAnchor,
    ReplaceSpan,
    apply_edit_script,
)
from corrigenda.core.guards import check_adjacent_duplicates
from corrigenda.errors import ParseError
from corrigenda.formats.alto.parser import parse_alto_file
from corrigenda.formats.page.parser import parse_page_file
from corrigenda.formats.page._ns import polygon_to_bbox
from corrigenda.producers.rules import RulesProducer, SubstitutionRule


# ---------------------------------------------------------------------------
# #14 — polygon_to_bbox: a half-malformed x,y pair must be skipped atomically
# ---------------------------------------------------------------------------


def test_polygon_bbox_skips_half_malformed_pair_atomically():
    # Last pair has a good x (500) but a bad y (abc). The old code appended
    # x before y raised, inflating width to 490 from a coordinate the
    # docstring promises to skip.
    hpos, vpos, w, h = polygon_to_bbox("10,10 20,20 500,abc")
    assert (hpos, vpos, w, h) == (10, 10, 10, 10)


def test_polygon_bbox_wellformed_unchanged():
    assert polygon_to_bbox("617,1046 3450,1046 3450,5797 617,5797") == (
        617,
        1046,
        2833,
        4751,
    )


# ---------------------------------------------------------------------------
# #29 — check_adjacent_duplicates catches the third line of a run
# ---------------------------------------------------------------------------


def test_duplicate_run_of_three_all_reverted():
    # Distinct sources, identical corrections. The old loop flagged only the
    # first pair, leaving line 2 unreverted.
    reverts = check_adjacent_duplicates(
        [
            ("id0", "source alpha", "HALLUCINATED IDENTICAL LINE"),
            ("id1", "source beta", "HALLUCINATED IDENTICAL LINE"),
            ("id2", "source gamma", "HALLUCINATED IDENTICAL LINE"),
        ]
    )
    assert set(reverts) == {"id0", "id1", "id2"}


# ---------------------------------------------------------------------------
# #28 — RulesProducer lexicon guard normalises through NFC (ncfold)
# ---------------------------------------------------------------------------


def test_lexicon_guard_matches_nfd_entry():
    import unicodedata

    # Lexicon supplied in DECOMPOSED (NFD) form; the token the rule produces
    # is composed (NFC, as the parser emits). The guard must still fire.
    nfd_word = unicodedata.normalize("NFD", "modérné")
    assert nfd_word != "modérné"  # sanity: genuinely decomposed
    prod = RulesProducer(
        [SubstitutionRule("rn", "rné", lexicon_guarded=True)],
        lexicon={nfd_word},
    )
    # OCR "modérn" → the guarded rule turns "rn" into "rné" giving the known
    # word "modérné"; the guard (NFC-folded) accepts it.
    script = prod.build_edit_script({"l1": "modérn"})
    assert script.ops, "guarded substitution should fire against an NFD lexicon"


# ---------------------------------------------------------------------------
# #17 — PairingPolicy.same_block_only is page-qualified
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# #18 — fusion check ignores context-only pairs (F8 window mode)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# #13 — explicit-mode subs join strips the FULL hyphen repertoire
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# #6 — explicit-mode PART2 that absorbed trailing words falls back
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# #5 — E2 rejects a zero-length insertion co-located with a replacement
# ---------------------------------------------------------------------------


def test_e2_rejects_colocated_insertion_and_replacement():
    # insert@[2,2]='X' listed BEFORE replace@[2,7]='Y' on '0123456789'.
    # Old code accepted both and produced '01Y6789' (char 6 survived).
    script = EditScript(
        ops=[
            ReplaceSpan(line_id="l1", anchor=RangeAnchor(start=2, end=2), text="X"),
            ReplaceSpan(line_id="l1", anchor=RangeAnchor(start=2, end=7), text="Y"),
        ]
    )
    res = apply_edit_script(script, {"l1": "0123456789"})
    # The co-located pair must not corrupt the line: the replacement is
    # rejected as an overlap, so '6' can never survive a supposed [2,7) wipe.
    assert "6" not in res.text_by_id.get("l1", "0123456789")[:6] or res.rejected
    assert any(r.reason == "e2_overlap" for r in res.rejected)


# ---------------------------------------------------------------------------
# #30 — an id-less TextLine cannot round-trip; both parsers must refuse it
# ---------------------------------------------------------------------------

_ALTO_IDLESS = """\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Layout>
    <Page ID="P1" WIDTH="1000" HEIGHT="1000">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="1000">
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
          <TextLine HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20">
            <String CONTENT="orphan" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""

_PAGE_IDLESS = """\
<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Page imageFilename="p.png" imageWidth="1000" imageHeight="1000">
    <TextRegion id="r1">
      <Coords points="0,0 1000,0 1000,900 0,900"/>
      <TextLine>
        <Coords points="10,10 900,10 900,30 10,30"/>
        <TextEquiv><Unicode>orphan</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>"""


def test_alto_idless_textline_refused(tmp_path):
    p = tmp_path / "a.xml"
    p.write_text(_ALTO_IDLESS, encoding="utf-8")
    with pytest.raises(ParseError, match="without an id"):
        parse_alto_file(p, "a.xml")


def test_page_idless_textline_refused(tmp_path):
    p = tmp_path / "p.xml"
    p.write_text(_PAGE_IDLESS, encoding="utf-8")
    with pytest.raises(ParseError, match="without an id"):
        parse_page_file(p, "p.xml")


# ---------------------------------------------------------------------------
# #32 — an id-less region under a ReadingOrder keeps document order
# ---------------------------------------------------------------------------


def test_idless_region_under_reading_order_keeps_document_order():
    from lxml import etree

    from corrigenda.formats.page._ns import _detect_namespace
    from corrigenda.formats.page.parser import _regions_in_reading_order

    # Regions [A(id), B(NO id), C(id)] with ReadingOrder [C, A]. The
    # declaration says nothing about B; sorting would yank B to the end.
    # Conservative fix: bail to document order [A, B, C].
    xml = """\
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Page imageFilename="p.png" imageWidth="1000" imageHeight="1000">
    <ReadingOrder>
      <OrderedGroup id="g">
        <RegionRefIndexed index="0" regionRef="C"/>
        <RegionRefIndexed index="1" regionRef="A"/>
      </OrderedGroup>
    </ReadingOrder>
    <TextRegion id="A"><Coords points="0,0 10,0 10,10 0,10"/></TextRegion>
    <TextRegion><Coords points="0,20 10,20 10,30 0,30"/></TextRegion>
    <TextRegion id="C"><Coords points="0,40 10,40 10,50 0,50"/></TextRegion>
  </Page>
</PcGts>"""
    root = etree.fromstring(xml.encode())
    ns = _detect_namespace(root)
    page_el = root.find(f"{{{ns}}}Page")
    ordered = _regions_in_reading_order(page_el, ns)
    assert [r.get("id") for r in ordered] == ["A", None, "C"]
