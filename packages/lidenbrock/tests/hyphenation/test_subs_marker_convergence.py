"""What the rewriter asks about a hyphen marker, and what it writes, agree.

Two functions decide a BOTH line's fate on every run: ``_subs_need_update``
asks whether the ALTO ``SUBS_*`` markers have to be rewritten, and
``_apply_subs`` writes them. They disagreed on the single-String case —
the predicate demanded a forward ``HypPart1`` that the writer deliberately
never emits there, because the trailing ``HYP`` already marks the forward
break.

The consequence is not a wrong file, it is a wrong ROUTE: a byte-correct
line was classified as needing a SUBS rewrite on every run, forever, and
the fast skip never converged. So the invariant pinned here is a fixed
point — whatever the writer writes, the predicate must be satisfied
immediately afterwards.
"""

from __future__ import annotations

from lidenbrock.core.schemas import HyphenRole, LineManifest, LineStatus

from tests._docs import _ALTO_ONE_LINE
from tests.hyphenation._lines import _line


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
    from lidenbrock.formats.alto.rewriter import _subs_need_update

    assert (
        _subs_need_update(_single_string_both_element(), _both_manifest(), _ALTO_NS)
        is False
    )


def test_f5_predicate_converges_after_apply():
    """Fixed-point invariant: whatever _apply_subs writes,
    _subs_need_update must be False immediately afterwards."""
    from lidenbrock.formats.alto.rewriter import _apply_subs, _subs_need_update

    tl = _single_string_both_element()
    lm = _both_manifest()
    _apply_subs(tl, lm, _ALTO_NS)
    assert _subs_need_update(tl, lm, _ALTO_NS) is False


def test_f5_multi_string_both_still_flags_missing_forward_subs():
    """The guard must not weaken the multi-String case: a BOTH line whose
    DISTINCT last String misses its forward HypPart1 still needs update."""
    from lxml import etree

    from lidenbrock.formats.alto.rewriter import _apply_subs, _subs_need_update

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
    from lidenbrock.formats.alto.parser import parse_alto_file
    from lidenbrock.formats.alto.rewriter import rewrite_alto_file

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
