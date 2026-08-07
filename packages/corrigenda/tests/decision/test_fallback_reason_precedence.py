"""Which reason survives when two passes revert the same line (ADR-013).

Characterisation: every assertion records what the code does TODAY, so
that `RM-01` — which moves all seven writes behind one entry point — can
prove it changed nothing it did not mean to.

The split looks arbitrary and is not. Four sites assign
``fallback_reason`` unconditionally (``_apply_line_acceptance`` × 3,
``_fall_back_to_source``); three defer behind ``if not
trace.fallback_reason`` (``_extend_to_units``, ``_refresh_pair_traces``,
``_apply_unit_reverts``). ADR-013 is why that is right, and it rests on
one invariant this file also pins, end to end and over real corpora:

  **I-1 — a line carrying a ``fallback_reason`` has already been
  reverted: its final text equals its source text.**

I-1 makes a second revert IDEMPOTENT on text. The pass that actually took
the correction away is therefore the first one, and deferring is what
keeps the recorded reason true rather than merely conservative — a
last-writer-wins rule would name a pass that changed nothing. And the
four assigning sites cannot collide at all: ``_apply_line_acceptance``
skips any line that already holds a decision, which is pinned below too.

An earlier note in the `RM` audit read this as a defect — "a
``token_realign`` gate reported as an ``adjacent_duplicate``, so
``fallback_reasons`` counts wrong". Checked against 756 decided lines
across six configurations, that is false, and the retraction is in
``docs/PLAN.md``. What was missing was never a fix; it was the invariant
that says the behaviour is correct.

When `RM-01` lands, the single writer must defer on ALL seven paths, and
these tests are how it proves the consumer-visible reason did not move.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path
from typing import Any

import pytest

from corrigenda.core.acceptance import _apply_line_acceptance, _apply_unit_reverts
from corrigenda.core.identity import line_ref
from corrigenda.core.outcome import _extend_to_units, _fall_back_to_source
from corrigenda.core.pipeline import CorrectionPipeline
from corrigenda.core.reconcile import _refresh_pair_traces
from corrigenda.core.schemas import (
    Coords,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineStatus,
    LossPolicy,
)
from corrigenda.formats.loader import build_document_manifest

from tests.decision._state import document, line

SRC = Path(__file__).parent.parent.parent / "src" / "corrigenda"
REPO = SRC.parent.parent.parent.parent
EXAMPLES = REPO / "examples"
CORPUS_GT = SRC.parent.parent / "tests" / "corpus_gt"


def _one_line(reason: str | None = None):
    lines = [line(1, "aaa", "AAA")]
    manifest, all_lines, traces = document(lines)
    if reason is not None:
        traces[line_ref(lines[0])].fallback_reason = reason
    return lines, all_lines, traces


def _linked_pair(partner_reason: str | None = None):
    """A PART1/PART2 unit, built as data — no pairing logic involved."""
    tail = line(1, "par-", "PAR-")
    head = line(2, "tir", "TIR")
    tail.hyphen_role = HyphenRole.PART1
    tail.hyphen_pair_line_id = head.line_id
    head.hyphen_role = HyphenRole.PART2
    head.hyphen_pair_line_id = tail.line_id
    manifest, all_lines, traces = document([tail, head])
    if partner_reason is not None:
        traces[line_ref(head)].fallback_reason = partner_reason
    return tail, head, all_lines, traces


# ---------------------------------------------------------------------------
# Sites 1-4 — the assigning writers, and why they never collide
# ---------------------------------------------------------------------------


def _pending(index: int, ocr: str, **kwargs: Any) -> LineManifest:
    """A line acceptance has not decided yet — ``corrected_text is None``.

    ``_apply_line_acceptance`` skips anything already decided, so a line
    built by :func:`tests.decision._state.line` (which sets a correction)
    would never reach the guards at all.
    """
    return LineManifest(
        line_id=f"L{index}",
        page_id="p1",
        block_id="b1",
        line_order_global=index,
        line_order_in_block=index,
        coords=Coords(hpos=0, vpos=index * 10, width=100, height=10),
        ocr_text=ocr,
        **kwargs,
    )


def _accept(lines: list[LineManifest], proposals: dict[str, str]):
    manifest, all_lines, traces = document(lines)
    _apply_line_acceptance(
        guard_config=GuardConfig(),
        chunk_lines=lines,
        text_by_id=proposals,
        all_lines_by_id={lm.line_id: lm for lm in lines},
        traces=traces,
    )
    return traces


def test_acceptance_writes_the_guards_own_reason() -> None:
    """Site 3 — a proposal too far from source is refused, and the guard's
    verdict is what lands on the trace."""
    lines = [_pending(1, "le chat noir dort")]
    traces = _accept(lines, {"L1": "ZZZZ QQQQ WWWW"})
    assert traces[line_ref(lines[0])].fallback_reason == "too_different_from_source"
    assert lines[0].corrected_text == lines[0].ocr_text


def test_acceptance_writes_the_orphan_hyphen_reason() -> None:
    """Site 1 — a PART1 whose source ends on a break mark and whose
    correction does not: the mark would be lost, so the line goes back."""
    lines = [_pending(1, "par-", hyphen_role=HyphenRole.PART1)]
    traces = _accept(lines, {"L1": "par"})
    assert traces[line_ref(lines[0])].fallback_reason == "orphan_hyphen_completed"


def test_acceptance_writes_the_fallen_partner_reason() -> None:
    """Site 2 — a hyphen member whose partner already fell back keeps its
    source text too (ADR-010), and says why."""
    tail = _pending(
        1,
        "par-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="L2",
        corrected_text="par-",
        status=LineStatus.FALLBACK,
    )
    head = _pending(2, "tir", hyphen_role=HyphenRole.PART2, hyphen_pair_line_id="L1")
    traces = _accept([tail, head], {"L2": "tir"})
    assert traces[line_ref(head)].fallback_reason == "hyphen_partner_fell_back"


def test_acceptance_skips_a_line_that_already_holds_a_decision() -> None:
    """Why sites 1-4 cannot collide with anything, including each other.

    ``_apply_line_acceptance`` opens with ``if lm.corrected_text is not
    None: continue``. A line carrying a reason carries a decision (I-1),
    so acceptance never reaches it a second time — the four assigning
    sites are unconditional because they are also unreachable twice."""
    lines = [line(1, "aaa", "AAA")]  # already decided
    manifest, all_lines, traces = document(lines)
    traces[line_ref(lines[0])].fallback_reason = "first_reason"
    _apply_line_acceptance(
        guard_config=GuardConfig(),
        chunk_lines=lines,
        text_by_id={"L1": "ZZZZ QQQQ WWWW"},
        all_lines_by_id={lm.line_id: lm for lm in lines},
        traces=traces,
    )
    assert traces[line_ref(lines[0])].fallback_reason == "first_reason"
    assert lines[0].corrected_text == "AAA"


def test_fall_back_to_source_defers_to_an_existing_reason() -> None:
    """Site 4 — MIGRATED to ``decide.fall_back`` (`RM-01` phase 2), so it
    now defers instead of assigning.

    The assertion is inverted ON PURPOSE and this is the one deliberate
    behaviour change of the migration. ADR-013 argues it is invisible: a
    line carrying a reason is already at its source text (I-1), so no
    collision reachable in a run can distinguish the two rules. Measured
    before the change over every corpus in the repository, with a
    producer failing ~20 % of its calls outright to force the
    chunk-exhaustion path — 145 fallbacks over 190 lines, **zero**
    collisions.

    The old pin (``== "second_reason"``) is gone rather than kept as a
    second case: it recorded a rule the code no longer follows."""
    lines, _all_lines, traces = _one_line("first_reason")
    _fall_back_to_source(lines, traces, reason="second_reason")
    assert traces[line_ref(lines[0])].fallback_reason == "first_reason"


def test_fall_back_to_source_still_reverts_text_and_status() -> None:
    """Deferring the REASON must not defer the revert — ADR-010's unit
    atomicity depends on text and status changing unconditionally."""
    lines, _all_lines, traces = _one_line("first_reason")
    lines[0].corrected_text = "A CORRECTION"
    lines[0].status = LineStatus.CORRECTED
    _fall_back_to_source(lines, traces, reason="second_reason")
    assert lines[0].corrected_text == lines[0].ocr_text
    assert lines[0].status is LineStatus.FALLBACK


# ---------------------------------------------------------------------------
# The deferring writers
# ---------------------------------------------------------------------------


def test_extend_to_units_never_overwrites() -> None:
    """A line dragged down by its unit keeps the reason it already had —
    ``hyphen_unit_fallback`` only fills a hole."""
    lines, _all_lines, traces = _one_line("first_reason")
    _extend_to_units(
        lines,
        traces,
        line_by_id={lm.line_id: lm for lm in lines},
        cross_page_partners=None,
    )
    assert traces[line_ref(lines[0])].fallback_reason == "first_reason"


def test_unit_revert_stamps_the_atomicity_reason_on_a_silent_member() -> None:
    """A member pulled down by its partner, with nothing on its trace,
    gets the calling pass's vocabulary."""
    tail, head, all_lines, traces = _linked_pair()
    _apply_unit_reverts(
        reverts={line_ref(tail): "reason_of_the_flagged_line"},
        all_lines=all_lines,
        traces=traces,
        atomicity_reason="pulled_by_unit",
    )
    assert traces[line_ref(head)].fallback_reason == "pulled_by_unit"
    assert head.corrected_text == head.ocr_text
    assert head.status is LineStatus.FALLBACK


