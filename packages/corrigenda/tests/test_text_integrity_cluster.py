"""Library text-integrity cluster.

Each test pins one confirmed finding of docs/audit/AUDIT-2026-07-13.md
(fix plan: docs/audit/PLAN-CORRECTIONS.md, Vague 1, F1-F12). Every test
was written to FAIL on the pre-fix code and pass after.

Shrinking on purpose, and this is now the LAST file named after a wave:
its two siblings (``test_audit_d_lib_fixes.py``, ``test_review_fixes.py``)
were dissolved into the invariants they were about (`RM-05b`), and this
file has given up its hyphenation, adjacent-duplicate, polygon and lexicon
cases the same way. The line builder it shared moved with them and is
imported back here.

What remains is what still has no better home, and each has one waiting:
the ALTO ``SUBS`` predicate (F5) and the HYP width fallback belong beside
the rewriter, whose tests this wave does not open; the geometry tiling
(F6), the int parsing (F7-F8), the line-separator gates (F10) and the PAGE
custom-group preservation (F12) each want a topical file that does not
exist yet. Splitting them is the next slice, not this one.
"""

from __future__ import annotations

import pytest

from corrigenda.core.protocols import ProducerMetadata
from corrigenda.core.schemas import HyphenRole, LineManifest, LineStatus

from tests.hyphenation._lines import _line


# ---------------------------------------------------------------------------
# F1 — heuristic-mode PART2 absorption must fall back (mirror of the
# explicit-mode guard pinned by test_explicit_part2_absorption_falls_back)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F2 — duplicate-revert partner extension must walk whole hyphen chains
# (worklist/fixpoint), not just one hop from the originally flagged lines
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F3 — cross-chunk boundary duplicate pass must compare PRE-REVERT
# corrections: a 3-run of identical corrections straddling a boundary
# (a,b in chunk0 — reverted intra-chunk — then c in chunk1) was masked
# because the pass read the post-revert (OCR) text of the boundary line
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F4 — _producer_ops keyed by bare line_id collides across source files
# (only page_ids are unique document-wide), corrupting the dry-run
# edit_script deliverable
# ---------------------------------------------------------------------------

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


@pytest.mark.asyncio
async def test_f4_producer_ops_do_not_collide_across_files(tmp_path):
    """Two files legitimately reuse line_id 'L1' with the SAME rule
    matching at DIFFERENT offsets. Pre-fix the last chunk overwrote
    _producer_ops['L1'], so file A's op lost its span (degraded to
    replace_line) — or worse, could carry file B's span."""
    from corrigenda import CorrectionPipeline
    from corrigenda.core.editing import ReplaceSpan, apply_edit_script
    from corrigenda.core.editing import EditScript
    from corrigenda.formats.alto.parser import build_document_manifest
    from corrigenda.producers.rules import RulesProducer, SubstitutionRule
    from tests._pipeline_harness import RecordingObserver

    path_a = tmp_path / "a.xml"
    path_b = tmp_path / "b.xml"
    path_a.write_text(_ALTO_ONE_LINE.format(text="la frauce entiere"), "utf-8")
    path_b.write_text(_ALTO_ONE_LINE.format(text="grande frauce unie"), "utf-8")

    doc = build_document_manifest([(path_a, "a.xml"), (path_b, "b.xml")])
    pipeline = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("frauce", "france")]),
        observer=RecordingObserver(),
        producer_metadata=ProducerMetadata(name="rules", implementation="fr-ocr-v1"),
    )
    result = await pipeline.run(
        document_manifest=doc,
        source_files={"a.xml": path_a, "b.xml": path_b},
    )

    ops = result.edit_script.ops
    assert len(ops) == 2, ops
    # Both files keep their producer op TYPE and their OWN span offsets
    # (document order: file A then file B).
    op_a, op_b = ops
    assert isinstance(op_a, ReplaceSpan), f"file A's op degraded: {op_a!r}"
    assert isinstance(op_b, ReplaceSpan), f"file B's op degraded: {op_b!r}"
    assert op_a.anchor.start == 3, op_a
    assert op_b.anchor.start == 7, op_b
    # Replaying each file's op over ITS OWN OCR text reproduces the
    # pipeline's final text for that file.
    replay_a = apply_edit_script(EditScript(ops=[op_a]), {"L1": "la frauce entiere"})
    replay_b = apply_edit_script(EditScript(ops=[op_b]), {"L1": "grande frauce unie"})
    assert replay_a.text_by_id["L1"] == "la france entiere"
    assert replay_b.text_by_id["L1"] == "grande france unie"


