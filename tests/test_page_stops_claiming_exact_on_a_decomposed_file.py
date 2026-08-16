"""`exact` must not be claimed on a PAGE file the run spells differently.

``EXACT`` promises the strongest thing the fidelity scale can say: *the
artefact says the decision, character for character*. `L8` found that
promise broken on ALTO — 115 lines of the BnF fixture claimed it while the
file carried its break mark as U+00AD and the reconstruction read ``-``.
The remedy was not a stricter invariant but a SECOND READING:
``RewriteResult.texts_verbatim``, the same tree walk with the substitution
table switched off, plus a ``source_spelling`` level for "the file is right,
it just spells one character its own way".

**That remedy was never applied to PAGE**, on a reason written in the plan
and never rechecked: *PAGE substitutes nothing on read (NFC + strip)*.

NFC is a substitution. A file carrying ``e`` + U+0301 yields a decision
carrying U+00E9 — one codepoint where the file has two — and the two
readings differ exactly as they did on ALTO. NFD is not exotic: it is a
legitimate Unicode form and some producers emit it.

Measured on 2026-08-16, before the fix: the raw PAGE fixture
NFD-normalised, run through the pipeline, reported ``{'exact': 32}`` while
**9 of those 32 lines** were spelled differently in the file than in the
decision.

The fixture is derived rather than committed, and the derivation is the
point: NFD of a fixture already in the tree isolates one variable. A second
130 KB file would only hide which.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from saknussemm.core.schemas import ProjectionFidelity
from saknussemm.formats.loader import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import run_pipeline

_SOURCE = (
    EXAMPLES / "page/Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml"
)

#: Below this the file is not decomposed enough for the run to be evidence.
_MINIMUM_RESPELLED_LINES = 5


def _decomposed_copy() -> Path:
    """The same document, in NFD, beside the original so the harness finds it."""
    target = EXAMPLES / "_nfd_probe.page.xml"
    target.write_text(
        unicodedata.normalize("NFD", _SOURCE.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    return target


def _lines_the_file_spells_differently() -> int:
    """How many lines the parser reads in a form the file does not carry."""
    target = _decomposed_copy()
    try:
        doc = build_document_manifest([(target, target.name)])
        return sum(
            1
            for page in doc.pages
            for line in page.lines
            if line.ocr_text != unicodedata.normalize("NFD", line.ocr_text)
        )
    finally:
        target.unlink(missing_ok=True)


def test_the_fixture_really_is_respelled_by_the_read() -> None:
    """Otherwise the assertion below holds over a document with no accents."""
    respelled = _lines_the_file_spells_differently()
    assert respelled >= _MINIMUM_RESPELLED_LINES, (
        f"only {respelled} line(s) are read in a form the file does not "
        "carry; the run below would then be evidence of nothing."
    )


def test_a_decomposed_page_file_is_not_reported_as_exact() -> None:
    target = _decomposed_copy()
    try:
        report = run_pipeline(target.name, {}).result.report
    finally:
        target.unlink(missing_ok=True)

    levels = report.projection_fidelity or {}
    assert levels.get(str(ProjectionFidelity.EXACT.value), 0) < report.total_lines, (
        f"every line claims EXACT ({levels}), but the file spells several of "
        "them differently from the decision — the parser composes what the "
        "file leaves decomposed. EXACT promises character-for-character; "
        "this is the L8 defect, on the format its remedy never reached."
    )
    assert levels.get(str(ProjectionFidelity.SOURCE_SPELLING.value), 0) > 0, (
        "no line reports SOURCE_SPELLING. That level exists for exactly "
        "this: the file is right and spells a character its own way, "
        "nothing is lost, and the report should say so rather than claim "
        "an equality that does not hold."
    )
