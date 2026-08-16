"""Pin the slow-path token geometry distribution (spec F6).

``_compute_geometry`` splits a corrected line's width across its tokens.
Pre-fix, the 0.6 weight applied to space tokens did NOT enter the total
used to compute the per-unit width, so every space's shortfall was dumped
onto the last token via a single ``correction`` term — inflating it.

These tests pin the corrected contract:
  - widths sum EXACTLY to the line width (no drift);
  - the 0.6 space weight is consistent on both sides, so two identical
    words separated by a space get identical widths (the old code gave
    the trailing word all the accumulated space deficit);
  - the final token only absorbs residual rounding, never a large slug.
"""

from __future__ import annotations

import pytest

from lidenbrock.core.schemas import HyphenRole, LineStatus
from lidenbrock.formats.alto.rewriter import (
    _compute_geometry,
    _is_space_token,
    _tokenize,
)

from tests._docs import _ALTO_ONE_LINE
from tests.hyphenation._lines import _line


def _widths(text: str, hpos: int, width: int) -> list[int]:
    return [w for _t, _h, w in _compute_geometry(hpos, width, _tokenize(text))]


def test_widths_sum_exactly_to_line_width():
    for text, width in [
        ("hello world", 200),
        ("a b c d e", 173),
        ("Régnait de mille sept cent", 421),
        ("un", 40),
        ("le mot suivant est long", 999),
    ]:
        widths = _widths(text, hpos=10, width=width)
        assert sum(widths) == width, f"{text!r}: {sum(widths)} != {width}"


def test_hpos_is_contiguous_from_start():
    tokens = _tokenize("hello world foo")
    geo = _compute_geometry(50, 300, tokens)
    cursor = 50
    for _t, h, w in geo:
        assert h == cursor
        cursor += w


def test_identical_words_around_a_space_get_equal_widths():
    """Spec F6 — two identical words separated by one space must render
    with the same width. Pre-fix the trailing word absorbed the space
    deficit and came out wider."""
    widths = _widths("abcd abcd", hpos=0, width=100)
    # tokens: ["abcd", " ", "abcd"]
    assert len(widths) == 3
    assert widths[0] == widths[2], f"asymmetric: {widths}"


def test_final_token_not_inflated_by_space_deficit():
    """The last token must not be dramatically larger than an equal-length
    earlier token purely because of space handling."""
    # "aa bb cc" — three equal words, two spaces.
    widths = _widths("aa bb cc", hpos=0, width=100)
    word_widths = [widths[0], widths[2], widths[4]]
    spread = max(word_widths) - min(word_widths)
    # Equal-length words should differ only by rounding (<= 1px).
    assert spread <= 1, f"word widths not balanced: {word_widths}"


def test_all_widths_at_least_one_at_the_boundary():
    """Tight line where width equals the token count: every token still
    gets at least 1px and the sum invariant holds."""
    # "a b c" tokenises to 5 tokens; width 5 is the tightest all-1 case.
    widths = _widths("a b c", hpos=0, width=5)
    assert len(widths) == 5
    assert all(w >= 1 for w in widths), widths
    assert sum(widths) == 5


def test_degenerate_width_below_token_count_pins_floor_behaviour():
    """Post-audit F6 pin — when width < token count the exact-sum
    invariant is mathematically unsatisfiable with all-≥1 widths: the
    min-1 floor wins and the sum settles at the token count. Any feasible
    width keeps the exact sum, spread across several donors if needed."""
    # 11 tokens ("a b c d e f"), width 7 → infeasible: all 1, sum 11.
    widths = _widths("a b c d e f", hpos=0, width=7)
    assert len(widths) == 11
    assert all(w >= 1 for w in widths), widths
    assert sum(widths) == 11  # floor wins, documented

    # Feasible tight case: sum must be EXACT even when several tokens
    # need flooring (deficit spread over multiple donors).
    widths2 = _widths("aaaaaaaa b c", hpos=0, width=12)
    assert all(w >= 1 for w in widths2), widths2
    assert sum(widths2) == 12


