"""The text the report claims the file carries, read back off the file.

A differential property (`T3`) over the one shortcut the engine takes on
purpose and documents in place. ``rewrite_alto_file`` ends with:

    the output texts are read off the very tree the bytes were just
    serialized from: the projection invariant verifies them **without a
    second full parse of the output**.

That is a sound optimisation and a real assumption: serializing a tree and
parsing the result back gives the same per-line text. Everything downstream
rests on it — ``ProjectionStage.extracted_text`` is what a host renders as
"what the file now says", and the projection invariant that guards the whole
run compares the decision against that same in-memory reading. If
serialization and parsing ever disagree, the guard and the preview are wrong
together, and in the same direction.

So this parses the delivered bytes — really parses them, through
``extract_output_texts``, the function the rewriter's own docstring says
"remains for round-trip checks over arbitrary ALTO bytes" and which the
pipeline no longer calls — and compares line by line.

**What it catches that the fidelity tests do not** — measured, not
supposed. ``test_projection_fidelity_report`` asserts a no-break space
survives by looking for it in ``outcome.projection.extracted_text``. That is
the report's claim about the file, checked against itself. Append
``.replace(b"\\xc2\\xa0", b" ")`` to the ``etree.tostring`` call — a
plausible "tidy up the odd whitespace" step, one expression, no new line —
and **every one of the 1407 other tests stays green** while every delivered
file has silently lost the character the run reports as intact. Only this
module goes red.

That is the shape of the gap: nothing else in the suite reads a per-line
text back out of the bytes that are actually handed to the caller.

The fixture therefore carries the two things the shortcut is most exposed
to: a character that must survive a byte-level round trip intact (U+00A0),
and lines whose word count changed, which sends them down the slow path
where the ``String``/``SP`` children are rebuilt rather than edited in
place.
"""

from __future__ import annotations

from corrigenda.core.schemas import HyphenRole
from corrigenda.formats.alto.parser import build_document_manifest
from corrigenda.formats.alto.rewriter import extract_output_texts

from tests._paths import EXAMPLES
from tests._pipeline_harness import PipelineRun, run_pipeline

#: The small hand-made fixture and the real BnF page — the second carries
#: explicit hyphenation and per-token confidences, so its slow-path
#: rebuilds have more to get wrong.
_CORPORA = ("sample.xml", "X0000002.xml")

NBSP = " "

#: Lines the run must send down the slow path — the path that rebuilds
#: ``String``/``SP`` children instead of editing CONTENT in place, and the
#: one with the most to lose in a round trip. Two, because ``sample.xml``
#: only has four correctable non-hyphen lines and the NBSP turns the first
#: two into fast-path rewrites (merging two words into one token, so the
#: added word leaves the count unchanged). The BnF page contributes
#: hundreds.
_MINIMUM_REBUILT = 2


def _corrections(corpus: str) -> dict[str, str]:
    """Word-count changes everywhere, and a no-break space on the first two.

    The added word forces the slow path; the NBSP is the character the
    format CAN carry and a byte-level round trip could still lose.

    Hyphen members are left alone deliberately. Appending a word to a
    PART1 line breaks the join against its recorded ``SUBS_CONTENT``, the
    reconciler reverts the pair, and the line ends up UNTOUCHED — the one
    path this property has nothing to say about.
    """
    source = build_document_manifest([(EXAMPLES / corpus, corpus)])
    lines = [
        (lm.line_id, lm.ocr_text)
        for page in source.pages
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


def _run(corpus: str) -> PipelineRun:
    return run_pipeline(corpus, _corrections(corpus))


def _claimed_and_real(run: PipelineRun, corpus: str) -> tuple[dict, dict]:
    claimed = {
        outcome.line_id: outcome.projection.extracted_text
        for outcome in run.result.report.lines
        if outcome.projection is not None
    }
    real = extract_output_texts(run.result.corrected_files[corpus], set(claimed))
    return claimed, real


def test_the_report_describes_the_delivered_bytes() -> None:
    for corpus in _CORPORA:
        claimed, real = _claimed_and_real(_run(corpus), corpus)
        disagree = {
            line_id: (text, real.get(line_id))
            for line_id, text in claimed.items()
            if real.get(line_id) != text
        }
        assert not disagree, (
            f"{corpus}: the report says the file carries text the file does "
            f"not carry (report, file): {disagree}. ``extracted_text`` is "
            "read off the tree before serialization — if serializing and "
            "parsing back disagree, the preview a host renders and the "
            "invariant that guards the run are wrong together."
        )


def test_every_line_the_report_mentions_is_in_the_file() -> None:
    """A line the file lost would otherwise pass as agreement over nothing."""
    for corpus in _CORPORA:
        claimed, real = _claimed_and_real(_run(corpus), corpus)
        missing = sorted(set(claimed) - set(real))
        assert not missing, (
            f"{corpus}: the report describes line(s) absent from the "
            f"delivered file: {missing[:10]}. Line identity is the one thing "
            "a rewrite may never lose."
        )


def test_the_run_exercises_what_the_shortcut_risks() -> None:
    """Otherwise the agreement above is over lines nobody rebuilt.

    Two conditions, neither implied by the other: lines that went down the
    slow path — where ``String``/``SP`` children are re-emitted from
    scratch — and a no-break space that had to survive the byte round trip.
    """
    for corpus in _CORPORA:
        run = _run(corpus)
        rebuilt = [
            outcome.line_id
            for outcome in run.result.report.lines
            if outcome.projection is not None
            and outcome.projection.rewriter_path == "slow_path"
        ]
        assert len(rebuilt) >= _MINIMUM_REBUILT, (
            f"{corpus}: only {len(rebuilt)} line(s) took the slow path — "
            f"expected at least {_MINIMUM_REBUILT}. The corrections stopped "
            "changing word counts, and the comparison no longer covers the "
            "path that rebuilds a line."
        )

        _, real = _claimed_and_real(run, corpus)
        carrying = [line_id for line_id, text in real.items() if NBSP in text]
        assert carrying, (
            f"{corpus}: no delivered line carries a no-break space, so the "
            "one character this property exists to follow through "
            "serialization is not in the fixture any more."
        )