def test_unit_revert_leaves_a_members_own_earlier_reason_alone() -> None:
    """The same pull, onto a member that already explained itself: the
    earlier reason survives, which is the behaviour you want."""
    tail, head, all_lines, traces = _linked_pair("earlier_reason_of_the_member")
    _apply_unit_reverts(
        reverts={line_ref(tail): "reason_of_the_flagged_line"},
        all_lines=all_lines,
        traces=traces,
        atomicity_reason="pulled_by_unit",
    )
    assert traces[line_ref(head)].fallback_reason == "earlier_reason_of_the_member"


def test_pair_trace_refresh_names_the_pair_when_the_trace_is_empty() -> None:
    """Site 6 — a member reverted by pair reconciliation, with nothing on
    its trace, is attributed to the pair."""
    tail, head, _all_lines, traces = _linked_pair()
    for member in (tail, head):
        member.corrected_text = member.ocr_text
        member.status = LineStatus.FALLBACK
    _refresh_pair_traces(tail, head, outcome="fallback", traces=traces)
    assert traces[line_ref(tail)].fallback_reason == "hyphen_pair_fallback"
    assert traces[line_ref(head)].fallback_reason == "hyphen_pair_fallback"


def test_pair_trace_refresh_defers_to_an_existing_reason() -> None:
    """Site 6, the deferring half — session 3 had this covered statically
    only. A member that already explained itself keeps its own words."""
    tail, head, _all_lines, traces = _linked_pair("earlier_reason_of_the_member")
    for member in (tail, head):
        member.corrected_text = member.ocr_text
        member.status = LineStatus.FALLBACK
    _refresh_pair_traces(tail, head, outcome="fallback", traces=traces)
    assert traces[line_ref(head)].fallback_reason == "earlier_reason_of_the_member"
    assert traces[line_ref(tail)].fallback_reason == "hyphen_pair_fallback"