# ---------------------------------------------------------------------------
# Tokenisation — which whitespace becomes an <SP>, and which does not
# ---------------------------------------------------------------------------


class TestTokenizeSplitsOnBreakingWhitespaceOnly:
    """A no-break space is a place one does NOT break, so it is not a
    separator: it belongs inside its String's CONTENT. Routing it through an
    ``<SP>`` — which carries no content — replaced it with an ordinary space
    and destroyed the only thing it was there to express."""

    def test_an_ordinary_space_separates(self):
        assert _tokenize("a b") == ["a", " ", "b"]

    def test_a_tab_separates(self):
        # A tab IS a break opportunity; it has no ALTO representation and
        # legitimately becomes an <SP>.
        assert _tokenize("a\tb") == ["a", "\t", "b"]

    def test_a_no_break_space_stays_inside_its_word(self):
        assert _tokenize("M. Dupont") == ["M. Dupont"]

    def test_a_narrow_no_break_space_stays_inside_its_word(self):
        # U+202F — French typography before % ; ! ? :
        assert _tokenize("12 %") == ["12 %"]

    def test_a_figure_space_stays_inside_its_word(self):
        assert _tokenize("1 000") == ["1 000"]

    def test_breaking_and_no_break_spaces_in_one_line(self):
        assert _tokenize("M. Dupont est là") == [
            "M. Dupont",
            " ",
            "est",
            " ",
            "là",
        ]

    def test_a_lone_no_break_space_is_not_a_space_token(self):
        # str.strip() calls U+00A0 whitespace, so the old classification
        # would have emitted this as an <SP> and lost it.
        assert _is_space_token(" ") is False
        assert _is_space_token(" ") is True
        assert _is_space_token("\t ") is True
        assert _is_space_token("a") is False


def test_geometry_weighs_a_no_break_space_as_part_of_its_word():
    """It is glyph-bearing content now, not a 0.6-weighted gap."""
    tokens = _tokenize("ab cd")
    assert tokens == ["ab cd"]
    geo = _compute_geometry(0, 100, tokens)
    assert [t for t, _h, _w in geo] == ["ab cd"]
    assert sum(w for _t, _h, w in geo) == 100


# ---------------------------------------------------------------------------
# The slow-path rebuild's own geometry: a trailing HYP must not land on top
# of a trailing SP, and an unusable HYP WIDTH falls back to the estimate
# rather than crashing (moved here from a wave-named file, `RM-05b`)
# ---------------------------------------------------------------------------


_ALTO_NS = "http://www.loc.gov/standards/alto/ns-v3#"


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


@pytest.mark.parametrize("corrected", ["deux mots- ", "deux mots-  ", " deux mots- "])
def test_f6_trailing_whitespace_geometry_tiles_cleanly(corrected):
    """corrected_text with leading/trailing whitespace on an explicit
    PART1 slow-path rebuild must still yield non-overlapping children
    summing exactly to the line WIDTH — pre-fix the HYP was placed at
    last_word end, on top of the trailing SP's range."""
    from lidenbrock.formats.alto.rewriter import _rebuild_line

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
    from lidenbrock.formats.alto.rewriter import _rebuild_line

    tl_clean = _part1_line_element()
    lm = _line("T1", "unseulmot-", role=HyphenRole.PART1, explicit=True)
    _rebuild_line(tl_clean, "deux mots-", lm, _ALTO_NS)
    clean = _rebuild_children(tl_clean)

    tl_spaced = _part1_line_element()
    _rebuild_line(tl_spaced, "deux mots- ", lm, _ALTO_NS)
    assert _rebuild_children(tl_spaced) == clean
    _assert_children_tile_line(tl_clean, 100, 1000)


@pytest.mark.parametrize("bad_width", ["1e999", "inf", "-inf", "nan", "abc"])
def test_review_w1_hyp_width_overflow_falls_back_to_estimate(bad_width):
    from lidenbrock.formats.alto.rewriter import _rebuild_line

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
    from lidenbrock.formats.alto.parser import parse_alto_file
    from lidenbrock.formats.alto.rewriter import rewrite_alto_file

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
