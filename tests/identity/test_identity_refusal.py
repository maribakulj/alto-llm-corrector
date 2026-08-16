"""What the parsers do when a file's identities are wrong — or only look it.

Four refusals and one acceptance, and the acceptance is the hard half: a
block id repeated on every page of a per-page OCR export is LEGITIMATE,
because identity is page-qualified. A gate strict enough to catch the
margin line that reuses a body id, and loose enough to let that through,
is the whole content of these cases.

Each was written to fail before its fix: the duplicate-id gate used to
scan the manifest's scope rather than the whole tree, so a margin or
nested duplicate exploded at rewrite time — after the full producer spend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saknussemm.errors import DuplicateIdError, ParseError
from saknussemm.formats.alto.parser import parse_alto_file
from saknussemm.formats.page.parser import parse_page_file

from tests.identity._docs import (
    _ALTO_IDLESS,
    _PAGE_IDLESS,
    _alto_doc,
    _write,
)


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


def test_alto_duplicate_margin_line_id_refused_at_parse_time(tmp_path: Path):
    """A margin TextLine reusing a body line's ID used to pass the parse
    gate (manifest scope) and explode only at rewrite time."""
    body = (
        "<TopMargin>"
        '<TextBlock ID="M1" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="30">'
        '<TextLine ID="SHARED" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="20">'
        '<String CONTENT="marge" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="20"/>'
        "</TextLine></TextBlock></TopMargin>"
        "<PrintSpace>"
        '<TextBlock ID="B1" HPOS="0" VPOS="100" WIDTH="900" HEIGHT="30">'
        '<TextLine ID="SHARED" HPOS="0" VPOS="100" WIDTH="900" HEIGHT="20">'
        '<String CONTENT="corps" HPOS="0" VPOS="100" WIDTH="900" HEIGHT="20"/>'
        "</TextLine></TextBlock></PrintSpace>"
    )
    with pytest.raises(DuplicateIdError):
        parse_alto_file(_write(tmp_path, _alto_doc(body)), "t.xml")


def test_page_duplicate_nested_line_id_refused(tmp_path: Path):
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Metadata><Creator>x</Creator><Created>2020-01-01T00:00:00</Created>
    <LastChange>2020-01-01T00:00:00</LastChange></Metadata>
  <Page imageFilename="p.png" imageWidth="1000" imageHeight="2000">
    <TextRegion id="r1">
      <Coords points="0,0 100,0 100,50 0,50"/>
      <TextLine id="SHARED"><Coords points="0,0 100,0 100,20 0,20"/>
        <TextEquiv><Unicode>a</Unicode></TextEquiv></TextLine>
      <TextRegion id="r1a">
        <Coords points="0,0 100,0 100,50 0,50"/>
        <TextLine id="SHARED"><Coords points="0,25 100,25 100,45 0,45"/>
          <TextEquiv><Unicode>b</Unicode></TextEquiv></TextLine>
      </TextRegion>
    </TextRegion>
  </Page>
</PcGts>"""
    with pytest.raises(DuplicateIdError):
        parse_page_file(_write(tmp_path, xml), "t.xml")


def test_block_ids_may_repeat_across_pages_of_one_file(tmp_path: Path):
    """Per-page OCR tools reuse block_0/block_1 on every page — block
    lookups are page-scoped downstream, so this is legitimate."""
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Layout>
    <Page ID="P1" WIDTH="1000" HEIGHT="1000"><PrintSpace>
      <TextBlock ID="block_0" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="30">
        <TextLine ID="p1l1" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="20">
          <String CONTENT="un" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="20"/>
        </TextLine>
      </TextBlock>
    </PrintSpace></Page>
    <Page ID="P2" WIDTH="1000" HEIGHT="1000"><PrintSpace>
      <TextBlock ID="block_0" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="30">
        <TextLine ID="p2l1" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="20">
          <String CONTENT="deux" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="20"/>
        </TextLine>
      </TextBlock>
    </PrintSpace></Page>
  </Layout>
</alto>"""
    pages, _ = parse_alto_file(_write(tmp_path, xml), "t.xml")
    assert len(pages) == 2  # parses fine — no DuplicateIdError
