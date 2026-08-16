"""What the library writes, the library reads back unchanged.

A metamorphic property (`T1`): correct a document, feed the delivered file
back in as the source, and ask for the same corrections again. The second
pass has nothing left to decide — every line already carries the text it
would propose — so it must hand back the same file.

The transformation is not exotic. It is what a host does on the second run
of a pipeline it re-ran, and what a user does by dropping the output of one
job into the next. Nothing in the contract makes a corrected file a
second-class input, so a round trip through the library's own rewriter has
to be a fixed point.

**What it reaches that the existing byte-stability tests do not.**
``test_rewriter_byte_stability`` pins the UNTOUCHED path over the ORIGINAL
file: a line nobody corrected keeps its bytes. This one starts on the other
side — the lines it re-reads are exactly the ones the rewriter REBUILT, with
their ``String``/``SP``/``HYP`` children re-emitted and their token widths
redistributed. Nothing else parses that output back. If the rewriter emits
markup the parser reconstructs differently — one ``SP`` short, a hyphen
absorbed, a token split elsewhere — the second pass sees a line that no
longer says what was decided, corrects it again, and the file moves. The
corrections below are therefore ABSOLUTE strings, not "append to whatever
you find": that is what makes the second pass able to disagree.

**The one legitimate difference, asserted rather than ignored.** Each run
records itself in ``Description``: two passes leave two
``postProcessingStep`` elements, and that is the point of a provenance
record. So the comparison strips them and counts them separately — a test
that compared raw bytes would have to be told to expect a difference, which
is how a real drift gets waved through.

**Which assertion carries the weight**, measured by mutation rather than
assumed. Making the rewriter reuse the previous run's
``postProcessingStep`` instead of appending — a plausible "don't duplicate
the record" tidy-up, and a silent loss of the first run's provenance — left
the **entire rest of the suite green**; only the count below moved.
``test_provenance`` checks that ONE pass writes ONE step, which is a
different sentence. The fixed-point assertion is the companion: it fires on
a markup mutation (an ``SP`` the rewriter fails to emit), but the projection
invariant catches that one inside a single pass too. Its own contribution is
the byte level — geometry, attributes, child order — which no text-level
invariant can see.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.formats.alto.parser import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import DictProvider, RecordingObserver

#: Both shipped fixtures: the small hand-made one and the real BnF page,
#: which carries explicit hyphenation and the confidence attributes the
#: rewriter has to redistribute.
_CORPORA = ("sample.xml", "X0000002.xml")

_PROVENANCE_TAG = "postProcessingStep"


def _corrections(path: Path, name: str) -> dict[str, str]:
    """Absolute target texts for the first few lines with something to say.

    Absolute, not relative: on the second pass these are compared against
    what the delivered file actually reads back as, so a round trip that
    lost a space produces a disagreement instead of quietly agreeing with
    itself.
    """
    source = build_document_manifest([(path, name)])
    return {
        lm.line_id: f"{lm.ocr_text} ajoute"
        for page in source.pages
        for lm in page.lines
        if len(lm.ocr_text.split()) > 3
    }


def _pass(path: Path, name: str, corrections: dict[str, str]) -> bytes:
    document = build_document_manifest([(path, name)])
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(corrections),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
    )
    result = pipeline.run_sync(document_manifest=document, source_files={name: path})
    return result.corrected_files[name]


def _without_provenance(xml: bytes) -> tuple[bytes, int]:
    """The document minus its run records, and how many it carried."""
    root = etree.fromstring(xml)
    removed = 0
    for element in list(root.iter()):
        if not isinstance(element.tag, str):  # comments, PIs
            continue
        if etree.QName(element).localname == _PROVENANCE_TAG:
            parent = element.getparent()
            assert parent is not None
            parent.remove(element)
            removed += 1
    return etree.tostring(root), removed


def _two_passes(tmp_path: Path, corpus: str) -> tuple[bytes, bytes]:
    source = EXAMPLES / corpus
    corrections = _corrections(source, corpus)

    first = _pass(source, corpus, corrections)
    intermediate = tmp_path / corpus
    intermediate.parent.mkdir(parents=True, exist_ok=True)
    intermediate.write_bytes(first)
    second = _pass(intermediate, corpus, corrections)
    return first, second


def test_the_second_pass_returns_the_first_pass(tmp_path: Path) -> None:
    for corpus in _CORPORA:
        first, second = _two_passes(tmp_path / corpus, corpus)
        stripped_first, _ = _without_provenance(first)
        stripped_second, _ = _without_provenance(second)
        assert stripped_first == stripped_second, (
            f"{corpus}: running the library on its own output moved the "
            "file. Everything but the run record must be a fixed point — a "
            "difference here means the rewriter emits markup the parser "
            "reads back as something else, and the drift compounds with "
            "every pass."
        )


def test_the_second_pass_records_itself(tmp_path: Path) -> None:
    """The difference the strip above hides, asserted instead of assumed."""
    for corpus in _CORPORA:
        first, second = _two_passes(tmp_path / corpus, corpus)
        _, in_first = _without_provenance(first)
        _, in_second = _without_provenance(second)
        assert (in_first, in_second) == (1, 2), (
            f"{corpus}: expected one run record after one pass and two "
            f"after two, got {in_first} then {in_second}. §11 provenance is "
            "the one thing a second pass is supposed to add; if it stopped, "
            "the fixed-point assertion above is comparing two files that "
            "forgot they were corrected."
        )


def test_the_first_pass_really_rewrote_lines(tmp_path: Path) -> None:
    """Otherwise both passes took the UNTOUCHED path and prove nothing.

    The property is only about lines the rewriter REBUILT. If the first
    pass corrects nothing, the second pass re-reads an untouched file and
    the fixed point is trivial.
    """
    for corpus in _CORPORA:
        source = EXAMPLES / corpus
        first = _pass(source, corpus, _corrections(source, corpus))

        delivered = tmp_path / f"delivered-{corpus}"
        delivered.parent.mkdir(parents=True, exist_ok=True)
        delivered.write_bytes(first)

        rebuilt = sum(
            1
            for page in build_document_manifest([(delivered, corpus)]).pages
            for lm in page.lines
            if lm.ocr_text.endswith(" ajoute")
        )
        assert rebuilt >= 3, (
            f"{corpus}: only {rebuilt} line(s) came back rewritten — the "
            "corrections stopped landing, and the second pass has nothing "
            "the rewriter touched to re-read."
        )
