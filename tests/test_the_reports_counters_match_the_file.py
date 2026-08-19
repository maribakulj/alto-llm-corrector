"""The report's COUNTERS must be re-derivable from the delivered file.

``docs/promises.md`` graded "the report says of the file what is in it" as
**partial**: contents and identities were guarded, counters were not. That is
the half a consumer actually reads. A dashboard shows "1 035 lines, 412
corrected, all exact"; nobody re-parses the XML to check, which is precisely
why nothing must be able to drift there quietly.

The three counters below are the ones an artefact can answer on its own, and
each is derived here from the delivered bytes rather than from the same
in-memory objects that produced the number — a counter checked against its own
source agrees with itself by construction, which is the failure mode this file
exists to avoid.

What is deliberately NOT checked this way: ``fallback_lines``. A fallen line
keeps its OCR text, and a *corrected* line can land on text identical to its
source, so the artefact cannot tell them apart — the decision set is the only
authority, and `test_status_truthfulness.py` is where that lives. Naming the
limit is part of the promise.

**Sensitivity measured on three mutations, each landing on its own
assertion** — which is what says the three are checking three things and not
one thing three times. Making ``total_lines`` count one less fails only the
first; skipping ``exact`` when tallying fidelity fails only the second;
dropping one entry from ``lines`` fails only the third.
"""

from __future__ import annotations

import pytest
from lxml import etree

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.formats.loader import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import DictProvider, RecordingObserver

_CORPORA = ("sample.xml", "X0000002.xml")


def _run(name: str):
    path = EXAMPLES / name
    document = build_document_manifest([(path, name)])
    # A correction on roughly one line in three, so the run has something to
    # count. Absolute texts, so the delivered file can disagree with them.
    corrections = {
        line.line_id: line.ocr_text.replace("e", "3")
        for index, page in enumerate(document.pages)
        for offset, line in enumerate(page.lines)
        if (index + offset) % 3 == 0 and "e" in line.ocr_text
    }
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(corrections),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
    )
    result = pipeline.run_sync(document_manifest=document, source_files={name: path})
    return result, result.corrected_files[name]


def _delivered_line_ids(xml: bytes) -> list[str]:
    root = etree.fromstring(xml)
    ns = root.tag.split("}")[0].strip("{")
    return [el.get("ID", "") for el in root.iter(f"{{{ns}}}TextLine") if el.get("ID")]


@pytest.mark.parametrize("name", _CORPORA)
def test_total_lines_counts_the_lines_the_file_has(name: str) -> None:
    """The headline number, counted off the artefact rather than the manifest."""
    result, xml = _run(name)
    assert result.report.total_lines == len(_delivered_line_ids(xml))


@pytest.mark.parametrize("name", _CORPORA)
def test_the_fidelity_levels_cover_every_line_exactly_once(name: str) -> None:
    """A level per written line, no more and no fewer.

    The scale grades how faithfully each rewritten line carries its decision.
    If the counts summed to less than the lines delivered, some line was
    written without ever being graded — which is the state the invariant
    exists to make impossible, and it would show up nowhere else.
    """
    result, xml = _run(name)
    levels = result.report.projection_fidelity or {}
    assert sum(levels.values()) == len(_delivered_line_ids(xml)), (
        f"{name}: {sum(levels.values())} graded lines for "
        f"{len(_delivered_line_ids(xml))} delivered ones — {levels}"
    )


@pytest.mark.parametrize("name", _CORPORA)
def test_every_reported_line_exists_in_the_file(name: str) -> None:
    """And the identities line up, not merely the totals.

    Two counts can agree while naming different lines. Comparing the SETS is
    what says the report is about this file rather than about a file with the
    same number of lines.
    """
    result, xml = _run(name)
    reported = {outcome.line_id for outcome in result.report.lines}
    assert reported == set(_delivered_line_ids(xml))


@pytest.mark.parametrize("name", _CORPORA)
def test_the_run_actually_corrected_something(name: str) -> None:
    """The premise. Every assertion above holds trivially on a run that
    changed nothing, so the fixture has to be doing work."""
    result, xml = _run(name)
    delivered = {outcome.line_id: outcome for outcome in result.report.lines}
    changed = [
        lid
        for lid, outcome in delivered.items()
        if outcome.decision.final_text != outcome.source_text
    ]
    total = len(delivered)
    assert len(changed) >= 2, f"{name}: only {len(changed)} lines changed"
    assert len(changed) / total >= 0.1, (
        f"{name}: {len(changed)}/{total} lines changed — too few for the "
        "assertions above to mean anything"
    )
