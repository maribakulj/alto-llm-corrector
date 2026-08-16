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

from saknussemm.core.losses import (
    COUNTS_INVALIDATION,
    INVALIDATION_COUNTER,
    INVALIDATION_UNIT,
    AttributeClass,
    AttributeFate,
)
from saknussemm.formats.alto.losses import (
    ALTO_STRING_ATTRIBUTES,
    fate_of,
    is_countable_loss,
    is_invalidated,
)
from saknussemm.core.schemas import LineStatus
from saknussemm.formats.alto._ns import _detect_namespace
from saknussemm.formats.alto.parser import parse_alto_file
from saknussemm.formats.alto.rewriter import rewrite_alto_file

from tests._paths import EXAMPLES

_EXAMPLES = EXAMPLES

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
            if is_invalidated(attr):
                # Counted per line under its own key (R4), not per String —
                # ``assert_the_matrix_holds`` owns that check. Asking for
                # ``wc_dropped`` here would demand the unit the decision
                # rejected.
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
# Direction 2: the rewriter behaves as the MATRIX says (R0)
# ---------------------------------------------------------------------------
#
# The raw "every attribute that disappeared must be counted" statement was
# too blunt: it flagged CONTENT/ID/HPOS/... whenever a correction changed
# the token count, which is re-segmentation and not loss. The matrix draws
# that line — STRUCTURAL attributes follow the tokens, SEMANTIC ones carry
# an assertion about a reading — so the invariant can now say what it means.


def assert_the_matrix_holds(
    source: Path, output: bytes, losses_by_line: dict[str, dict[str, int]]
) -> None:
    """Every SEMANTIC attribute's observed fate matches its declared one."""
    src_lines, src_ns = _lines_by_id(source)
    out_lines, out_ns = _lines_by_id(output)

    for line_id, src_line in src_lines.items():
        before = _string_attr_counts(src_line, src_ns)
        after = _string_attr_counts(out_lines[line_id], out_ns)
        losses = losses_by_line.get(line_id, {})

        for attr, count in before.items():
            cls, fate = fate_of(attr)
            if cls is AttributeClass.STRUCTURAL:
                continue  # follows re-segmentation; not a loss channel
            gone = count - after[attr]

            if fate in (AttributeFate.PRESERVED, AttributeFate.REWRITTEN):
                assert gone <= 0, (
                    f"{line_id}: {attr.upper()} is declared {fate.value} but "
                    f"{gone} of {count} disappeared. Either the rewriter "
                    "regressed or the matrix is wrong — both are bugs."
                )
                continue

            if gone <= 0:
                continue
            if not is_countable_loss(attr):
                continue

            if fate is AttributeFate.INVALIDATED:
                # Counted in LINES (R4): the line reports it once however
                # many Strings carried it, under the key both formats share.
                assert losses.get(INVALIDATION_COUNTER, 0) == 1, (
                    f"{line_id}: {gone} × {attr.upper()} disappeared and the "
                    f"line reports {losses.get(INVALIDATION_COUNTER, 0)}. An "
                    f"{fate.value} attribute is counted once per line."
                )
                assert f"{attr}_dropped" not in losses, (
                    f"{line_id}: {attr.upper()} is counted twice — once per "
                    "line and once per String. That is R1's shape exactly."
                )
                continue

            assert losses.get(f"{attr}_dropped", 0) == gone, (
                f"{line_id}: {gone} × {attr.upper()} disappeared and the "
                f"report counts {losses.get(f'{attr}_dropped', 0)}. It is "
                f"declared {fate.value}, which the matrix says is counted."
            )


@pytest.mark.parametrize("name", ["sample.xml", "X0000002.xml"])
@pytest.mark.parametrize("path_kind", sorted(_TRANSFORMS))
def test_the_rewriter_obeys_the_loss_matrix(name: str, path_kind: str) -> None:
    path, out, losses = _rewrite(name, _TRANSFORMS[path_kind])
    assert_the_matrix_holds(path, out, losses)


def test_the_matrix_declares_every_attribute_the_fixtures_carry() -> None:
    """An attribute nobody classified defaults to SEMANTIC/DROPPED, which is
    the safe answer — but on the repo's own fixtures we should have made the
    call deliberately rather than fallen back to it."""
    seen: set[str] = set()
    for name in ("sample.xml", "X0000002.xml"):
        lines, ns = _lines_by_id(_EXAMPLES / name)
        for line in lines.values():
            seen |= set(_string_attr_counts(line, ns))

    undeclared = {a for a in seen if a.upper() not in ALTO_STRING_ATTRIBUTES}
    assert not undeclared, (
        f"{sorted(undeclared)} appear in the fixtures but are not in the "
        "matrix — they fall through to the DROPPED default, which is safe "
        "but undecided."
    )


