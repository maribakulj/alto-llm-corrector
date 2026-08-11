"""Minimal ALTO and PAGE documents with the identities under test.

Builders that put a chosen id — or no id, or a repeated one — exactly
where a parser has to notice it: a margin block, a nested region, a second
page. Moved out of ``test_review_fixes.py`` and ``test_audit_d_lib_fixes.py``
unchanged.

``_alto_doc`` here wraps a PAGE body and NOT a ``PrintSpace``, which is
what lets a caller place a block in a margin; ``test_structure_traversal``
has a same-named builder that wraps a ``PrintSpace`` instead. The two are
deliberately left separate: they emit different XML, and merging them
would quietly change what several tests assert.
"""

from __future__ import annotations

import textwrap
from pathlib import Path


def _write(tmp_path: Path, xml: str, name: str = "t.xml") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(xml).strip(), encoding="utf-8")
    return p


def _alto_doc(page_body: str) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Layout>
    <Page ID="P1" WIDTH="2000" HEIGHT="3000">
      {page_body}
    </Page>
  </Layout>
</alto>"""


def _tb(block_id: str, content: str, idnext: str | None = None, vpos: int = 10) -> str:
    nxt = f' IDNEXT="{idnext}"' if idnext else ""
    ident = f' ID="{block_id}"' if block_id is not None else ""
    return (
        f'<TextBlock{ident}{nxt} HPOS="10" VPOS="{vpos}" '
        'WIDTH="900" HEIGHT="40">'
        f'<TextLine ID="TL_{block_id or "anon"}_{vpos}" HPOS="10" VPOS="{vpos}" '
        'WIDTH="900" HEIGHT="20">'
        f'<String CONTENT="{content}" HPOS="10" VPOS="{vpos}" WIDTH="900" HEIGHT="20"/>'
        "</TextLine></TextBlock>"
    )


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
