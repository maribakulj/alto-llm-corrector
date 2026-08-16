"""A line's STATUS must not contradict its own text (the L9 family).

L3 and L9 were the same defect twice, found one at a time: a line kept its
OCR text and was reported ``corrected``, so the loss reached no counter and
carried no reason. L3 was the cross-page hyphen head frozen on raw OCR; L9
was any pair the reconciler rejected for incoherence. Neither was found by
the suite — one needed an audit, the other fell out of writing a test for
the first.

Finding that family one member at a time is the wrong method. This file
states the invariant instead, so the next member fails a test rather than
waiting for someone to notice it:

    a line whose producer proposed something DIFFERENT, and whose final
    text is nevertheless its source text, has had a correction taken away
    from it — and must say ``fallback``.

An identity proposal is exempt: nothing was taken away, and ``corrected``
is the honest label for "the model agreed with the OCR". The invariant is
therefore about *discarded* work, not about text equality.

The mirror also holds and is cheaper to state: a ``fallback`` line must
carry its source text. A fallback that changed the text would be a
correction wearing the wrong label.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings

from saknussemm import CorrectionPipeline
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.core.schemas import CorrectionReport, RetryPolicy
from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._alto_gen import rich_alto_documents
from tests._pipeline_harness import DictProvider
from tests.test_properties_hypothesis import _write_tmp

from tests._paths import EXAMPLES

_EXAMPLES = EXAMPLES


class _Null:
    def on_event(self, *a, **k) -> None:
        pass


def assert_status_tells_the_truth(report: CorrectionReport) -> None:
    """The invariant, over any run's report."""
    for line in report.lines:
        proposed = line.proposal.output_text if line.proposal else None
        final = line.decision.final_text
        status = line.decision.status
        source = line.source_text

        if status == "fallback":
            assert final == source, (
                f"{line.page_id}/{line.line_id}: reported fallback but the "
                f"text changed — {source!r} -> {final!r}. A fallback keeps "
                "the source text; this is a correction wearing the wrong label."
            )
            continue

        if status != "corrected":
            continue  # failed / pending are not this invariant's business

        discarded = proposed is not None and proposed != source and final == source
        assert not discarded, (
            f"{line.page_id}/{line.line_id}: reported CORRECTED while "
            f"keeping its source text {source!r}, after the producer "
            f"proposed {proposed!r}. A correction was discarded and no "
            "counter or reason records it (L3/L9 family)."
        )


def _report_for(path: Path, corrections: dict[str, str]) -> CorrectionReport:
    doc = build_document_manifest([(path, path.name)])
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(corrections),
        api_key="k",
        model="m",
        observer=_Null(),
        retry_policy=RetryPolicy.deterministic(),
    )
    result = pipeline.run_sync(document_manifest=doc, source_files={path.name: path})
    return result.report


# ---------------------------------------------------------------------------
# Over the generated corpus — every structure the generator encodes
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(doc_and_roles=rich_alto_documents())
def test_status_never_lies_under_a_wholesale_substitution(doc_and_roles) -> None:
    """``e``→``3`` is the harshest cheap producer: it rewrites most lines and
    breaks the boundary join of most pairs, so it exercises accept, reject
    and reconcile-revert in one run."""
    doc, _ = doc_and_roles
    path = _write_tmp(doc)
    try:
        manifest = build_document_manifest([(path, path.name)])
        pipeline = CorrectionPipeline(
            producer=RulesProducer([SubstitutionRule("e", "3")]),
            observer=_Null(),
            producer_metadata=ProducerMetadata(name="rules", implementation="v1"),
        )
        result = pipeline.run_sync(
            document_manifest=manifest, source_files={path.name: path}
        )
        assert_status_tells_the_truth(result.report)
    finally:
        path.unlink(missing_ok=True)


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(doc_and_roles=rich_alto_documents())
def test_status_never_lies_when_the_producer_changes_nothing(doc_and_roles) -> None:
    """The identity pass: nothing is discarded, so nothing may report a
    discard — and no line may claim fallback either."""
    doc, _ = doc_and_roles
    path = _write_tmp(doc)
    try:
        report = _report_for(path, {})
        assert_status_tells_the_truth(report)
        assert all(ln.decision.status != "fallback" for ln in report.lines), (
            "an identity pass proposes nothing objectionable; a fallback here "
            "means a guard rejected the source text against itself"
        )
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Over the real fixtures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["sample.xml", "X0000002.xml"])
def test_status_never_lies_on_the_real_fixtures(name: str) -> None:
    path = _EXAMPLES / name
    doc = build_document_manifest([(path, path.name)])
    # A per-line correction that keeps word counts and boundary words
    # plausible: uppercase the FIRST word only. Wholesale substitution is
    # covered by the generated cases above.
    corrections = {
        lm.line_id: (
            lm.ocr_text.split(" ", 1)[0].upper()
            + (" " + lm.ocr_text.split(" ", 1)[1] if " " in lm.ocr_text else "")
        )
        for page in doc.pages
        for lm in page.lines
        if lm.ocr_text.strip()
    }
    report = _report_for(path, corrections)
    assert_status_tells_the_truth(report)


def test_the_invariant_actually_catches_the_l9_shape() -> None:
    """Guard the guard: a hand-built report with the L9 shape must fail.

    Without this, a bug in the assertion would make every case above pass
    vacuously — which is exactly how the family survived this long.
    """
    from saknussemm.core.schemas import DecisionStage, LineOutcome, ProposalStage

    bad = CorrectionReport(
        run_id="r",
        total_lines=1,
        lines=[
            LineOutcome(
                line_id="L1",
                page_id="P1",
                source_text="prati-",
                proposal=ProposalStage(input_text="prati-", output_text="prat1-"),
                decision=DecisionStage(status="corrected", final_text="prati-"),
            )
        ],
    )
    with pytest.raises(AssertionError, match="CORRECTED while keeping its source"):
        assert_status_tells_the_truth(bad)


def test_the_invariant_catches_a_fallback_that_changed_the_text() -> None:
    from saknussemm.core.schemas import DecisionStage, LineOutcome

    bad = CorrectionReport(
        run_id="r",
        total_lines=1,
        lines=[
            LineOutcome(
                line_id="L1",
                page_id="P1",
                source_text="prati-",
                decision=DecisionStage(status="fallback", final_text="prat1-"),
            )
        ],
    )
    with pytest.raises(AssertionError, match="reported fallback but the text changed"):
        assert_status_tells_the_truth(bad)