# ---------------------------------------------------------------------------
# F5 — _subs_need_update must share _apply_subs's single-String BOTH
# guard: the predicate demanded a forward HypPart1 that _apply_subs
# (deliberately) never writes, so such lines never classified UNTOUCHED
# ---------------------------------------------------------------------------

_ALTO_NS = "http://www.loc.gov/standards/alto/ns-v3#"


def _single_string_both_element():
    from lxml import etree

    tl = etree.Element(f"{{{_ALTO_NS}}}TextLine", ID="M1")
    s = etree.SubElement(tl, f"{{{_ALTO_NS}}}String")
    s.set("CONTENT", "çait-")
    # Already byte-correct backward marker (middle fragment of a 3+-line
    # split word: PART2-of-previous on its only String).
    s.set("SUBS_TYPE", "HypPart2")
    s.set("SUBS_CONTENT", "dénonçait")
    etree.SubElement(tl, f"{{{_ALTO_NS}}}HYP").set("CONTENT", "-")
    return tl


def _both_manifest() -> LineManifest:
    lm = _line("M1", "çait-", role=HyphenRole.BOTH, subs="dénonçait", explicit=True)
    lm.hyphen_forward_explicit = True
    lm.hyphen_forward_subs_content = "çaitsuite"
    return lm


def test_f5_single_string_both_predicate_false_on_correct_state():
    """A byte-correct single-String BOTH line must NOT be reported as
    needing a SUBS update: _apply_subs deliberately skips the forward
    write there (the trailing HYP already marks the forward hyphen), so
    the predicate demanding HypPart1 on the same String could never be
    satisfied — the line was misrouted to SUBS-ONLY on every run."""
    from corrigenda.formats.alto.rewriter import _subs_need_update

    assert (
        _subs_need_update(_single_string_both_element(), _both_manifest(), _ALTO_NS)
        is False
    )


def test_f5_predicate_converges_after_apply():
    """Fixed-point invariant: whatever _apply_subs writes,
    _subs_need_update must be False immediately afterwards."""
    from corrigenda.formats.alto.rewriter import _apply_subs, _subs_need_update

    tl = _single_string_both_element()
    lm = _both_manifest()
    _apply_subs(tl, lm, _ALTO_NS)
    assert _subs_need_update(tl, lm, _ALTO_NS) is False


def test_f5_multi_string_both_still_flags_missing_forward_subs():
    """The guard must not weaken the multi-String case: a BOTH line whose
    DISTINCT last String misses its forward HypPart1 still needs update."""
    from lxml import etree

    from corrigenda.formats.alto.rewriter import _apply_subs, _subs_need_update

    tl = _single_string_both_element()
    s2 = etree.SubElement(tl, f"{{{_ALTO_NS}}}String")
    s2.set("CONTENT", "mot-")
    # Keep document order String,String,HYP (HYP must stay last).
    tl.remove(tl[1])  # move HYP after the new String
    etree.SubElement(tl, f"{{{_ALTO_NS}}}HYP").set("CONTENT", "-")
    lm = _both_manifest()
    lm.ocr_text = "çait- mot-"
    assert _subs_need_update(tl, lm, _ALTO_NS) is True
    _apply_subs(tl, lm, _ALTO_NS)
    assert _subs_need_update(tl, lm, _ALTO_NS) is False
    strings = [c for c in tl if c.tag == f"{{{_ALTO_NS}}}String"]
    assert strings[-1].get("SUBS_TYPE") == "HypPart1"


