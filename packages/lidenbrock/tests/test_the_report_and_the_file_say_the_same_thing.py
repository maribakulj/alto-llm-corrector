"""The text the report claims the file carries, read back off the file.

A differential property (`T3`) over the one shortcut both writers take on
purpose and document in place. ``rewrite_alto_file`` ends with:

    the output texts are read off the very tree the bytes were just
    serialized from: the projection invariant verifies them **without a
    second full parse of the output**.

and ``rewrite_page_file`` says the same thing in its own words. That is a
sound optimisation and a real assumption: serializing a tree and parsing the
result back gives the same per-line text. Everything downstream rests on it
— ``ProjectionStage.extracted_text`` is what a host renders as "what the
file now says", and the projection invariant that guards the whole run
compares the decision against that same in-memory reading. If serialization
and parsing ever disagree, the guard and the preview are wrong together, and
in the same direction.

So this parses the delivered bytes — really parses them, through each
format's ``extract_output_texts``, the function the rewriters document as
remaining "for round-trip checks over arbitrary ALTO bytes" and which the
pipeline no longer calls — and compares line by line.

**What it catches that the fidelity tests do not** — measured, not
supposed. ``test_projection_fidelity_report`` asserts a no-break space
survives by looking for it in ``outcome.projection.extracted_text``. That is
the report's claim about the file, checked against itself. Append
``.replace(b"\\xc2\\xa0", b" ")`` to a rewriter's ``etree.tostring`` call — a
plausible "tidy up the odd whitespace" step, one expression, no new line —
and **every other test in the suite stays green** while every delivered file
has silently lost the character the run reports as intact. Only this module
goes red.

That is the shape of the gap: nothing else in the suite reads a per-line
text back out of the bytes that are actually handed to the caller.

**Both writers, one sentence.** The property is not about ALTO; it is about
what "the report describes the artefact" means, so it runs over every format
the library writes. Each has its own tree, its own serializer and its own
extractor, and a second implementation of a shortcut is where the first
one's assumptions stop being shared — so the measurement was repeated rather
than assumed to carry over. Mutating the ALTO writer: 1407 other tests
green. Mutating the PAGE writer, the same one-expression change: 1407 other
tests green. The gap was the same size on both sides.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lidenbrock import CorrectionPipeline
from lidenbrock.core.editing import EditScript, ReplaceLine
from lidenbrock.core.protocols import ProducerMetadata
from lidenbrock.core.schemas import DocumentManifest, HyphenRole
from lidenbrock.formats.alto.parser import (
    build_document_manifest as build_alto_manifest,
)
from lidenbrock.formats.alto.rewriter import extract_output_texts as extract_alto_texts
from lidenbrock.formats.page.parser import (
    build_document_manifest as build_page_manifest,
)
from lidenbrock.formats.page.rewriter import extract_output_texts as extract_page_texts

from tests._paths import EXAMPLES

#: Written as an escape, never as the character. A literal U+00A0 in a
#: source file is one reformat, one copy-paste or one careless rewrite away
#: from becoming an ordinary space — and if it does, every assertion below
#: that mentions it passes over nothing. That happened once while this
#: module was being widened: the character flattened, the fixture kept
#: running, and the guard meant to prevent exactly this went green because
#: ``" " in text`` is true of every line ever written.
NBSP = "\u00a0"

#: Lines each run must send down the slow path — the path that rebuilds a
#: line's children instead of editing its text in place, and the one with
#: the most to lose in a round trip. Two, because ``sample.xml`` only has
#: four correctable non-hyphen lines and the NBSP turns the first two into
#: fast-path rewrites (merging two words into one token, so the added word
#: leaves the count unchanged). The other three fixtures contribute more.
_MINIMUM_REBUILT = 2

_PAGE = EXAMPLES / "page"


@dataclass(frozen=True)
class _Format:
    """One writer, with the two functions that bracket it."""

    path: Path
    parse: Callable[[list[tuple[Path, str]]], DocumentManifest]
    extract: Callable[[bytes, set[str]], dict[str, str]]

    @property
    def name(self) -> str:
        return self.path.name


#: ALTO: the small hand-made fixture and the real BnF page, which carries
#: explicit hyphenation and per-token confidences. PAGE: two Gallica
#: transcriptions, whose ``¬`` breaks and ``custom`` offsets exercise a
#: rewriter that shares no code with the ALTO one.
_FORMATS = (
    _Format(EXAMPLES / "sample.xml", build_alto_manifest, extract_alto_texts),
    _Format(EXAMPLES / "X0000002.xml", build_alto_manifest, extract_alto_texts),
    _Format(
        _PAGE / "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
        build_page_manifest,
        extract_page_texts,
    ),
    _Format(
        _PAGE / "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
        build_page_manifest,
        extract_page_texts,
    ),
)


class _Silent:
    def on_event(self, *args: Any, **kwargs: Any) -> None:
        pass


class _Dictated:
    """An ``EditProducer`` that replaces exactly the lines it was given.

    ``requires_full_coverage = False`` is the deterministic-producer
    declaration (``core/attempt.py``): no op means no edit, and the engine
    fills the uncovered lines with their canonical text rather than
    treating the gap as a dropped LLM answer. Without it every chunk fails
    the 1:1 count check, retries, and falls back — which is what a first
    version of this fixture did, silently testing nothing but the fallback
    path.
    """

    requires_full_coverage = False

    def __init__(self, corrections: dict[str, str]) -> None:
        self.corrections = corrections

    async def produce(self, payload: Any, *, options: Any) -> tuple[EditScript, None]:
        return (
            EditScript(
                ops=[
                    ReplaceLine(
                        line_id=line.line_id, text=self.corrections[line.line_id]
                    )
                    for line in payload.lines
                    if line.line_id in self.corrections
                ]
            ),
            None,
        )


def _corrections(document: DocumentManifest) -> dict[str, str]:
    """Word-count changes everywhere, and a no-break space on the first two.

    The added word forces the slow path; the NBSP is the character the
    format CAN carry and a byte-level round trip could still lose.

    Hyphen members are left alone deliberately. Appending a word to a PART1
    line breaks the join against its recorded break content, the reconciler
    reverts the pair, and the line ends up UNTOUCHED — the one path this
    property has nothing to say about.
    """
    lines = [
        (lm.line_id, lm.ocr_text)
        for page in document.pages
        for lm in page.lines
        if len(lm.ocr_text.split()) > 3 and lm.hyphen_role is HyphenRole.NONE
    ]
    corrections = {}
    for index, (line_id, text) in enumerate(lines):
        corrected = f"{text} ajoute"
        if index < 2:
            corrected = corrected.replace(" ", NBSP, 1)
        corrections[line_id] = corrected
    return corrections


def _run(fmt: _Format) -> Any:
    document = fmt.parse([(fmt.path, fmt.name)])
    pipeline = CorrectionPipeline(
        producer=_Dictated(_corrections(document)),
        observer=_Silent(),
        producer_metadata=ProducerMetadata(name="dictated", implementation="test"),
    )
    return asyncio.run(
        pipeline.run(document_manifest=document, source_files={fmt.name: fmt.path})
    )


def _claimed_and_real(fmt: _Format) -> tuple[dict[str, str], dict[str, str], Any]:
    result = _run(fmt)
    claimed = {
        outcome.line_id: outcome.projection.extracted_text
        for outcome in result.report.lines
        if outcome.projection is not None
    }
    real = fmt.extract(result.corrected_files[fmt.name], set(claimed))
    return claimed, real, result


def test_the_report_describes_the_delivered_bytes() -> None:
    for fmt in _FORMATS:
        claimed, real, _ = _claimed_and_real(fmt)
        disagree = {
            line_id: (text, real.get(line_id))
            for line_id, text in claimed.items()
            if real.get(line_id) != text
        }
        assert not disagree, (
            f"{fmt.name}: the report says the file carries text the file "
            f"does not carry (report, file): {disagree}. ``extracted_text`` "
            "is read off the tree before serialization — if serializing and "
            "parsing back disagree, the preview a host renders and the "
            "invariant that guards the run are wrong together."
        )


def test_every_line_the_report_mentions_is_in_the_file() -> None:
    """A line the file lost would otherwise pass as agreement over nothing."""
    for fmt in _FORMATS:
        claimed, real, _ = _claimed_and_real(fmt)
        missing = sorted(set(claimed) - set(real))
        assert not missing, (
            f"{fmt.name}: the report describes line(s) absent from the "
            f"delivered file: {missing[:10]}. Line identity is the one thing "
            "a rewrite may never lose."
        )


def test_every_run_exercises_what_the_shortcut_risks() -> None:
    """Otherwise the agreement above is over lines nobody rebuilt.

    Two conditions per fixture, neither implied by the other: lines that
    went down the slow path — where a line's children are re-emitted from
    scratch — and a no-break space that had to survive the byte round trip.
    """
    for fmt in _FORMATS:
        _, real, result = _claimed_and_real(fmt)
        rebuilt = [
            outcome.line_id
            for outcome in result.report.lines
            if outcome.projection is not None
            and outcome.projection.rewriter_path == "slow_path"
        ]
        assert len(rebuilt) >= _MINIMUM_REBUILT, (
            f"{fmt.name}: only {len(rebuilt)} line(s) took the slow path — "
            f"expected at least {_MINIMUM_REBUILT}. The corrections stopped "
            "changing word counts, and the comparison no longer covers the "
            "path that rebuilds a line."
        )

        carrying = [line_id for line_id, text in real.items() if NBSP in text]
        assert carrying, (
            f"{fmt.name}: no delivered line carries a no-break space, so the "
            "one character this property exists to follow through "
            "serialization is not in the fixture any more."
        )
