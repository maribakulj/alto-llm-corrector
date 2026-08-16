"""What ``LossPolicy(strict=True)`` does, and to which format (R7).

The policy reads as a general safety gate: "a correction that cannot project
without loss is REJECTED before any output exists". It is not general. The
check is ``LineManifest.word_count``, and only the PAGE parser populates that
field — ALTO's per-token ``String`` geometry redistributes at any token count,
so there is no word markup to lose and nothing for the gate to measure.

A host that sets ``strict=True`` on an ALTO document therefore gets the
default behaviour, silently. That is defensible; being silent about it was
not, because the same host has an ALTO rewrite that really does drop semantic
attributes it cannot re-attach — reported, and gated by nothing.

These tests pin both halves. Arming the gate for ALTO would change delivered
output and needs a measured threshold, not a flag flipped in passing; until
someone does that measurement, the restriction is a documented, tested fact.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from lidenbrock.core.schemas import LossPolicy
from lidenbrock.formats.alto.parser import build_document_manifest
from lidenbrock.formats.alto.rewriter import rewrite_alto_file
from lidenbrock.formats.page.parser import (
    build_document_manifest as build_page_manifest,
)

from tests._paths import EXAMPLES

_NS = "http://www.loc.gov/standards/alto/ns-v3#"
_PAGE_EXAMPLES = EXAMPLES / "page"
_NEWSEYE = _PAGE_EXAMPLES / "newseye-fr" / "0250199004.xml"

_ALTO = f"""<?xml version="1.0"?>
<alto xmlns="{_NS}">
  <Layout>
    <Page ID="P1" WIDTH="600" HEIGHT="800">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="600" HEIGHT="800">
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="600" HEIGHT="30">
          <TextLine ID="L1" HPOS="0" VPOS="0" WIDTH="300" HEIGHT="30">
            <String ID="S1" CONTENT="foo" TAGREFS="T1" language="fr"
                    HPOS="0" VPOS="0" WIDTH="120" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""


def test_alto_lines_carry_no_word_count_at_all() -> None:
    """The root of it: the gate's input is absent, so the gate cannot fire."""
    doc = build_document_manifest([(Path(_write_alto()), "p.xml")])
    counts = {lm.word_count for page in doc.pages for lm in page.lines}
    assert counts == {None}


def test_page_lines_do_carry_one() -> None:
    """The contrast, on a real fixture — the field is not dead, it is
    format-scoped."""
    doc = build_page_manifest([(_NEWSEYE, _NEWSEYE.name)])
    counts = [lm.word_count for page in doc.pages for lm in page.lines if lm.word_count]
    assert counts, "the PAGE fixture must carry Word markup for this to mean anything"


def test_strict_is_a_no_op_on_alto_and_the_rewrite_still_loses(
    tmp_path: Path,
) -> None:
    """Both halves in one assertion set.

    Under ``strict=True`` a word-count-changing ALTO correction projects
    anyway — and the rebuild drops ``TAGREFS``/``language``, which the report
    counts and the policy did not stop. A host reading the policy's promise
    and not this test would expect the opposite.
    """
    assert LossPolicy(strict=True).strict is True

    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_ALTO, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    by_id = {lm.line_id: lm for page in doc.pages for lm in page.lines}
    by_id["L1"].corrected_text = "foo bar"  # 1 -> 2 words: the rebuild path

    result = rewrite_alto_file(xml_path, doc.pages, "test", "mock")

    # It projected. Nothing reverted to source.
    assert result.rewriter_paths["L1"] == "slow_path"
    root = etree.fromstring(result.xml_bytes)
    contents = [s.get("CONTENT") for s in root.iter(f"{{{_NS}}}String")]
    assert contents == ["foo", "bar"]

    # And it lost semantic attributes on the way — reported, ungated.
    assert result.losses.get("tagrefs_dropped") == 1
    assert result.losses.get("language_dropped") == 1


def _write_alto() -> str:
    import tempfile

    path = Path(tempfile.mkdtemp()) / "p.xml"
    path.write_text(_ALTO, encoding="utf-8")
    return str(path)