def test_f5_single_string_both_identity_line_routes_untouched(tmp_path):
    """End-to-end router check: an identity correction on a byte-correct
    single-String BOTH line must take Path 1 (UNTOUCHED) — pre-fix it
    always fell to Path 2 (SUBS-ONLY) and the fast-skip never converged."""
    from corrigenda.formats.alto.parser import parse_alto_file
    from corrigenda.formats.alto.rewriter import rewrite_alto_file

    xml = _ALTO_ONE_LINE.format(text="placeholder").replace(
        '<String CONTENT="placeholder" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20"/>',
        '<String CONTENT="çait-" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20"'
        ' SUBS_TYPE="HypPart2" SUBS_CONTENT="dénonçait"/><HYP CONTENT="-"/>',
    )
    path = tmp_path / "both.xml"
    path.write_text(xml, encoding="utf-8")
    pages, _root = parse_alto_file(path, "both.xml")
    (lm,) = [line for p in pages for line in p.lines]
    # Force the exact single-String BOTH shape (a real one arises from a
    # 3+-line chain; the rewriter contract is per-line so we pin it here).
    lm.hyphen_role = HyphenRole.BOTH
    lm.hyphen_source_explicit = True
    lm.hyphen_subs_content = "dénonçait"
    lm.hyphen_forward_explicit = True
    lm.hyphen_forward_subs_content = "çaitsuite"
    lm.corrected_text = lm.ocr_text
    lm.status = LineStatus.CORRECTED

    out_bytes, metrics, paths = rewrite_alto_file(path, pages, "test", "model")
    assert paths[lm.line_id] == "untouched", paths
    assert metrics.untouched == 1 and metrics.subs_only == 0


# ---------------------------------------------------------------------------
# F6 — slow-path trailing HYP placed after the last WORD, ignoring a
# trailing SP: corrected text ending in whitespace produced overlapping
# geometry (HYP on top of the SP's HPOS range)
# ---------------------------------------------------------------------------


def _rebuild_children(tl):
    """(localname, hpos, width) for every child, in document order."""
    out = []
    for c in tl:
        local = c.tag.rsplit("}", 1)[-1]
        out.append((local, int(c.get("HPOS")), int(c.get("WIDTH"))))
    return out


def _assert_children_tile_line(tl, line_hpos: int, line_width: int) -> None:
    children = _rebuild_children(tl)
    cursor = line_hpos
    for local, hpos, width in children:
        assert hpos == cursor, f"{local} at {hpos}, expected {cursor}: {children}"
        cursor += width
    assert cursor == line_hpos + line_width, children


def _part1_line_element():
    from lxml import etree

    tl = etree.Element(f"{{{_ALTO_NS}}}TextLine")
    tl.set("ID", "T1")
    tl.set("HPOS", "100")
    tl.set("VPOS", "0")
    tl.set("WIDTH", "1000")
    tl.set("HEIGHT", "50")
    s = etree.SubElement(tl, f"{{{_ALTO_NS}}}String")
    for k, v in (
        ("ID", "S1"),
        ("CONTENT", "unseulmot-"),
        ("HPOS", "100"),
        ("VPOS", "0"),
        ("WIDTH", "960"),
        ("HEIGHT", "50"),
    ):
        s.set(k, v)
    h = etree.SubElement(tl, f"{{{_ALTO_NS}}}HYP")
    h.set("CONTENT", "-")
    h.set("WIDTH", "40")
    return tl


@pytest.mark.parametrize("corrected", ["deux mots- ", "deux mots-  ", " deux mots- "])
def test_f6_trailing_whitespace_geometry_tiles_cleanly(corrected):
    """corrected_text with leading/trailing whitespace on an explicit
    PART1 slow-path rebuild must still yield non-overlapping children
    summing exactly to the line WIDTH — pre-fix the HYP was placed at
    last_word end, on top of the trailing SP's range."""
    from corrigenda.formats.alto.rewriter import _rebuild_line

    tl = _part1_line_element()
    lm = _line("T1", "unseulmot-", role=HyphenRole.PART1, explicit=True)
    _rebuild_line(tl, corrected, lm, _ALTO_NS)
    _assert_children_tile_line(tl, 100, 1000)
    # The HYP is the LAST child, at the very end of the line.
    local, hpos, width = _rebuild_children(tl)[-1]
    assert local == "HYP"
    assert hpos + width == 1100