def test_pair_trace_refresh_writes_no_reason_to_a_surviving_member() -> None:
    """A coherent pair keeps its correction, so there is nothing to
    explain — the reason stays empty and the status reads ``corrected``."""
    tail, head, _all_lines, traces = _linked_pair()
    _refresh_pair_traces(tail, head, outcome="coherent", traces=traces)
    assert traces[line_ref(tail)].fallback_reason is None
    assert traces[line_ref(head)].validation_status == "corrected"


def test_a_second_revert_keeps_the_first_reason_because_the_first_did_it() -> None:
    """The case ADR-013 turns on, and the one this file exists to pin.

    ``_apply_unit_reverts`` writes ``corrected_text`` and ``status``
    unconditionally, the reason only into an empty trace. Read alone that
    looks like a line being reverted by one pass and attributed to
    another.

    It is not, and I-1 is why: the line already carried a reason, so it
    was already at its source text, so THIS revert changed nothing a
    reader can see. The pass that took the correction away is the earlier
    one, and its reason is the true one — not the stale one. The
    behaviour below is correct, and pinning it protects it from a
    well-meaning `RM-01` that "fixes" it into last-writer-wins and starts
    naming passes that did nothing.

    The invariant that makes this argument is not asserted here in the
    abstract: :func:`test_a_reason_implies_the_line_is_back_at_source`
    checks it over the corpora.
    """
    lines, all_lines, traces = _one_line("first_reason")
    # I-1 in this fixture: a line with a reason is already at source.
    lines[0].corrected_text = lines[0].ocr_text
    lines[0].status = LineStatus.FALLBACK
    before = lines[0].corrected_text

    result = _apply_unit_reverts(
        reverts={line_ref(lines[0]): "a_later_pass_flagged_it_too"},
        all_lines=all_lines,
        traces=traces,
    )

    # The later pass reports the flag it raised …
    assert result[line_ref(lines[0])] == "a_later_pass_flagged_it_too"
    # … but it changed nothing: the revert was idempotent.
    assert lines[0].corrected_text == before
    assert lines[0].status is LineStatus.FALLBACK
    # … so the recorded reason still names what actually happened.
    assert traces[line_ref(lines[0])].fallback_reason == "first_reason"


