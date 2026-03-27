"""Tests for alto/rewriter.py"""
from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from app.alto.parser import parse_alto_file
from app.alto.rewriter import (
    _compute_geometry,
    _tokenize,
    rewrite_alto_file,
)
from app.schemas import Coords, HyphenRole, LineManifest, PageManifest, BlockManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NS_V3 = "http://www.loc.gov/standards/alto/ns-v3#"


def _ns(local: str) -> str:
    return f"{{{NS_V3}}}{local}"


def make_line(
    line_id: str,
    ocr_text: str,
    corrected_text: str | None = None,
    hyphen_role: HyphenRole = HyphenRole.NONE,
    hyphen_pair_line_id: str | None = None,
    hyphen_subs_content: str | None = None,
    hyphen_source_explicit: bool = False,
) -> LineManifest:
    return LineManifest(
        line_id=line_id,
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=10, vpos=20, width=400, height=30),
        ocr_text=ocr_text,
        corrected_text=corrected_text,
        hyphen_role=hyphen_role,
        hyphen_pair_line_id=hyphen_pair_line_id,
        hyphen_subs_content=hyphen_subs_content,
        hyphen_source_explicit=hyphen_source_explicit,
    )


def make_alto_xml(lines_xml: str, with_description: bool = False) -> str:
    desc = (
        """  <Description>
    <Processing ID="P1">
    </Processing>
  </Description>"""
        if with_description
        else ""
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<alto xmlns="{NS_V3}">\n'
        f"  {desc}\n"
        f"  <Layout>\n"
        f'    <Page ID="P1" WIDTH="2480" HEIGHT="3508">\n'
        f'      <PrintSpace HPOS="0" VPOS="0" WIDTH="2480" HEIGHT="3508">\n'
        f'        <TextBlock ID="TB1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="60">\n'
        f"          {lines_xml}\n"
        f"        </TextBlock>\n"
        f"      </PrintSpace>\n"
        f"    </Page>\n"
        f"  </Layout>\n"
        f"</alto>"
    )


def write_and_rewrite(
    tmp_path: Path,
    lines_xml: str,
    manifests: list[LineManifest],
    with_description: bool = False,
) -> etree._Element:
    xml_path = tmp_path / "test.xml"
    xml_path.write_text(make_alto_xml(lines_xml, with_description), encoding="utf-8")

    page = PageManifest(
        page_id="P1",
        source_file="test.xml",
        page_index=0,
        page_width=2480,
        page_height=3508,
        blocks=[BlockManifest(
            block_id="TB1",
            page_id="P1",
            block_order=0,
            coords=Coords(hpos=10, vpos=20, width=400, height=60),
            line_ids=[m.line_id for m in manifests],
        )],
        lines=manifests,
    )

    result_bytes = rewrite_alto_file(xml_path, [page], "openai", "gpt-4o")
    return etree.fromstring(result_bytes)


# ---------------------------------------------------------------------------
# Unit tests: _tokenize and _compute_geometry
# ---------------------------------------------------------------------------

def test_normal_line_tokenize():
    tokens = _tokenize("hello world")
    assert tokens == ["hello", " ", "world"]


def test_tokenize_multiple_spaces():
    tokens = _tokenize("a  b")
    assert tokens == ["a", "  ", "b"]


def test_geometry_sum_equals_width():
    tokens = _tokenize("hello world foo")
    geo = _compute_geometry(0, 300, tokens)
    total = sum(w for _, _, w in geo)
    assert total == 300


def test_geometry_sum_single_word():
    geo = _compute_geometry(0, 100, ["hello"])
    assert sum(w for _, _, w in geo) == 100


def test_geometry_sum_many_tokens():
    tokens = _tokenize("one two three four five six seven")
    geo = _compute_geometry(50, 500, tokens)
    assert sum(w for _, _, w in geo) == 500


# ---------------------------------------------------------------------------
# TextLine invariants
# ---------------------------------------------------------------------------

def test_line_id_preserved(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="Bonjour" HPOS="10" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "Bonjour", corrected_text="Bonjour")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    assert tl.get("ID") == "TL1"


def test_coords_preserved(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="test" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "test", corrected_text="corrected text")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    assert tl.get("HPOS") == "10"
    assert tl.get("VPOS") == "20"
    assert tl.get("WIDTH") == "400"
    assert tl.get("HEIGHT") == "30"


