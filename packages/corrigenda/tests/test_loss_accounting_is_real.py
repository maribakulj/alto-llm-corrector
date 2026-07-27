"""A counted loss must be a loss (R1-R4, differential).

The report claims every granularity loss is counted. That claim is only
worth something if the counter and the file agree, and nothing compared
them: the counters are incremented where the rewriter *decides* to drop
something, not where the bytes end up. A later pass that puts an attribute
back leaves the counter standing.

So the invariant is a differential one — count the attribute in the source
line, count it in the rewritten line, and require the report's number to be
the difference:

    losses_by_line[line]["<attr>_dropped"] == occurrences(source) -
                                              occurrences(output)

A phantom (counter high, nothing gone) misleads an auditor exactly as much
as a blind spot (something gone, counter silent). This file rejects both
directions, which is the point: "every loss is counted" and "every count is
a loss" are two claims and the repo only ever tested the first.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from corrigenda.core.schemas import LineStatus
from corrigenda.formats.alto._ns import _detect_namespace
from corrigenda.formats.alto.parser import parse_alto_file
from corrigenda.formats.alto.rewriter import rewrite_alto_file

_EXAMPLES = Path(__file__).parent.parent.parent.parent / "examples"

#: ``<attr>_dropped`` -> the ALTO attribute it claims to have dropped.
_ATTR_OF_KEY = re.compile(r"^(?P<attr>[a-z_]+)_dropped$")


def _string_attr_counts(textline: etree._Element, ns: str) -> Counter[str]:
    """How many of the line's ``String`` children carry each attribute."""
    tag = f"{{{ns}}}String" if ns else "String"
    counts: Counter[str] = Counter()
    for string_el in textline:
        if string_el.tag != tag:
            continue
        for key in string_el.attrib:
            counts[str(key).rsplit("}", 1)[-1].lower()] += 1
    return counts


def _lines_by_id(xml: bytes | Path) -> tuple[dict[str, etree._Element], str]:
    root = (
        etree.fromstring(xml)
        if isinstance(xml, bytes)
        else etree.parse(str(xml)).getroot()
    )
    ns = _detect_namespace(root)
    tag = f"{{{ns}}}TextLine" if ns else "TextLine"
    return {tl.get("ID"): tl for tl in root.iter(tag)}, ns


def assert_every_count_is_a_real_loss(
    source: Path, output: bytes, losses_by_line: dict[str, dict[str, int]]
) -> None:
    """The invariant, over one rewritten file."""
    src_lines, src_ns = _lines_by_id(source)
    out_lines, out_ns = _lines_by_id(output)

    for line_id, losses in losses_by_line.items():
        before = _string_attr_counts(src_lines[line_id], src_ns)
        after = _string_attr_counts(out_lines[line_id], out_ns)

        for key, claimed in losses.items():
            m = _ATTR_OF_KEY.match(key)
            if m is None:
                continue  # not an attribute claim (e.g. word_order_suspected)
            attr = m.group("attr")
            actual = before[attr] - after[attr]
            assert claimed == actual, (
                f"{line_id}: report claims {claimed} × {key}, but the file "
                f"went from {before[attr]} to {after[attr]} occurrences of "
                f"{attr.upper()} — a difference of {actual}. "
                + (
                    "The counter is a phantom: nothing was lost."
                    if actual < claimed
                    else "The counter understates a real loss."
                )
            )


def assert_every_real_loss_is_counted(
    source: Path, output: bytes, losses_by_line: dict[str, dict[str, int]]
) -> None:
    """The other direction — an attribute that vanished must be counted."""
    src_lines, src_ns = _lines_by_id(source)
    out_lines, out_ns = _lines_by_id(output)

    for line_id, src_line in src_lines.items():
        before = _string_attr_counts(src_line, src_ns)
        after = _string_attr_counts(out_lines[line_id], out_ns)
        losses = losses_by_line.get(line_id, {})
        for attr, count in before.items():
            gone = count - after[attr]
            if gone <= 0:
                continue
            claimed = losses.get(f"{attr}_dropped", 0)
            assert claimed == gone, (
                f"{line_id}: {gone} × {attr.upper()} disappeared from the "
                f"rewritten line but the report counts {claimed}. A loss the "
                "report does not carry is a loss the host cannot audit."
            )


