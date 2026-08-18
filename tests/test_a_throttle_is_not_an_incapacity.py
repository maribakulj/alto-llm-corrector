"""Being throttled and being unable are not the same failure.

Both end identically today: attempts run out, the chunk falls back, and the
report says ``all_attempts_exhausted``. They mean opposite things to whoever
reads that.

**Transport** — a 429, a dropped connection — means the model was never
asked. Asking again later works. **Malformed output** means the producer
answered and could not hold the contract; asking again changes nothing until
the producer does.

Measured on 2026-08-18, and this is why the distinction is worth carrying:
running three jobs against one rate-limited account turned sustained 429s
into chunk fallbacks, and the same page went from **67 % of lines corrected
to 37 %**. Every one of those failures was reported as the model failing. An
operator reading that concludes their model is bad and changes it, when what
they needed was to stop hammering their own quota.

The library already knows the difference — ``_RECOVERABLE_ERROR_TYPES`` is
built on it. It simply stopped travelling at the point the message was built,
which is the one line this fixes.
"""

from __future__ import annotations

import pytest

from saknussemm.core.attempt import _failure_family
from saknussemm.core.protocols import ProviderTransientError
from saknussemm.errors import ProposalValidationError


def test_a_rate_limit_is_named_as_transport() -> None:
    """The case that cost 30 points of correction rate and looked like the model."""
    assert (
        _failure_family(ProviderTransientError("429 Too Many Requests")) == "transport"
    )


@pytest.mark.parametrize(
    "exc",
    [
        ProposalValidationError("line count mismatch"),
        ValueError("not JSON"),
        __import__("json").JSONDecodeError("bad", "{", 0),
    ],
)
def test_a_producer_that_cannot_answer_is_named_as_such(exc: Exception) -> None:
    """The documented malformed-output family, whatever its exact class.

    `§8.4` keeps these value-shaped precisely so one route handles them; the
    label must follow the family, not the class name.
    """
    assert _failure_family(exc) == "producer_output"


def test_the_two_families_never_collide() -> None:
    """Guard the guard: a single label would make this file green and useless."""
    assert _failure_family(ProviderTransientError("x")) != _failure_family(
        ValueError("y")
    )


def test_the_family_reaches_the_report_an_operator_reads() -> None:
    """End of the wire, through the real pipeline.

    The label is only worth having if it survives into the fallback reason,
    because that string is what an operator actually reads when a run comes
    back with lines uncorrected. Driven through the public producer seam
    rather than by assembling a RunContext by hand: the point is what the
    report says, not what an internal returns.
    """
    from saknussemm.core.pipeline import CorrectionPipeline
    from saknussemm.formats.loader import build_document_manifest

    from tests._paths import EXAMPLES
    from tests._pipeline_harness import RecordingObserver

    class AlwaysThrottled:
        """A provider whose every call is refused by the vendor's rate limit."""

        requires_full_coverage = False

        async def produce(self, payload, *, options):  # noqa: ANN001, ANN202
            raise ProviderTransientError("429 Too Many Requests")

    path = EXAMPLES / "sample.xml"
    manifest = build_document_manifest([(path, path.name)])
    result = CorrectionPipeline(
        producer=AlwaysThrottled(), observer=RecordingObserver()
    ).run_sync(document_manifest=manifest, source_files={path.name: path})

    reasons = [
        line.decision.reason.detail or line.decision.reason.code
        for line in result.report.lines
        if line.decision.reason is not None
    ]
    assert reasons, "no line fell back, so the throttling never reached a report"
    assert any("transport" in reason for reason in reasons), (
        f"a rate-limited run reports {reasons[:2]} — an operator reading this "
        "cannot tell a saturated quota from a model that cannot answer, and "
        "will change the model."
    )
    assert any("429" in reason for reason in reasons), (
        "the vendor's own words must survive the labelling"
    )
