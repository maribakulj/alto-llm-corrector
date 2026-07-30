"""The ALTO slow path must REPORT the semantic String attributes it drops.

When a correction changes a line's word count the rewriter rebuilds its
``String`` children from scratch, recycling only ``ID``/``STYLEREFS``/
``STYLE`` (§6.1). Attributes like ``TAGREFS`` (links to structural/semantic
tags) and ``language`` are NOT invalidated by a spelling fix, yet they were
dropped silently — the rewrite called itself "lossless" while losing them.

Policy (agreed): keep the conservative whitelist (a re-segmented line can't
positionally re-attach a tag to the right new word, so we do NOT guess), but
COUNT every dropped semantic attribute into the loss report so "lossless"
stops being a lie. ``WC``/``CC`` (genuinely invalidated) and recomputed
geometry are NOT losses. The fast path edits in place and keeps these
attributes untouched — so only the slow path reports.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from corrigenda.formats.alto._ns import _detect_namespace
from corrigenda.formats.alto.parser import build_document_manifest
from corrigenda.formats.alto.rewriter import rewrite_alto_file

_NS = "http://www.loc.gov/standards/alto/ns-v3#"

_ALTO = f"""<?xml version="1.0"?>
<alto xmlns="{_NS}">
  <Layout>
    <Page ID="P1" WIDTH="600" HEIGHT="800">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="600" HEIGHT="800">
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="600" HEIGHT="30">
          <TextLine ID="L1" HPOS="0" VPOS="0" WIDTH="300" HEIGHT="30">
            <String ID="S1" CONTENT="foo" TAGREFS="T1" language="fr" CUSTOM="vendor-data" WC="0.9" STYLE="bold" HPOS="0" VPOS="0" WIDTH="120" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""


def _run(tmp_path: Path, corrected: str):
    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_ALTO, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    by_id = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    by_id["L1"].corrected_text = corrected
    return rewrite_alto_file(xml_path, doc.pages, "test", "mock")


def test_slow_path_reports_dropped_semantic_attrs(tmp_path: Path):
    # "foo" -> "foo bar": word count 1 -> 2 → slow path (rebuild).
    result = _run(tmp_path, "foo bar")
    assert result.rewriter_paths["L1"] == "slow_path"

    # The dropped semantic attributes are now COUNTED, per line and aggregate.
    assert result.losses.get("tagrefs_dropped") == 1
    assert result.losses.get("language_dropped") == 1
    assert result.losses.get("custom_dropped") == 1
    assert result.losses_by_line["L1"].get("tagrefs_dropped") == 1

    # WC is INVALIDATED, not dropped — it is reported, but per LINE and under
    # the key both formats share (R4), never as a per-String `wc_dropped`.
    assert "wc_dropped" not in result.losses
    assert result.losses.get("confidence_invalidated") == 1
    # Geometry and the recycled whitelist are NOT losses.
    assert "style_dropped" not in result.losses
    assert "hpos_dropped" not in result.losses
    assert "id_dropped" not in result.losses

    # Nor is CONTENT. The source reading is not LOST by a rebuild — it is
    # REPLACED by the correction, which is the entire point of the run.
    # Counting it inflated the loss report with a phantom: 239 "losses" on a
    # real 566-line page whose corrections were sound. A loss report that
    # counts a non-loss misleads an auditor exactly as much as one that
    # misses a real loss.
    assert "content_dropped" not in result.losses
    assert "content_dropped" not in (result.losses_by_line.get("L1") or {})

    # The behaviour itself is unchanged: the attrs really are gone from output
    # (we report, we don't invent a re-attachment).
    root = etree.fromstring(result.xml_bytes)
    ns = _detect_namespace(root)
    strings = [
        s for s in root.iter(f"{{{ns}}}String") if s.get("CONTENT") in ("foo", "bar")
    ]
    assert all(s.get("TAGREFS") is None for s in strings)


def test_fast_path_preserves_everything_it_can_and_reports_what_it_cannot(
    tmp_path: Path,
):
    # "foo" -> "bar": same word count → fast path edits CONTENT in place and
    # TAGREFS/language/CUSTOM survive untouched, so there is nothing to
    # DROP. It still invalidates the String's WC — the engine's confidence in
    # a word it no longer contains — and since R4 that is reported (per line).
    result = _run(tmp_path, "bar")
    assert result.rewriter_paths["L1"] == "fast_path"
    assert result.losses == {"confidence_invalidated": 1}
    assert result.losses_by_line == {"L1": {"confidence_invalidated": 1}}
    root = etree.fromstring(result.xml_bytes)
    ns = _detect_namespace(root)
    s1 = next(s for s in root.iter(f"{{{ns}}}String"))
    assert s1.get("TAGREFS") == "T1"
    assert s1.get("language") == "fr"
    assert s1.get("WC") is None  # what the counter is about


