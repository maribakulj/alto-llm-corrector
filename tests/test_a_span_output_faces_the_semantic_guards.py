"""`E6a` — the guard matrix judges a span's OUTPUT, not just its shape.

The edit protocol has two layers of refusal and they check different things.
`E1`–`E5` live in ``apply_edit_script``: structural, and `E4`/`E5` measure
drift on the span itself. `E6` is the three-stage matrix in ``check_line``,
applied later by the pipeline, and it reads the FINISHED line — similarity to
its source, length ratio, neighbourhood.

``docs/promises.md`` graded this row **partial**, and precisely: "the semantic
stage is never exercised on a span's output". The structural half was covered
several times over; nothing ever built a span edit whose *result* a semantic
guard would refuse, so the sentence "the guards apply to text coming out of a
span" rested on reading the code rather than on running it.

The distinction matters because the two layers can disagree. A span may be
small, anchored correctly, and inside every drift bound — `E4` and `E5` see
nothing wrong — while the line it produces bears no resemblance to the one it
replaced. That is exactly the shape a hallucinating producer emits when it
rewrites a short line, and only the semantic stage can see it.

**Sensitivity measured, not assumed.** Short-circuiting ``check_line`` to
accept everything fails both tests below — the refusal one because nothing
is refused, the control one because the reasonable span then lands for the
wrong reason. Dropping ``min_source_similarity`` to 0 fails only the first,
which is the finer check: it says the refusal comes from *that* threshold
and not from some other stage that happens to fire on the same input.
"""

from __future__ import annotations

import pytest

from saknussemm.core.editing import EditScript, RangeAnchor, ReplaceSpan
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.protocols import ProducerMetadata, ProducerOptions
from saknussemm.core.schemas import CorrectionRequest, LineStatus, RetryPolicy, Usage
from saknussemm.formats.alto.parser import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import RecordingObserver

_SOURCE = EXAMPLES / "sample.xml"


class _RewritesEveryLineWithOneSpan:
    """One span per line, replacing all of it with unrelated text.

    Structurally impeccable: the anchor is in range, there is one op per line,
    no overlap, no newline. And the growth ratio is satisfied — the
    replacement is shorter than what it replaces — so `E4` has nothing to
    say. Only a guard that looks at what the line now MEANS can refuse it.
    """

    wants_geometry = False
    wants_image = False
    requires_full_coverage = False

    def __init__(self) -> None:
        self.metadata = ProducerMetadata(name="span-test", implementation="v1")

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        ops = [
            ReplaceSpan(
                line_id=line.line_id,
                anchor=RangeAnchor(start=0, end=len(line.ocr_text)),
                text="zzz qqq",
            )
            for line in payload.lines
            if len(line.ocr_text) > 8
        ]
        return EditScript(ops=list(ops)), None


class _EditsOneWordWithOneSpan:
    """The control: a span whose output any guard would accept.

    Without it, the refusal below could come from a pipeline that refuses
    every span, and the property would be the opposite of the one claimed.
    """

    wants_geometry = False
    wants_image = False
    requires_full_coverage = False

    def __init__(self) -> None:
        self.metadata = ProducerMetadata(name="span-test", implementation="v1")

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        ops = []
        for line in payload.lines:
            first = line.ocr_text.split(" ")[0]
            if len(first) < 3:
                continue
            ops.append(
                ReplaceSpan(
                    line_id=line.line_id,
                    anchor=RangeAnchor(start=0, end=len(first)),
                    # One character changed inside the first word: the
                    # smallest edit that is not the identity.
                    text=first[:-1] + ("x" if first[-1] != "x" else "y"),
                )
            )
        return EditScript(ops=list(ops)), None


async def _run(producer):
    document = build_document_manifest([(_SOURCE, _SOURCE.name)])
    pipeline = CorrectionPipeline(
        producer=producer,
        observer=RecordingObserver(),
        retry_policy=RetryPolicy(transient_backoff_base=0.0, output_backoff_base=0.0),
        producer_metadata=ProducerMetadata(name="span-test", implementation="v1"),
    )
    return await pipeline.run(
        document_manifest=document, source_files={_SOURCE.name: _SOURCE}
    )


@pytest.mark.asyncio
async def test_a_structurally_valid_span_can_still_be_refused_on_meaning() -> None:
    """The gap the promise named, closed by running it rather than reading it."""
    result = await _run(_RewritesEveryLineWithOneSpan())
    fallen = [d for d in result.decisions.decisions if d.status is LineStatus.FALLBACK]
    assert fallen, "a span rewriting whole lines must not reach the artefact"
    assert all(d.final_text == d.source_text for d in fallen)
    assert "too_different_from_source" in result.fallback_reasons, (
        f"refused, but not by the SEMANTIC stage: {result.fallback_reasons}"
    )


@pytest.mark.asyncio
async def test_a_reasonable_span_still_lands() -> None:
    """The control. Both halves are needed: one says the guard fires, the
    other says it is not simply refusing every span it sees."""
    result = await _run(_EditsOneWordWithOneSpan())
    corrected = [
        d for d in result.decisions.decisions if d.status is LineStatus.CORRECTED
    ]
    assert corrected, result.fallback_reasons
    assert any(d.final_text != d.source_text for d in corrected)
