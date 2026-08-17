"""Replaying the published edit script must reproduce the delivered file.

`core/report.py` states it plainly: the ``EditScript`` a run publishes is
the one it **actually applied**, and it therefore *never* carries an op for
a line reverted to OCR or reconciled to different text — because a consumer
replaying it would otherwise diverge from the pipeline's own corrected XML.

That promise was marked **closed** in `docs/promises.md` on 2026-08-16, by
me. It was false, and the audit of 2026-08-17 measured it:

    delivered   TL1 = 'Le peuple att-'
    published   [replace_span TL1 [10,13) -> '']
    replayed    {'TL1': 'Le peuple -'}

Two failures composed. ``_script_to_raw`` applied the span ops and **threw
away** the refusals; then, for a producer that does not require full
coverage, the uncovered line was filled with its canonical text — so the
report saw ``produced == final``, concluded the op had survived every
guard, and published it.

**Why the existing test stayed green.** It drives the pipeline through a
``DictProvider``, a producer that emits whole-line ops only. The path
"span op refused" is never entered, so the property was verified on the
one shape that cannot exhibit it. The corpus of producers was the blind
spot, not the assertion.

The line also reported ``corrected`` while carrying its source text — a
second, separate lie, and one this file does not fix. Making a refusal
visible in the report is `A2b`; this is `A2c`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from saknussemm.core.editing import apply_edit_script
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._pipeline_harness import RecordingObserver

#: A PART1 line whose boundary word a rule erases — refused by `E5` since
#: `A1b`. A rules producer is the point: it declares
#: ``requires_full_coverage = False``, which is the branch that filled the
#: refused line with canonical text and made the refusal look like success.
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


def _run_with_a_refused_span() -> tuple[object, dict[str, str]]:
    """``(result, {line_id: canonical text})`` after a run whose op is refused."""
    directory = Path(tempfile.mkdtemp())
    path = directory / "refused.xml"
    path.write_text(_ALTO, encoding="utf-8")
    manifest = build_document_manifest([(path, path.name)])
    canonical = {
        line.line_id: line.ocr_text for page in manifest.pages for line in page.lines
    }
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("att", "")]),
        observer=RecordingObserver(),
    ).run_sync(document_manifest=manifest, source_files={path.name: path})
    return result, canonical


def test_the_op_is_really_refused_and_the_line_really_unchanged() -> None:
    """Otherwise the assertions below hold over a run with nothing to publish.

    Both halves matter. If the rule did not fire there would be no op; if
    the guard did not refuse it there would be nothing wrongly published.
    """
    result, canonical = _run_with_a_refused_span()
    delivered = {
        outcome.line_id: outcome.decision.final_text
        for outcome in result.report.lines  # type: ignore[attr-defined]
    }
    assert delivered["TL1"] == canonical["TL1"] == "Le peuple att-", (
        f"expected the refused op to leave TL1 at its source text, got "
        f"{delivered['TL1']!r}"
    )


def test_replaying_the_published_script_reproduces_the_delivered_text() -> None:
    """The promise itself, asserted as a replay rather than as an absence.

    Checking "the refused op is not in the list" would pass on a run that
    published nothing for the wrong reason. Replaying is what a consumer
    actually does, and it is the only form of the property that cannot be
    satisfied by accident.
    """
    result, canonical = _run_with_a_refused_span()
    replayed = dict(canonical)
    replayed.update(apply_edit_script(result.edit_script, canonical).text_by_id)  # type: ignore[attr-defined]
    delivered = {
        outcome.line_id: outcome.decision.final_text
        for outcome in result.report.lines  # type: ignore[attr-defined]
    }
    assert replayed == delivered, (
        f"a consumer replaying the published script gets {replayed} where the "
        f"run delivered {delivered}. The script is documented as the one the "
        "run actually applied; an op the guards refused produced nothing, so "
        "publishing it hands the consumer a different document."
    )