def test_f6_no_whitespace_geometry_unchanged():
    """Non-regression: the trim must not alter a clean rebuild."""
    from corrigenda.formats.alto.rewriter import _rebuild_line

    tl_clean = _part1_line_element()
    lm = _line("T1", "unseulmot-", role=HyphenRole.PART1, explicit=True)
    _rebuild_line(tl_clean, "deux mots-", lm, _ALTO_NS)
    clean = _rebuild_children(tl_clean)

    tl_spaced = _part1_line_element()
    _rebuild_line(tl_spaced, "deux mots- ", lm, _ALTO_NS)
    assert _rebuild_children(tl_spaced) == clean
    _assert_children_tile_line(tl_clean, 100, 1000)


# ---------------------------------------------------------------------------
# F7/F8/F9 — infinity/overflow-shaped numeric strings crashed with an
# uncaught OverflowError (int(float("1e999"))) instead of following the
# documented policy: tolerant → default, strict → ValueError (the same
# class promised for genuinely non-numeric values), polygon pair → skip
# ---------------------------------------------------------------------------

_INF_SHAPED = ["inf", "-inf", "Infinity", "1e999", "-1e400", "nan"]


@pytest.mark.parametrize("raw", _INF_SHAPED)
def test_f7_parse_int_tolerant_defaults_on_non_finite(raw: str):
    from corrigenda.core._parse import parse_int_tolerant

    assert parse_int_tolerant(raw, 7) == 7


@pytest.mark.parametrize("raw", _INF_SHAPED)
def test_f7_parse_int_strict_raises_the_promised_class(raw: str):
    from corrigenda.core._parse import parse_int_tolerant

    with pytest.raises(ValueError):
        parse_int_tolerant(raw, 0, strict=True)


def test_f8_alto_int_attr_inf_coordinate_surfaces_as_value_error():
    """ALTO geometry policy: a non-representable coordinate must surface
    as the promised ValueError (real error worth surfacing) — pre-fix an
    OverflowError escaped instead."""
    from lxml import etree

    from corrigenda.formats.alto._ns import _int_attr

    el = etree.Element("TextLine", WIDTH="1e400")
    with pytest.raises(ValueError):
        _int_attr(el, "WIDTH")
    # Missing attribute still defaults.
    assert _int_attr(el, "HPOS", 3) == 3


# ---------------------------------------------------------------------------
# F10 — the newline check must cover every str.splitlines boundary:
# U+2028/U+2029 (and \x0b \x0c \x85 …) survived into single-line ALTO
# CONTENT because only "\n"/"\r" were rejected — twin sites: the LLM
# response validator AND editing's replace_line gate
# ---------------------------------------------------------------------------

_SEPARATORS = [" ", " ", "\x0b", "\x0c", "\x85", "\x1c", "\x1d", "\x1e"]


@pytest.mark.parametrize("sep", _SEPARATORS)
def test_f10_validator_rejects_unicode_line_separators(sep: str):
    from corrigenda.core.validator import validate_llm_response
    from corrigenda.errors import ValidationError

    raw = {"lines": [{"line_id": "l1", "corrected_text": f"hello{sep}world"}]}
    with pytest.raises(ValidationError):
        validate_llm_response(raw, ["l1"], None, {"l1": "hello world"})


@pytest.mark.parametrize("sep", _SEPARATORS)
def test_f10_editing_rejects_unicode_line_separators(sep: str):
    from corrigenda.core.editing import (
        EditScript,
        ReplaceLine,
        apply_edit_script,
    )

    script = EditScript(ops=[ReplaceLine(line_id="l1", text=f"hello{sep}world")])
    res = apply_edit_script(script, {"l1": "hello world"})
    # A fully-rejected line is ABSENT from text_by_id (keeps prior text).
    assert "l1" not in res.text_by_id, "op must be rejected"
    assert res.rejected and res.rejected[0].reason == "e3_newline"