def test_a_fast_path_line_whose_words_are_untouched_reports_nothing(
    tmp_path: Path,
):
    """The counter follows the file, not the path. A line can reach the fast
    path on one changed word while another keeps its WC — and a line where
    NO String's CONTENT moved keeps every confidence, so it must report
    nothing even though it took a write path (here: a SUBS-only change would
    be the same shape)."""
    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_ALTO, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    by_id = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    by_id["L1"].corrected_text = "foo"  # identical → UNTOUCHED
    result = rewrite_alto_file(xml_path, doc.pages, "test", "mock")
    assert result.rewriter_paths["L1"] == "untouched"
    assert result.losses == {}
    root = etree.fromstring(result.xml_bytes)
    ns = _detect_namespace(root)
    assert next(s for s in root.iter(f"{{{ns}}}String")).get("WC") == "0.9"


def test_untouched_line_reports_nothing(tmp_path: Path):
    result = _run(tmp_path, "foo")
    assert result.rewriter_paths["L1"] == "untouched"
    assert result.losses == {}


def test_loss_surfaces_in_correction_report(tmp_path: Path):
    """End-to-end: a slow-path attribute drop reaches the user-facing
    ``CorrectionReport.format_losses`` — the point of reporting it."""
    from corrigenda import CorrectionPipeline

    from tests._pipeline_harness import DictProvider, RecordingObserver

    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_ALTO, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    pipeline = CorrectionPipeline.for_provider(
        DictProvider({"L1": "foo bar"}),
        api_key="k",
        model="m",
        provider_name="test",
        observer=RecordingObserver(),
    )
    result = pipeline.run_sync(
        document_manifest=doc, source_files={xml_path.name: xml_path}
    )
    assert result.report.format_losses is not None
    assert result.report.format_losses.get("tagrefs_dropped") == 1
    assert result.report.format_losses.get("language_dropped") == 1


# ---------------------------------------------------------------------------
# R2 — an EMPTIED line loses its alignment-scoped attributes, uncounted
# ---------------------------------------------------------------------------

_STYLED = _ALTO.replace(
    '<String ID="S1" CONTENT="foo" TAGREFS="T1" language="fr" '
    'CUSTOM="vendor-data" WC="0.9" STYLE="bold" HPOS="0" VPOS="0" '
    'WIDTH="120" HEIGHT="30"/>',
    '<String ID="S1" CONTENT="foo" STYLE="bold" STYLEREFS="TS1" HPOS="0" '
    'VPOS="0" WIDTH="60" HEIGHT="30"/>'
    '<SP WIDTH="10" HPOS="60" VPOS="0"/>'
    '<String ID="S2" CONTENT="bar" STYLE="italic" HPOS="70" VPOS="0" '
    'WIDTH="60" HEIGHT="30"/>',
)


def test_an_emptied_line_reports_the_styles_it_loses(tmp_path: Path):
    """``STYLE``/``STYLEREFS`` are ALIGNMENT_SCOPED: they survive when their
    ``String`` is matched to a target token and go when it is not, so the
    alignment-aware pass owns counting them. A correction that empties the
    line returns BEFORE that pass — there are no target tokens to align
    against — so every style went with no counter at all.

    Nothing is matched when nothing is written: the honest count is all of
    them. 56 lines of the repo's ALTO corpora carry these attributes, so the
    exposure is real even though emptying a line is a path the acceptance
    guards normally refuse.
    """
    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_STYLED, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    by_id = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    assert by_id["L1"].ocr_text == "foo bar"
    by_id["L1"].corrected_text = ""
    result = rewrite_alto_file(xml_path, doc.pages, "test", "mock")

    assert result.rewriter_paths["L1"] == "slow_path"
    assert result.losses.get("style_dropped") == 2  # bold + italic
    assert result.losses.get("stylerefs_dropped") == 1
    # And they really are gone from the output — we report, we do not invent.
    root = etree.fromstring(result.xml_bytes)
    ns = _detect_namespace(root)
    assert list(root.iter(f"{{{ns}}}String")) == []


def test_a_rebuilt_line_that_keeps_its_styles_reports_none(tmp_path: Path):
    """The other direction: same fixture, a correction that still writes both
    words. Both Strings align, both styles survive, and the counter that the
    emptied case needed must not fire here."""
    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_STYLED, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    by_id = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    by_id["L1"].corrected_text = "foo bar baz"  # 3 != 2 words → slow path
    result = rewrite_alto_file(xml_path, doc.pages, "test", "mock")
    assert result.rewriter_paths["L1"] == "slow_path"
    assert "style_dropped" not in result.losses
    assert "stylerefs_dropped" not in result.losses


# ---------------------------------------------------------------------------
# R3 — a PART2 line's <HYP> is removed with no counter
# ---------------------------------------------------------------------------