def test_invalidation_is_counted_once_per_line_not_once_per_string() -> None:
    """R4, settled: counted, per LINE.

    The unit is the whole decision. Per occurrence this fires 3339 times on
    one real page — a number that varies with how wordy a line is rather
    than with anything an archive acts on, and that would drown the
    four-digit signals beside it. Per line it says the fact: *these* lines
    no longer carry the engine's confidence.

    So the assertion is deliberately two-sided. The counter must equal the
    number of lines that lost at least one ``WC``/``CC`` — not the number of
    attributes lost (that is the noise the decision rejected), and not zero
    (that was silence, and PAGE was not silent about the same event).
    """
    assert fate_of("WC") == (AttributeClass.SEMANTIC, AttributeFate.INVALIDATED)
    assert is_countable_loss("WC") is COUNTS_INVALIDATION is True
    assert INVALIDATION_UNIT == "line"

    path, out, losses = _rewrite("X0000002.xml", _TRANSFORMS["slow"])
    src, sns = _lines_by_id(path)
    dst, dns = _lines_by_id(out)

    lines_that_lost = 0
    attributes_lost = 0
    for line_id, el in src.items():
        before = _string_attr_counts(el, sns)
        after = _string_attr_counts(dst[line_id], dns)
        gone = sum(before[a] - after[a] for a in ("wc", "cc"))
        if gone > 0:
            lines_that_lost += 1
            attributes_lost += gone

    assert lines_that_lost > 0, "the fixture must exercise the invalidation"
    assert attributes_lost > lines_that_lost, (
        "fixture check: with one attribute per line the two units would be "
        "indistinguishable and this test would prove nothing"
    )

    counted = sum(v.get(INVALIDATION_COUNTER, 0) for v in losses.values())
    assert counted == lines_that_lost
    # Every line that reports it reports exactly 1 — a line cannot lose its
    # confidence twice.
    assert {
        v[INVALIDATION_COUNTER] for v in losses.values() if INVALIDATION_COUNTER in v
    } == {1}
    # And the per-String counter stays out of it: two sites counting one
    # attribute is the shape of R1.
    assert not any(k.startswith(("wc_", "cc_")) for v in losses.values() for k in v)


def test_a_line_that_keeps_its_confidence_reports_nothing() -> None:
    """The other direction. The fast path removes ``WC`` only from Strings
    whose CONTENT actually changed, so "the line took a write path" is not
    "the line lost confidence" — and the counter must follow the file, not
    the path."""
    path, out, losses = _rewrite("X0000002.xml", _TRANSFORMS["identity"])
    src, sns = _lines_by_id(path)
    dst, dns = _lines_by_id(out)
    for line_id, el in src.items():
        before = _string_attr_counts(el, sns)
        after = _string_attr_counts(dst[line_id], dns)
        if sum(before[a] - after[a] for a in ("wc", "cc")) == 0:
            assert INVALIDATION_COUNTER not in losses.get(line_id, {})


def test_both_formats_report_the_invalidation_under_one_key() -> None:
    """The parity half of R4 — the defect was not only silence, it was that
    ALTO said nothing while PAGE said ``conf_dropped``. One key, one unit,
    both formats; a consumer must not need to know which format produced a
    report to find out whether its OCR confidence survived."""
    from saknussemm.formats.page.rewriter import PageRewriterMetrics

    assert INVALIDATION_COUNTER in PageRewriterMetrics()._loss_counters()
    assert "conf_dropped" not in PageRewriterMetrics()._loss_counters()


def test_an_unknown_attribute_defaults_to_a_countable_loss() -> None:
    """A producer's dialect extension must surface in the report, not
    vanish on the assumption it did not matter."""
    cls, fate = fate_of("TAGREFS")
    assert (cls, fate) == (AttributeClass.SEMANTIC, AttributeFate.DROPPED)
    assert is_countable_loss("TAGREFS") is True


def test_an_identity_rewrite_loses_nothing_at_all() -> None:
    """The one case where every direction holds trivially: the UNTOUCHED
    path does not modify the tree."""
    for name in ("sample.xml", "X0000002.xml"):
        path, out, losses = _rewrite(name, _TRANSFORMS["identity"])
        assert_every_count_is_a_real_loss(path, out, losses)
        assert_every_real_loss_is_counted(path, out, losses)
        assert_the_matrix_holds(path, out, losses)


def test_the_invariant_catches_a_phantom() -> None:
    """Guard the guard."""
    src = _EXAMPLES / "sample.xml"
    _, out, _ = _rewrite("sample.xml", _TRANSFORMS["identity"])
    line_id = next(iter(_lines_by_id(src)[0]))
    with pytest.raises(AssertionError, match="phantom"):
        assert_every_count_is_a_real_loss(src, out, {line_id: {"subs_type_dropped": 3}})


def test_the_matrix_check_catches_a_preserved_attribute_going_missing() -> None:
    """Guard the other guard: strip a PRESERVED attribute and the matrix
    check must object — that is a regression, not a re-segmentation."""
    src = _EXAMPLES / "X0000002.xml"
    _, out, losses = _rewrite("X0000002.xml", _TRANSFORMS["identity"])

    root = etree.fromstring(out)
    ns = _detect_namespace(root)
    for string_el in root.iter(f"{{{ns}}}String" if ns else "String"):
        string_el.attrib.pop("STYLEREFS", None)

    with pytest.raises(AssertionError, match="declared preserved"):
        assert_the_matrix_holds(src, etree.tostring(root), losses)