def test_f10_plain_text_still_accepted():
    from corrigenda.core.validator import validate_llm_response

    raw = {"lines": [{"line_id": "l1", "corrected_text": "héllo wörld"}]}
    resp = validate_llm_response(raw, ["l1"], None, {"l1": "hello world"})
    assert resp.lines[0].corrected_text == "héllo wörld"


# ---------------------------------------------------------------------------
# F11 — lexicon guard must re-validate the COMPOSED token when several
# edits land inside one whitespace-delimited word: each guard vetted its
# own edit against the ORIGINAL token in isolation, so the composition
# could produce a word NOT in the lexicon
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F12 — kept structural groups must be preserved VERBATIM (source
# slice), not re-emitted with normalised spacing: non-Transkribus
# exporters legitimately write `readingOrder{index:0;}` (no space) and
# reconstruction silently altered it
# ---------------------------------------------------------------------------


def test_f12_kept_group_spacing_preserved_verbatim():
    from corrigenda.formats.page._custom import strip_offset_groups

    new, removed = strip_offset_groups(
        "readingOrder{index:0;} textStyle {offset:0;length:3;}"
    )
    assert removed == 1
    assert new == "readingOrder{index:0;}", new  # no space injected


def test_f12_inter_group_source_text_preserved_between_kept_groups():
    from corrigenda.formats.page._custom import strip_offset_groups

    new, removed = strip_offset_groups(
        "readingOrder {index:0;}  structure {type:heading;} textStyle {offset:1;}"
    )
    assert removed == 1
    # The double space between the two KEPT groups is source text.
    assert new == "readingOrder {index:0;}  structure {type:heading;}", new


def test_f12_nothing_removed_is_byte_identity():
    from corrigenda.formats.page._custom import strip_offset_groups

    src = "readingOrder{index:0;}   structure {type:heading;}"
    assert strip_offset_groups(src) == (src, 0)


def test_f12_all_groups_removed_yields_empty():
    from corrigenda.formats.page._custom import strip_offset_groups

    assert strip_offset_groups("textStyle {offset:0;length:3;}") == ("", 1)


def test_f12_canonical_transkribus_spacing_unchanged():
    from corrigenda.formats.page._custom import strip_offset_groups

    new, removed = strip_offset_groups(
        "readingOrder {index:0;} textStyle {offset:12;length:5;}"
    )
    assert (new, removed) == ("readingOrder {index:0;}", 1)


# ---------------------------------------------------------------------------
# Wave-1 adversarial-review follow-up — F7-class twin the fix missed: the
# slow-path rebuild read the ORIGINAL HYP's WIDTH with a bare
# ``int(float(...))`` guarded only by ``except (TypeError, ValueError)``,
# so an inf/overflow-shaped value (``WIDTH="1e999"``) crashed the whole
# rewrite with an uncaught OverflowError. The HYP element is never parsed
# by ``_int_attr`` upstream, so a malformed upload reaches this site
# directly. Policy at this call site is TOLERANT (unusable width → the
# 4% estimate), matching the pre-existing "abc" behaviour.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_width", ["1e999", "inf", "-inf", "nan", "abc"])
def test_review_w1_hyp_width_overflow_falls_back_to_estimate(bad_width):
    from corrigenda.formats.alto.rewriter import _rebuild_line

    tl = _part1_line_element()
    tl[-1].set("WIDTH", bad_width)  # the HYP child
    lm = _line("T1", "unseulmot-", role=HyphenRole.PART1, explicit=True)
    # Pre-fix: OverflowError for the inf-shaped values. Post-fix: the
    # unusable width follows the tolerant policy — 4% estimate — and the
    # rebuilt children still tile the line exactly.
    _rebuild_line(tl, "deux mots-", lm, _ALTO_NS)
    _assert_children_tile_line(tl, 100, 1000)
    local, _hpos, _width = _rebuild_children(tl)[-1]
    assert local == "HYP"


def test_review_w1_hyp_width_overflow_end_to_end(tmp_path):
    """A malformed upload (HYP WIDTH="1e999" on an explicit PART1) with a
    word-count-changing correction must not abort the whole rewrite."""
    from corrigenda.formats.alto.parser import parse_alto_file
    from corrigenda.formats.alto.rewriter import rewrite_alto_file

    xml = _ALTO_ONE_LINE.format(text="placeholder").replace(
        '<String CONTENT="placeholder" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20"/>',
        '<String CONTENT="unseulmot-" HPOS="10" VPOS="10" WIDTH="860" HEIGHT="20"'
        ' SUBS_TYPE="HypPart1" SUBS_CONTENT="unseulmotsuite"/>'
        '<HYP CONTENT="-" WIDTH="1e999"/>',
    )
    path = tmp_path / "overflow-hyp.xml"
    path.write_text(xml, encoding="utf-8")
    pages, _root = parse_alto_file(path, "overflow-hyp.xml")
    (lm,) = [line for p in pages for line in p.lines]
    lm.corrected_text = "deux mots-"  # forces the slow-path rebuild
    lm.status = LineStatus.CORRECTED

    out_bytes, _metrics, paths = rewrite_alto_file(path, pages, "test", "model")
    assert lm.line_id in paths
    assert (
        b"deux mots"
        in out_bytes.replace(b'CONTENT="deux"', b"deux").replace(
            b'CONTENT="mots-"', b"mots"
        )
        or b"deux" in out_bytes
    )


@pytest.mark.asyncio
async def test_review_w1_edit_script_ops_attributable_across_files(tmp_path):
    """Wave-1 review follow-up (F4 residual) — the (page_id, line_id)
    keying fixed the internal capture collision, but the EMITTED dry-run
    edit_script still carried two ops with the same bare line_id and no
    file qualifier: a consumer replaying the whole script could not
    attribute each op to its file. Ops must now carry the page_id and
    apply_edit_script(page_id=…) must scope replay to one page."""
    from corrigenda import CorrectionPipeline
    from corrigenda.core.editing import EditScript, apply_edit_script
    from corrigenda.formats.alto.parser import build_document_manifest
    from corrigenda.producers.rules import RulesProducer, SubstitutionRule
    from tests._pipeline_harness import RecordingObserver

    path_a = tmp_path / "a.xml"
    path_b = tmp_path / "b.xml"
    path_a.write_text(_ALTO_ONE_LINE.format(text="la frauce entiere"), "utf-8")
    path_b.write_text(_ALTO_ONE_LINE.format(text="grande frauce unie"), "utf-8")

    doc = build_document_manifest([(path_a, "a.xml"), (path_b, "b.xml")])
    pipeline = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("frauce", "france")]),
        observer=RecordingObserver(),
        producer_metadata=ProducerMetadata(name="rules", implementation="fr-ocr-v1"),
    )
    result = await pipeline.run(
        document_manifest=doc,
        source_files={"a.xml": path_a, "b.xml": path_b},
    )

    ops = result.edit_script.ops
    assert len(ops) == 2, ops
    # Every emitted op is attributable: page_ids present and distinct
    # (page_ids are document-unique even when line_ids repeat).
    page_a_id, page_b_id = (p.page_id for p in doc.pages)
    assert [op.page_id for op in ops] == [page_a_id, page_b_id], ops

    # Replaying the WHOLE script scoped to one page applies only that
    # page's op — no cross-file bleed, no spurious rejection.
    full = EditScript(ops=list(ops))
    replay_a = apply_edit_script(full, {"L1": "la frauce entiere"}, page_id=page_a_id)
    replay_b = apply_edit_script(full, {"L1": "grande frauce unie"}, page_id=page_b_id)
    assert replay_a.text_by_id["L1"] == "la france entiere"
    assert not replay_a.rejected, replay_a.rejected
    assert replay_b.text_by_id["L1"] == "grande france unie"
    assert not replay_b.rejected, replay_b.rejected

    # Unscoped replay keeps its historical behaviour (all ops considered).
    legacy = apply_edit_script(EditScript(ops=[ops[0]]), {"L1": "la frauce entiere"})
    assert legacy.text_by_id["L1"] == "la france entiere"