# ---------------------------------------------------------------------------
# I-1, over real files — the invariant the whole rule rests on
# ---------------------------------------------------------------------------


class _AdversarialProducer:
    """A provider that breaks lines the way the guards are built to catch.

    Deterministic (seeded): duplicates a neighbour, absorbs across a seam,
    drops the break mark, re-segments, and sometimes answers far enough
    from source to be refused outright. The point is to reach every reason
    family in one run — a polite provider produces no fallbacks and would
    make I-1 vacuously true.
    """

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    async def list_models(self, api_key: str) -> list[Any]:  # pragma: no cover
        return []

    async def complete_structured(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], None]:
        out = []
        previous = None
        for entry in user_payload.get("lines", []):
            text = entry.get("ocr_text", "")
            roll = self._rng.random()
            if roll < 0.15 and previous:
                text = previous  # adjacent duplicate
            elif roll < 0.30:
                text = "ZZZZ QQQQ WWWW"  # too different from source
            elif roll < 0.40 and previous:
                text = f"{previous} {text}"  # absorbs the previous line
            elif roll < 0.55:
                text = text.rstrip("-¬⸗­")  # break mark dropped
            elif roll < 0.70:
                text = text.replace(" ", "") + " x"  # re-segmentation
            previous = entry.get("ocr_text", "")
            out.append({"line_id": entry["line_id"], "corrected_text": text})
        return {"lines": out}, None


class _Silent:
    def on_event(self, event_type: Any, payload: dict[str, Any]) -> None:
        pass


_CORPORA = [
    pytest.param([EXAMPLES / "sample.xml"], id="alto-sample"),
    pytest.param(sorted(CORPUS_GT.glob("*.src.page.xml")), id="page-corpus-gt"),
]

_POLICIES = [
    pytest.param(LossPolicy(), id="report"),
    pytest.param(LossPolicy(min_alignment_score=0.6), id="token_realign"),
    pytest.param(LossPolicy(strict=True), id="strict"),
]


