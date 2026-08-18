"""The slow path welds a break mark to the word before it. Open defect.

Found by a real Mistral run over 20 Gallica newspaper pages on 2026-08-17:
one page produced **no output at all**, killed by ``ProjectionError``.

    rewritten XML for 'alto.xml' diverges from the run's decision on line
    'PAG_1_TL000441': decided 'à la révision des jugements et d -' but the
    artefact contains 'à la révision des jugements et d-'

The space between ``d`` and the break mark is gone, so the file says
something the run did not decide. Refusing to deliver is correct — the
projection invariant is doing its job. The defect is upstream of it.

**The shape that triggers it**, taken from the real line: an explicit
``HypPart1`` whose last ``String`` is the break mark itself, preceded by an
``<SP>``, with a ``<HYP>`` after it. The mark exists twice, as String and as
HYP — the case the 2026-07-21 double-hyphen fix addressed.

**Why only the slow path.** Measured, both arms:

    decided 'et d -'                same word count → fast path  → 'et d -'
    decided 'à la révision et d -'  more words      → slow path  → 'à la révision et d-'

**The mechanism, traced end to end.** ``_drop_structural_break_hyphen``
removes the trailing mark because ``<HYP>`` carries it structurally, and it
correctly leaves the space: ``'…et d -'`` becomes ``'…et d '``. The rebuild
then splits that into words, which discards the trailing space, lays out one
``String`` per word with ``<SP>`` between them, and appends the ``<HYP>``
directly after the last ``String``. Reading back gives ``'…et d' + '-'``.

**The fix, and why this file does not contain it.** The rebuild must emit a
trailing ``<SP>`` before the ``<HYP>`` when the write text ends in
whitespace — which is exactly what the source file had. That belongs inside
the geometry-aware layout, which reserves an end-of-line slot for the HYP and
redistributes token widths so the children sum to the line's WIDTH. Getting
it wrong writes bad geometry into a delivered file, which is worse than the
lost space. Landing the reproduction with the trace costs the next person
nothing and lets them fix it without repeating the investigation.

**When it is fixed, this file inverts**: the assertion below becomes
``assert delivered == decided`` and the docstring becomes history.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from saknussemm.core.schemas import LineStatus
from saknussemm.formats.alto.parser import parse_alto_file
from saknussemm.formats.alto.rewriter import extract_output_texts, rewrite_alto_file

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'

#: The real line's shape: `<SP>`, the break mark as its own String carrying
#: the SUBS, then `<HYP>`. Reduced only in the words before it.
_DOCUMENT = (
    f'<?xml version="1.0" encoding="UTF-8"?><alto {_NS}><Layout>'
    '<Page ID="P1" WIDTH="4000" HEIGHT="200"><PrintSpace>'
    '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="4000" HEIGHT="100">'
    '<TextLine ID="TL1" HPOS="0" VPOS="10" WIDTH="900" HEIGHT="40">'
    '<String ID="S1" CONTENT="et" HPOS="0" VPOS="10" WIDTH="60" HEIGHT="30"/>'
    '<SP HPOS="60" VPOS="10" WIDTH="20"/>'
    '<String ID="S2" CONTENT="d" HPOS="80" VPOS="10" WIDTH="30" HEIGHT="30"/>'
    '<SP HPOS="110" VPOS="10" WIDTH="33"/>'
    '<String ID="S3" CONTENT="-" HPOS="143" VPOS="10" WIDTH="7" HEIGHT="4" '
    'SUBS_TYPE="HypPart1" SUBS_CONTENT="demain"/>'
    '<HYP CONTENT="-" HPOS="150" VPOS="12" WIDTH="30"/>'
    "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
)


def _deliver(decided: str) -> str:
    path = Path(tempfile.mkdtemp()) / "w.xml"
    path.write_bytes(_DOCUMENT.encode("utf-8"))
    pages, _ = parse_alto_file(path, path.name)
    line = pages[0].lines[0]
    line.corrected_text = decided
    line.status = LineStatus.CORRECTED
    result = rewrite_alto_file(path, pages, "test", "mock")
    return extract_output_texts(result.xml_bytes, {"TL1"})["TL1"]


def test_the_fixture_is_the_shape_that_fails() -> None:
    """Guard the reproduction itself: an explicit PART1 with a doubled mark.

    If the parser stops seeing this as ``HypPart1``, or the fixture loses its
    ``<HYP>``, the case below would pass for a reason that has nothing to do
    with the defect.
    """
    path = Path(tempfile.mkdtemp()) / "w.xml"
    path.write_bytes(_DOCUMENT.encode("utf-8"))
    pages, _ = parse_alto_file(path, path.name)
    line = pages[0].lines[0]
    assert line.hyphen_role.value == "HypPart1", line.hyphen_role
    assert line.ocr_text == "et d -", repr(line.ocr_text)
    assert "<HYP" in _DOCUMENT


def test_the_fast_path_keeps_the_space() -> None:
    """The same line, same mark, unchanged word count — and it is correct.

    This is what says the defect is the REBUILD and not the hyphen handling:
    both paths drop the structural mark, only one loses the space.
    """
    assert _deliver("et d -") == "et d -"


def test_the_slow_path_welds_the_mark_OPEN_DEFECT() -> None:
    """Asserts the WRONG behaviour on purpose, so the day it changes is loud.

    A correction that adds words routes the line through the rebuild, and the
    space before the break mark does not survive. One real page died of this.

    Inverting this assertion is the fix's acceptance test.
    """
    decided = "à la révision et d -"
    delivered = _deliver(decided)
    assert delivered == "à la révision et d-", (
        f"the slow path delivered {delivered!r}. If it now equals {decided!r}, "
        "the defect is fixed — invert this assertion and rewrite the module "
        "docstring as history."
    )
    assert delivered != decided, "kept as the statement of what is wrong"