def test_string_ids_pattern(tmp_path):
    """When corrected text has more words than original, extra words get generated IDs.
    The first word reuses the original ID; the second gets a generated fallback."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="old" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "old", corrected_text="hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    ids = [s.get("ID") for s in strings]
    # Original ID "S1" is reused for position 0; position 1 gets generated ID
    assert "S1" in ids
    assert "TL1_STR_0001" in ids


def test_no_newline_in_content(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="old" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "old", corrected_text="hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    for s in root.findall(f".//{_ns('String')}"):
        assert "\n" not in (s.get("CONTENT") or "")
        assert "\r" not in (s.get("CONTENT") or "")


# ---------------------------------------------------------------------------
# Hyphenation: PART1
# ---------------------------------------------------------------------------

def test_part1_has_hyp_element(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/>
  <HYP CONTENT="-"/>
</TextLine>"""
    lm = make_line(
        "TL1", "por-", corrected_text="por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    hyp_els = tl.findall(_ns("HYP"))
    assert len(hyp_els) == 1
    assert hyp_els[0].get("CONTENT") == "-"


def test_part1_subs_type_when_explicit(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="tra-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="travail"/>
  <HYP CONTENT="-"/>
</TextLine>"""
    lm = make_line(
        "TL1", "tra-", corrected_text="tra-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="travail",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    last_str = strings[-1]
    assert last_str.get("SUBS_TYPE") == "HypPart1"


def test_part2_subs_type_when_explicit(tmp_path):
    lines_xml = """\
<TextLine ID="TL2" HPOS="10" VPOS="55" WIDTH="400" HEIGHT="30">
  <String ID="S2" CONTENT="vail" HPOS="10" VPOS="55" WIDTH="80" HEIGHT="30"
          SUBS_TYPE="HypPart2" SUBS_CONTENT="travail"/>
</TextLine>"""
    lm = make_line(
        "TL2", "vail", corrected_text="vail",
        hyphen_role=HyphenRole.PART2,
        hyphen_subs_content="travail",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    first_str = strings[0]
    assert first_str.get("SUBS_TYPE") == "HypPart2"


def test_subs_content_written_when_explicit(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="con-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
          SUBS_TYPE="HypPart1" SUBS_CONTENT="construction"/>
  <HYP CONTENT="-"/>
</TextLine>"""
    lm = make_line(
        "TL1", "con-", corrected_text="con-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="construction",
        hyphen_source_explicit=True,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    last_str = strings[-1]
    assert last_str.get("SUBS_CONTENT") == "construction"


def test_subs_content_absent_when_heuristic(tmp_path):
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="boule-" HPOS="10" VPOS="20" WIDTH="120" HEIGHT="30"/>
</TextLine>"""
    lm = make_line(
        "TL1", "boule-", corrected_text="boule-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content=None,
        hyphen_source_explicit=False,  # heuristic
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    for s in root.findall(f".//{_ns('String')}"):
        assert s.get("SUBS_CONTENT") is None
        assert s.get("SUBS_TYPE") is None


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

def test_round_trip_normal(tmp_path):
    """Parse → rewrite without any correction → re-parse → same IDs."""
    xml_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="{NS_V3}">
  <Layout>
    <Page ID="P1" WIDTH="2480" HEIGHT="3508">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="2480" HEIGHT="3508">
        <TextBlock ID="TB1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="60">
          <TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
            <String ID="S1" CONTENT="Bonjour" HPOS="10" VPOS="20" WIDTH="200" HEIGHT="30"/>
            <SP WIDTH="10"/>
            <String ID="S2" CONTENT="monde" HPOS="220" VPOS="20" WIDTH="190" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""
    xml_path = tmp_path / "round.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    pages, _ = parse_alto_file(xml_path, "round.xml")
    # No corrections applied — corrected_text stays None, rewriter uses ocr_text
    result_bytes = rewrite_alto_file(xml_path, pages, "openai", "gpt-4o")

    # Re-parse result
    out_path = tmp_path / "out.xml"
    out_path.write_bytes(result_bytes)
    pages2, _ = parse_alto_file(out_path, "out.xml")

    assert len(pages2) == 1
    assert len(pages2[0].lines) == 1
    assert pages2[0].lines[0].line_id == "TL1"


# ---------------------------------------------------------------------------
# Bug-fix tests: soft hyphen, WC, String IDs, HYP node preservation
# ---------------------------------------------------------------------------

def test_rewriter_no_soft_hyphen_in_content(tmp_path):
    """U+00AD soft hyphen must be stripped from String CONTENT."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="n\u00e9ces-" HPOS="10" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    # corrected_text contains a soft hyphen injected by the LLM
    lm = make_line("TL1", "n\u00e9ces-", corrected_text="n\u00e9ces\u00ad")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    for s in root.findall(f".//{_ns('String')}"):
        assert "\u00ad" not in (s.get("CONTENT") or ""), \
            "Soft hyphen U+00AD must not appear in CONTENT"


def test_rewriter_preserves_wc(tmp_path):
    """WC confidence scores must be copied from original String nodes by position."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="Bon" HPOS="10" VPOS="20" WIDTH="150" HEIGHT="30" WC="0.95"/>
  <SP WIDTH="10" HPOS="160" VPOS="20"/>
  <String ID="S2" CONTENT="jour" HPOS="170" VPOS="20" WIDTH="200" HEIGHT="30" WC="0.87"/>
</TextLine>"""
    lm = make_line("TL1", "Bon jour", corrected_text="Bon jour")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    assert len(strings) == 2
    assert strings[0].get("WC") == "0.95", "First String WC must be preserved"
    assert strings[1].get("WC") == "0.87", "Second String WC must be preserved"


def test_rewriter_preserves_string_ids(tmp_path):
    """Original String IDs must be reused by position after rewrite."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="word_001" CONTENT="Hello" HPOS="10" VPOS="20" WIDTH="180" HEIGHT="30"/>
  <SP WIDTH="10" HPOS="190" VPOS="20"/>
  <String ID="word_002" CONTENT="world" HPOS="200" VPOS="20" WIDTH="200" HEIGHT="30"/>
</TextLine>"""
    lm = make_line("TL1", "Hello world", corrected_text="Hello world")
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    strings = root.findall(f".//{_ns('String')}")
    ids = [s.get("ID") for s in strings]
    assert "word_001" in ids, "First original String ID must be preserved"
    assert "word_002" in ids, "Second original String ID must be preserved"


def test_rewriter_preserves_hyp_node_heuristic(tmp_path):
    """A heuristic PART1 line must always have a HYP child after rewrite."""
    lines_xml = """\
<TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
  <String ID="S1" CONTENT="boule-" HPOS="10" VPOS="20" WIDTH="120" HEIGHT="30"/>
  <HYP CONTENT="-" HPOS="130" VPOS="20" WIDTH="16" HEIGHT="30"/>
</TextLine>"""
    lm = make_line(
        "TL1", "boule-", corrected_text="boule-",
        hyphen_role=HyphenRole.PART1,
        hyphen_source_explicit=False,
    )
    root = write_and_rewrite(tmp_path, lines_xml, [lm])
    tl = root.find(f".//{_ns('TextLine')}")
    hyp_els = tl.findall(_ns("HYP"))
    assert len(hyp_els) == 1, "HYP node must be present for heuristic PART1 line"
    assert hyp_els[0].get("CONTENT") == "-"


def test_round_trip_with_hyphen(tmp_path):
    """Parse ALTO with explicit hyphen pair → rewrite → re-parse → HYP present."""
    xml_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="{NS_V3}">
  <Layout>
    <Page ID="P1" WIDTH="2480" HEIGHT="3508">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="2480" HEIGHT="3508">
        <TextBlock ID="TB1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="80">
          <TextLine ID="TL1" HPOS="10" VPOS="20" WIDTH="400" HEIGHT="30">
            <String ID="S1" CONTENT="por-" HPOS="10" VPOS="20" WIDTH="100" HEIGHT="30"
                    SUBS_TYPE="HypPart1" SUBS_CONTENT="porte"/>
            <HYP CONTENT="-"/>
          </TextLine>
          <TextLine ID="TL2" HPOS="10" VPOS="55" WIDTH="400" HEIGHT="30">
            <String ID="S2" CONTENT="te" HPOS="10" VPOS="55" WIDTH="60" HEIGHT="30"
                    SUBS_TYPE="HypPart2" SUBS_CONTENT="porte"/>
            <SP WIDTH="10"/>
            <String ID="S3" CONTENT="ouverte" HPOS="80" VPOS="55" WIDTH="200" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""
    xml_path = tmp_path / "hyp.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    pages, _ = parse_alto_file(xml_path, "hyp.xml")
    result_bytes = rewrite_alto_file(xml_path, pages, "openai", "gpt-4o")

    root = etree.fromstring(result_bytes)
    hyp_els = root.findall(f".//{{{NS_V3}}}HYP")
    assert len(hyp_els) >= 1
    assert hyp_els[0].get("CONTENT") == "-"

    # TL1 ID and coords must be intact
    tl1 = root.find(f".//{{{NS_V3}}}TextLine[@ID='TL1']")
    assert tl1 is not None
    assert tl1.get("WIDTH") == "400"