@pytest.mark.parametrize("paths", _CORPORA)
@pytest.mark.parametrize("loss_policy", _POLICIES)
def test_a_reason_implies_the_line_is_back_at_source(
    paths: list[Path], loss_policy: LossPolicy
) -> None:
    """**I-1** — no line carries a ``fallback_reason`` while holding a
    correction.

    This is the load-bearing fact under ADR-013: it is what makes a
    second revert idempotent, and therefore what makes the FIRST reason
    the true one. It is not obvious and it is not documented anywhere in
    the code — it holds because every site writes the revert on the
    statement before the reason, and because ``guards.check_line``
    returns ``text=source_ocr`` on all five of its rejection branches.

    Nothing enforced it before this test. `RM-01` must keep it green: a
    single writer that records a reason without reverting, or that
    reverts without recording, breaks the rule ADR-013 rests on rather
    than merely changing a string.
    """
    if not paths:
        pytest.skip("corpus absent")
    manifest = build_document_manifest([(p, p.name) for p in paths])
    pipeline = CorrectionPipeline.for_provider(
        _AdversarialProducer(),
        api_key="k",
        model="m",
        observer=_Silent(),
        loss_policy=loss_policy,
    )
    result = pipeline.run_sync(
        document_manifest=manifest,
        source_files={p.name: p for p in paths},
    )

    source = {line_ref(lm): lm.ocr_text for page in manifest.pages for lm in page.lines}
    offenders = {
        ref: (decision.fallback_reason, decision.final_text, source[ref])
        for ref, decision in result.decisions.by_ref.items()
        if decision.fallback_reason and decision.final_text != source[ref]
    }
    assert not offenders, (
        f"I-1 broken on {len(offenders)} line(s): {list(offenders.items())[:3]}. "
        "A line that carries a fallback reason must already be back at its "
        "source text — ADR-013's whole argument for first-writer-wins "
        "depends on it."
    )

    # A run with no fallback at all would satisfy I-1 vacuously.
    assert any(d.fallback_reason for d in result.decisions.by_ref.values()), (
        "the adversarial producer stopped producing fallbacks — this "
        "corpus no longer exercises I-1, so fix the producer rather than "
        "trusting the green"
    )


# ---------------------------------------------------------------------------
# The split itself, pinned statically
# ---------------------------------------------------------------------------


def _reason_writes() -> tuple[int, int]:
    """``(guarded, unguarded)`` writes of ``fallback_reason`` in ``core``.

    Guarded = the assignment sits under an ``if`` that tests the field
    (``if not trace.fallback_reason``). Unguarded = it is handed to
    ``_set_trace`` as a keyword, which always assigns.
    """
    guarded = unguarded = 0
    for path in sorted((SRC / "core").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                assigns = [
                    sub
                    for sub in ast.walk(node)
                    if isinstance(sub, ast.Assign)
                    and any(
                        isinstance(t, ast.Attribute) and t.attr == "fallback_reason"
                        for t in sub.targets
                    )
                ]
                if assigns and "fallback_reason" in ast.unparse(node.test):
                    guarded += len(assigns)
            elif isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                )
                if name == "_set_trace":
                    unguarded += sum(
                        1 for kw in node.keywords if kw.arg == "fallback_reason"
                    )
    return guarded, unguarded


def test_the_precedence_rule_is_split_four_ways_against_three() -> None:
    """The census behind ADR-013, moving as `RM-01` migrates.

    Trajectory: (3 deferring, 4 assigning) at session 3, then one pair
    per migrated site as ``decide.fall_back`` absorbs them.

    The seven sites are pinned behaviourally above; this counts them, so
    that an eighth cannot appear unnoticed between two of the named
    tests. ADR-013 settles which way the split should go when `RM-01`
    collapses it: the single writer defers on all seven paths.

    When that lands there is ONE writer, and this test should be deleted
    rather than adjusted — a census of one is not a rule."""
    guarded, unguarded = _reason_writes()
    assert (guarded, unguarded) == (2, 0), (
        f"the precedence split moved to {guarded} deferring / {unguarded} "
        "assigning writes. If that was deliberate, update the behavioural "
        "pins above in the same commit — they are what says which reason a "
        "consumer actually sees."
    )
