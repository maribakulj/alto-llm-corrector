"""A guard that refuses must say so, or its threshold cannot be tuned.

``EditRejection`` has carried thirteen reason codes since the edit protocol
landed, and until 2026-08-17 it had **no consumer outside the tests**. A
line whose only op was refused reported ``corrected``, with no reason,
``fallback_chunks`` at zero, and nothing anywhere counting the refusal.

So the report could not distinguish *the producer proposed nothing* from
*it proposed something the guards refused*. The refusal rate of `E1`–`E5`
was therefore not merely unmeasured: it was **unmeasurable**.

That is the practical problem, and it is worse than a missing statistic.
The default source-similarity gate reverts a line whose correction changed
more than about two thirds of its characters — which is exactly what a
legitimate correction looks like on badly degraded OCR, the corpus this
library exists for. A consumer could loosen that threshold on such a corpus
and measure no difference whatever the change did, because both outcomes
reported the same thing. **A guard whose effect is invisible cannot be
calibrated**, and `cinoc` sweeping a ``GuardConfig`` was steering blind.

The reason code is the part that makes it actionable rather than merely
informative: ``e5_hyphen`` and ``e4_line_budget`` firing on the same pages
call for opposite changes.

What this file does **not** fix: the line still reports ``corrected`` while
carrying its source text. That is the `L3`/`L9` shape, it needs the single
decision writer, and it is named as its own debt rather than smuggled in
here.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._pipeline_harness import RecordingObserver

#: A PART1 line whose boundary word a rule erases — refused by `E5`.
_ALTO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>'
    '<Page ID="P1" WIDTH="1000" HEIGHT="300"><PrintSpace>'
    '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="200">'
    '<TextLine ID="TL1" HPOS="0" VPOS="10" WIDTH="900" HEIGHT="40">'
    '<String ID="S1" CONTENT="Le" HPOS="0" VPOS="10" WIDTH="100" HEIGHT="40"/>'
    '<SP WIDTH="10" HPOS="100" VPOS="10"/>'
    '<String ID="S2" CONTENT="peuple" HPOS="110" VPOS="10" WIDTH="300" HEIGHT="40"/>'
    '<SP WIDTH="10" HPOS="410" VPOS="10"/>'
    '<String ID="S3" CONTENT="att" HPOS="420" VPOS="10" WIDTH="200" HEIGHT="40" '
    'SUBS_TYPE="HypPart1" SUBS_CONTENT="attendit"/>'
    '<HYP CONTENT="-" HPOS="620" VPOS="10" WIDTH="20" HEIGHT="40"/>'
    "</TextLine>"
    '<TextLine ID="TL2" HPOS="0" VPOS="60" WIDTH="900" HEIGHT="40">'
    '<String ID="S4" CONTENT="endit" HPOS="0" VPOS="60" WIDTH="200" HEIGHT="40" '
    'SUBS_TYPE="HypPart2" SUBS_CONTENT="attendit"/>'
    '<SP WIDTH="10" HPOS="200" VPOS="60"/>'
    '<String ID="S5" CONTENT="longtemps" HPOS="210" VPOS="60" WIDTH="400" HEIGHT="40"/>'
    "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
)


def _run(rules: list[SubstitutionRule]) -> object:
    directory = Path(tempfile.mkdtemp())
    path = directory / "refused.xml"
    path.write_text(_ALTO, encoding="utf-8")
    manifest = build_document_manifest([(path, path.name)])
    return CorrectionPipeline(
        producer=RulesProducer(rules), observer=RecordingObserver()
    ).run_sync(document_manifest=manifest, source_files={path.name: path})


def test_a_refused_op_is_named_with_its_page_line_and_reason() -> None:
    result = _run([SubstitutionRule("att", "")])
    refused = result.report.edit_rejections or []  # type: ignore[attr-defined]
    assert [(r.page_id, r.line_id, r.reason) for r in refused] == [
        ("P1", "TL1", "e5_hyphen")
    ], (
        f"the report says {refused} about a run whose only op was refused by "
        "E5. Thirteen reason codes existed with no consumer, so the report "
        "could not tell 'the producer proposed nothing' from 'it proposed "
        "something the guards refused' — which is what makes a GuardConfig "
        "impossible to tune."
    )


def test_the_page_is_named_and_not_only_the_line() -> None:
    """``line_id`` alone repeats across files (`ADR-007`).

    A refusal keyed on a bare line id would collapse two files' refusals
    into one row, and a bench counting per page would count wrong.
    """
    result = _run([SubstitutionRule("att", "")])
    refused = result.report.edit_rejections or []  # type: ignore[attr-defined]
    assert all(r.page_id for r in refused)


def test_a_run_that_refuses_nothing_says_nothing() -> None:
    """The field is absent rather than an empty list.

    Same convention as ``hyphen_splits``: an optional field that appears
    only when it has something to say, so a report is not padded with
    evidence of absence.
    """
    result = _run([SubstitutionRule("peuple", "peuples")])
    assert result.report.edit_rejections is None  # type: ignore[attr-defined]


def test_the_order_does_not_depend_on_execution() -> None:
    """Two runs over one document must produce the same report.

    ``hyphen_splits`` is accumulated in execution order and is on the list
    for `A7c` for exactly that reason; this field is sorted from the start
    so bounded concurrency does not make the report irreproducible.
    """
    first = _run([SubstitutionRule("att", "")])
    second = _run([SubstitutionRule("att", "")])
    assert (first.report.edit_rejections or []) == (  # type: ignore[attr-defined]
        second.report.edit_rejections or []  # type: ignore[attr-defined]
    )
