"""One call per page, and not one line's text on another line's line.

Page-aligned mode trades the per-line JSON contract for position: 28 calls
instead of ~2 000, `$0.14` instead of `$1.11`, because the line-keyed envelope
carries `prev_text` and `next_text` with every line and so sends each line's
text three times.

What it buys back has to be paid exactly once, and this is where. The answer
has no line ids. If the mapping is recovered wrongly, the file says something
the scan does not, on a line nobody flagged — worse than never correcting.

So these tests are all one property under different pressures: **an edit is
emitted only where the alignment vouched for the line**, and everything else
keeps its OCR text.
"""

from __future__ import annotations

import pytest

from saknussemm.core.protocols import ProducerOptions
from saknussemm.core.schemas import CorrectionRequest, LineContext
from saknussemm.errors import ProposalValidationError
from saknussemm.producers.page_llm import PageLLMEditProducer


class _Answers:
    """A provider returning a fixed page, and recording what it was asked."""

    def __init__(self, lines: object) -> None:
        self._lines = lines
        self.payloads: list[dict] = []

    async def complete_structured(self, **kwargs):
        self.payloads.append(kwargs["user_payload"])
        return {"lines": self._lines} if isinstance(
            self._lines, list
        ) else self._lines, None


def _request(*texts: str) -> CorrectionRequest:
    return CorrectionRequest(
        document_id="D1",
        page_id="P1",
        granularity="page",
        lines=[
            LineContext(line_id=f"L{i}", ocr_text=text) for i, text in enumerate(texts)
        ],
    )


def _producer(answer: object) -> tuple[PageLLMEditProducer, _Answers]:
    provider = _Answers(answer)
    return PageLLMEditProducer(provider, "k", "m"), provider


async def _run(answer: object, *texts: str):
    producer, provider = _producer(answer)
    script, _ = await producer.produce(
        _request(*texts), options=ProducerOptions(temperature=0.0)
    )
    return script, provider


@pytest.mark.asyncio
async def test_the_envelope_carries_the_text_once() -> None:
    """The whole economic argument, asserted rather than claimed.

    A payload that grew back into the per-line contract — ids, neighbours —
    would keep the alignment risk and give up the saving that justifies it.
    """
    _, provider = await _run(
        ["le chat dort", "sur le tapis"], "le chat dort", "sur le tapis"
    )
    assert provider.payloads == [{"lines": ["le chat dort", "sur le tapis"]}]


@pytest.mark.asyncio
async def test_a_corrected_page_edits_the_lines_that_changed() -> None:
    script, _ = await _run(
        ["le roi de France", "vive le roi"], "le roi de Frauce", "vive le roi"
    )
    assert [(op.line_id, op.text) for op in script.ops] == [("L0", "le roi de France")]


@pytest.mark.asyncio
async def test_a_merged_page_edits_NEITHER_line() -> None:
    """The failure the mode exists for, at the producer's level.

    A model that folds two lines into one leaves both unvouched: the swallowed
    line has no answer, and the surviving one must not receive the merged text
    — that is a line getting its neighbour's words. Both keep their OCR, which
    the engine already knows how to report.
    """
    script, _ = await _run(
        ["premier vers ici deuxieme vers la", "troisieme vers bas"],
        "premier vers ici",
        "deuxieme vers la",
        "troisieme vers bas",
    )
    assert [op.line_id for op in script.ops] == [], script.ops


@pytest.mark.asyncio
async def test_a_line_the_alignment_declines_simply_gets_no_edit() -> None:
    """No op is not an error: it is the engine's own word for "kept the OCR".

    `requires_full_coverage` is False for exactly this. Declared True, the
    1.6% of lines the alignment will not settle on a real page would become
    validator errors and fail the whole page.
    """
    script, _ = await _run(
        ["alpha bravo charlie", "zoulou yankee xray"],
        "alpha bravo charlie",
        "delta echo foxtrot",
    )
    assert [op.line_id for op in script.ops] == []
    assert PageLLMEditProducer.requires_full_coverage is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        {"lignes": ["a"]},  # wrong key
        {"lines": "a"},  # not a list
        {"lines": [1, 2]},  # not strings
        "not a dict at all",
    ],
)
async def test_a_malformed_page_is_a_retryable_failure_not_zero_edits(answer) -> None:
    """Turning a broken answer into "no edits" would report a clean run.

    The run would say every line was left alone, which is what a *good* run
    looks like when the page needed nothing. The two must not be
    indistinguishable, so this goes down the pipeline's malformed-output path
    — retried, then counted.
    """
    with pytest.raises(ProposalValidationError):
        await _run(answer, "le chat dort")


@pytest.mark.asyncio
async def test_a_reordered_page_is_refused_rather_than_approximated() -> None:
    """Band exhaustion means position stopped identifying a line.

    There is no safe partial reading of that page: whatever the alignment
    returns is the best DIAGONAL answer, not the best answer. Refusing sends
    it back through the retry machinery instead of writing a guess.
    """
    head = [f"alpha{i} beta{i} gamma{i}" for i in range(30)]
    tail = [f"omega{i} psi{i} chi{i}" for i in range(30)]
    producer, _ = _producer(tail + head)
    producer._line_band = 3
    with pytest.raises(ProposalValidationError, match="band"):
        await producer.produce(
            _request(*(head + tail)), options=ProducerOptions(temperature=0.0)
        )


@pytest.mark.asyncio
async def test_an_unchanged_page_emits_nothing() -> None:
    """No edit for a line the model returned identical — the run's own idea
    of "untouched", reached without a special case."""
    script, _ = await _run(["le chat dort"], "le chat dort")
    assert script.ops == []