_PART2 = (
    '<String ID="S0" CONTENT="tion" SUBS_TYPE="HypPart2" '
    'SUBS_CONTENT="fonction" HPOS="0" VPOS="0" WIDTH="40" HEIGHT="30"/>'
)
_HYP = '<HYP CONTENT="-" HPOS="40" VPOS="0" WIDTH="8" HEIGHT="30"/>'
_TAIL = '<String ID="S1" CONTENT="suite" HPOS="60" VPOS="0" WIDTH="60" HEIGHT="30"/>'


def _one_line(children: str) -> str:
    return f"""<?xml version="1.0"?>
<alto xmlns="{_NS}">
  <Layout>
    <Page ID="P1" WIDTH="600" HEIGHT="800">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="600" HEIGHT="800">
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="600" HEIGHT="30">
          <TextLine ID="L1" HPOS="0" VPOS="0" WIDTH="300" HEIGHT="30">{children}</TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""


#: A continuation line whose HYP is line-TERMINAL — which the parser reads as
#: a forward break, so the role is BOTH and the HYP is re-emitted.
_PART2_TERMINAL_HYP = _one_line(_PART2 + _HYP)
#: The same line with the HYP in the MIDDLE. ALTO does not define this, the
#: parser tolerates it, the role stays PART2 — and the element is dropped.
_PART2_MIDLINE_HYP = _one_line(_PART2 + _HYP + _TAIL)


def test_a_terminal_hyp_on_a_part2_line_makes_it_BOTH_not_part2(tmp_path: Path):
    """The plan's premise for R3, corrected by measurement.

    R3 read "a PART2 line's ``<HYP>`` is removed with no counter". The
    common shape it evokes — a continuation line that also carries a
    trailing break mark — is not PART2 at all: the parser reads the trailing
    mark as a forward break and classifies the line ``BOTH``, which takes
    the PART1-like branch and RE-EMITS the HYP. Nothing is dropped and there
    is nothing to count.
    """
    from corrigenda.core.schemas import HyphenRole

    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_PART2_TERMINAL_HYP, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    lm = doc.pages[0].lines[0]
    assert lm.hyphen_role is HyphenRole.BOTH
    lm.corrected_text = "tion suite-"  # 2 words → slow path
    result = rewrite_alto_file(xml_path, doc.pages, "test", "mock")
    assert result.rewriter_paths["L1"] == "slow_path"
    assert "hyp_elements_removed" not in result.losses
    root = etree.fromstring(result.xml_bytes)
    ns = _detect_namespace(root)
    assert len(list(root.iter(f"{{{ns}}}HYP"))) == 1  # re-emitted, not lost


def test_a_part2_line_reports_the_break_element_it_loses(tmp_path: Path):
    """The shape that IS reachable: a ``<HYP>`` that is not line-terminal.

    ALTO defines HYP as the line's trailing break, so this is malformed —
    but the parser accepts it, keeps the role PART2, and the rebuild removes
    the element with no counter. 0 of the 1711 ALTO lines in ``examples/``
    and ``corpus/`` have the shape, so this pins a latent path the way L2's
    doubling test does.

    What is lost is the ELEMENT, not the mark: the ``-`` is already part of
    the reconstructed text and comes back inside a rebuilt ``String``'s
    CONTENT. Both halves are asserted, so nobody "fixes" this by
    re-synthesising a HYP that would then double the mark.
    """
    from corrigenda.core.schemas import HyphenRole

    xml_path = tmp_path / "p.xml"
    xml_path.write_text(_PART2_MIDLINE_HYP, encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    by_id = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    assert by_id["L1"].hyphen_role is HyphenRole.PART2
    assert by_id["L1"].ocr_text == "tion-suite"
    # 3 word tokens against the source's 2 Strings → the rebuild path.
    by_id["L1"].corrected_text = "tion-suite encore toujours"
    result = rewrite_alto_file(xml_path, doc.pages, "test", "mock")

    assert result.rewriter_paths["L1"] == "slow_path"
    assert result.losses.get("hyp_elements_removed") == 1
    root = etree.fromstring(result.xml_bytes)
    ns = _detect_namespace(root)
    assert list(root.iter(f"{{{ns}}}HYP")) == []
    # The MARK survives — in CONTENT, where the reconstruction put it.
    assert result.texts["L1"] == "tion-suite encore toujours"


def test_the_element_vocabulary_is_not_the_attribute_vocabulary() -> None:
    """``hyp_elements_removed`` deliberately avoids the ``<attr>_dropped``
    suffix: that suffix is a claim about a ``String`` attribute, and the
    differential invariant reads it as one (source count minus output count).
    An element loss keyed ``hyp_dropped`` would be checked against a
    non-existent ``HYP`` attribute and read as a phantom."""
    from corrigenda.core.losses import ALTO_STRING_ATTRIBUTES

    assert not "hyp_elements_removed".endswith("_dropped")
    assert "HYP" not in ALTO_STRING_ATTRIBUTES
