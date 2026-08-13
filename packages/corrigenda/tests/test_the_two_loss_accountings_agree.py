"""One event, one counter — checked across the report's two loss surfaces.

A differential property (`T3`), over a promise the contract makes in
writing. ``ProducerMetadata``'s sibling field says of ``losses_by_line``:

    per-line attribution of ``losses``: line_id → that line's own loss
    counters (only lines that lost something appear). **Summing the values
    reproduces** ``losses``.

Nothing verified it. The per-line numbers are checked against the delivered
XML by ``test_loss_accounting_is_real``, and the aggregate is checked for
being non-empty in places, but the two were never compared to each other —
which is the only check that catches them drifting apart.

That drift is the defect this repository has hit more than any other. `R1`
was two accounting sites for one event, free to diverge; `R5` was a
diagnostic riding in the loss dictionary so that summing the counters
counted a non-event; `R4` and `R8` were both closed by REFUSING to add a
second counter, on the reasoning that a number derivable from another
number will eventually disagree with it. When two surfaces publish the same
event anyway — as the report does, once aggregated and once per line — the
agreement has to be asserted rather than assumed.

The run below is a real one: four lines corrected so their word count
changes, which invalidates their OCR confidence and produces genuine,
countable losses. If it ever stops losing anything the test fails rather
than passing over an empty sum.
"""

from __future__ import annotations

import collections

from tests._pipeline_harness import run_pipeline

#: A document whose lines carry per-token confidences worth invalidating.
_CORPUS = "X0000002.xml"

#: How many lines the run must actually damage. Below this the sum is small
#: enough to agree by luck.
_MINIMUM_DAMAGED_LINES = 3


def _a_run_that_loses_something() -> object:
    """Correct a few lines in a way that changes their word count.

    A changed word count rebuilds the line, which invalidates the OCR
    confidence the source asserted about the old reading — a real loss, and
    one the matrix says is counted per line.
    """
    baseline = run_pipeline(_CORPUS, {})
    targets = [
        (outcome.line_id, outcome.source_text)
        for outcome in baseline.result.report.lines
        if outcome.source_text and len(outcome.source_text.split()) > 3
    ][:4]
    corrections = {line_id: f"{text} ajoute" for line_id, text in targets}
    return run_pipeline(_CORPUS, corrections).result.report


def test_the_per_line_losses_sum_to_the_aggregate() -> None:
    report = _a_run_that_loses_something()

    per_line: collections.Counter[str] = collections.Counter()
    for outcome in report.lines:
        if outcome.projection and outcome.projection.losses:
            per_line.update(outcome.projection.losses)

    assert report.format_losses == dict(per_line), (
        "the report's two loss surfaces disagree.\n"
        f"  aggregate: {report.format_losses}\n"
        f"  per line:  {dict(per_line)}\n"
        "The contract says summing the per-line attribution reproduces the "
        "aggregate. One event, one counter — two numbers for one event are "
        "free to drift, which is what `R1` was."
    )


def test_the_run_really_loses_something() -> None:
    """Otherwise the assertion above compares two empty dictionaries."""
    report = _a_run_that_loses_something()

    assert report.format_losses, (
        "the run lost nothing, so the agreement above is vacuous. Either "
        "the corrections stopped changing word counts, or the accounting "
        "stopped reporting — both are worth knowing."
    )
    damaged = [
        outcome.line_id
        for outcome in report.lines
        if outcome.projection and outcome.projection.losses
    ]
    assert len(damaged) >= _MINIMUM_DAMAGED_LINES, (
        f"only {len(damaged)} line(s) lost anything; the sum agrees too "
        "easily to be evidence. Expected at least "
        f"{_MINIMUM_DAMAGED_LINES}."
    )