def _rewrite(name: str, transform) -> tuple[Path, bytes, dict[str, dict[str, int]]]:
    path = _EXAMPLES / name
    pages, _ = parse_alto_file(path, path.name)
    for page in pages:
        for lm in page.lines:
            lm.corrected_text = transform(lm.ocr_text)
            lm.status = LineStatus.CORRECTED
    result = rewrite_alto_file(path, pages, "test", "mock")
    return path, result.xml_bytes, result.losses_by_line


# ---------------------------------------------------------------------------
# Direction 1: every COUNT is a real loss.  Closed (R1).
# ---------------------------------------------------------------------------

_TRANSFORMS = {
    # Nothing changes, so nothing can be lost — the UNTOUCHED path.
    "identity": lambda t: t,
    # Same token count: the fast path updates CONTENT in place.
    "fast": lambda t: (
        t.partition(" ")[0].upper() + t.partition(" ")[1] + t.partition(" ")[2]
    ),
    # One more token: forces the slow-path rebuild, the only path with
    # anything real to drop.
    "slow": lambda t: (t + " zz") if t.strip() else t,
}


@pytest.mark.parametrize("name", ["sample.xml", "X0000002.xml"])
@pytest.mark.parametrize("path_kind", sorted(_TRANSFORMS))
def test_no_phantom_losses(name: str, path_kind: str) -> None:
    """R1 — the counters used to claim SUBS_TYPE/SUBS_CONTENT were dropped on
    every rebuilt String, while ``_apply_subs`` re-established both from the
    manifest on the very same pass. 229 phantom claims of each on one real
    566-line page."""
    path, out, losses = _rewrite(name, _TRANSFORMS[path_kind])
    assert_every_count_is_a_real_loss(path, out, losses)


# ---------------------------------------------------------------------------
# Direction 2: every real loss is COUNTED.  Open (R4) — pinned as xfail.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="R4 — ALTO drops WC (and CC) from every String whose CONTENT it "
    "rewrites, deliberately: the source engine's per-word confidence does not "
    "survive a correction. It is counted nowhere, while the PAGE rewriter "
    "does count its equivalent as conf_dropped. Measured here: 520 WC gone "
    "and 0 counted on examples/X0000002.xml through the FAST path alone, "
    "3339 through the slow one. Whether that is a 'loss', an 'invalidation' "
    "or a 'recalculation' is exactly what the R0 matrix has to settle before "
    "a counter is added — so this lands as an executable statement of the "
    "gap, not as a guess at the answer.",
)
@pytest.mark.parametrize("name", ["sample.xml", "X0000002.xml"])
@pytest.mark.parametrize("path_kind", ["fast", "slow"])
def test_every_real_loss_is_counted(name: str, path_kind: str) -> None:
    path, out, losses = _rewrite(name, _TRANSFORMS[path_kind])
    assert_every_real_loss_is_counted(path, out, losses)


def test_an_identity_rewrite_loses_nothing_at_all() -> None:
    """The one case where both directions already hold: the UNTOUCHED path
    does not modify the tree, so neither counter can be wrong."""
    for name in ("sample.xml", "X0000002.xml"):
        path, out, losses = _rewrite(name, _TRANSFORMS["identity"])
        assert_every_count_is_a_real_loss(path, out, losses)
        assert_every_real_loss_is_counted(path, out, losses)


def test_the_invariant_catches_a_phantom() -> None:
    """Guard the guard."""
    src = _EXAMPLES / "sample.xml"
    _, out, _ = _rewrite("sample.xml", _TRANSFORMS["identity"])
    line_id = next(iter(_lines_by_id(src)[0]))
    with pytest.raises(AssertionError, match="phantom"):
        assert_every_count_is_a_real_loss(src, out, {line_id: {"subs_type_dropped": 3}})


def test_the_invariant_catches_an_uncounted_loss() -> None:
    """Guard the other guard: strip an attribute the report says nothing
    about, and the second direction must complain. WIDTH, because every
    String in the fixture carries one."""
    src = _EXAMPLES / "sample.xml"
    pages, _ = parse_alto_file(src, src.name)
    for page in pages:
        for lm in page.lines:
            lm.corrected_text = lm.ocr_text
            lm.status = LineStatus.CORRECTED
    out = rewrite_alto_file(src, pages, "test", "mock").xml_bytes

    root = etree.fromstring(out)
    ns = _detect_namespace(root)
    for string_el in root.iter(f"{{{ns}}}String" if ns else "String"):
        string_el.attrib.pop("WIDTH", None)
    stripped = etree.tostring(root)

    with pytest.raises(AssertionError, match="disappeared from the rewritten"):
        assert_every_real_loss_is_counted(src, stripped, {})
