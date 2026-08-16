"""Documents small enough to reason about, shared across topics.

One entry so far, and the bar for a second is the same: a fixture belongs
here only when files that share no invariant need the identical bytes.
``_ALTO_ONE_LINE`` is read by the identity tests (two files reusing the
same ``line_id``), by a hyphenation marker test (a single-String BOTH
line) and by a geometry test (a HYP with an unusable WIDTH) — three
subjects, one minimal document.

Fixtures used by ONE topic stay with it: see ``tests/hyphenation/_lines.py``
and ``tests/identity/_docs.py``.
"""

from __future__ import annotations

_ALTO_ONE_LINE = """\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Layout>
    <Page ID="P1" WIDTH="1000" HEIGHT="1000">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="1000">
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
          <TextLine ID="L1" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20">
            <String CONTENT="{text}" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""
