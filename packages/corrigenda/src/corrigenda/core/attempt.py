"""One chunk, asked of a producer until it answers or the budget runs out.

The narrowest loop in the engine, and the one that was hardest to read: a
single 221-line method held what to ask, how to ask it again, what came
back, and what to record — four different jobs, only one of which is
control flow. They are four functions now, and the loop reads as the
retry policy it implements:

  - :func:`_build_correction_request` — what the producer is asked, and
    the input side of the trace;
  - :func:`_produce` — the call itself, stopping at the raw
    :class:`EditScript`, and :func:`_script_to_raw` to put that script in
    the shape the validator checks;
  - :func:`_validate_and_capture` — what happens to what came back:
    proposal traces, validation, and capturing the ops actually applied;
  - :func:`_handle_failed_attempt` — what a failure means and what a
    retry costs;
  - :func:`_attempt_chunk` — the loop itself, and nothing else.

Free functions. What the engine used to supply from ``self`` is an
argument: the retry policy that shapes the ramp, the guard config the
validator and the span protocol read, and the observer callback. An
attempt is a call over a chunk and a policy, not a property of a run.

**This function never applies the OCR fallback.** That decision — and the
warning event that goes with it — belongs to the caller, which may descend
a granularity instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from corrigenda.core import events as ev
from corrigenda.core.context import RunContext
from corrigenda.core.editing import (
    EditOp,
    EditScript,
    ReplaceLine,
    ReplaceSpan,
    apply_edit_script,
)
from corrigenda.core.hyphenation import enrich_chunk_lines
from corrigenda.core.identity import LineRef
from corrigenda.core.protocols import (
    EditProducer,
    ProducerOptions,
    ProviderPermanentError,
    ProviderTransientError,
)
from corrigenda.core.redaction import sanitize_error
from corrigenda.core.retry import _RetryDecision, _classify_retry
from corrigenda.core.traces import _set_trace
from corrigenda.core.schemas import (
    ChunkRequest,
    CorrectionRequest,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineTrace,
    ProposalBatch,
    RetryPolicy,
    Usage,
)
from corrigenda.core.validator import validate_llm_response

# ADR-008 (revised) — recoverability is an ALLOWLIST. Exactly the two
# families the retry classifier can route are recoverable on the
# producer-attempt path:
#   - ProviderTransientError — transport flakiness a conforming provider
#     wrapped (wrapping is the provider CONTRACT, not a courtesy: the
#     provider-agnostic pipeline cannot name raw httpx/SDK exceptions,
#     so an unwrapped one is indistinguishable from a bug and fails the
#     run rather than degrading to a fake success);
#   - ValueError — the documented malformed-producer-output family
#     (ProposalValidationError, HyphenIntegrityError, json.JSONDecodeError all
#     inherit it; §8.4 keeps them value-shaped for exactly this route).
# Everything else — RuntimeError, KeyError, a pydantic bug, an SDK
# exception nobody classified — fails the run: an unknown exception
# must never become a silently-uncorrected "success".
_RECOVERABLE_ERROR_TYPES: tuple[type[BaseException], ...] = (
    ProviderTransientError,
    ValueError,
)


def _script_to_raw(
    script: EditScript,
    chunk_lines: list[LineManifest],
    *,
    producer: EditProducer,
    guard_config: GuardConfig,
) -> dict[str, Any]:
    """Normalise a producer's EditScript into the validator's raw shape.

    - ``replace_line`` ops pass through as-is (duplicates and empty
      texts included — the validator's structural checks must see them
      exactly as the historical raw response did).
    - ``replace_span`` ops are normalised and applied against the
      chunk's canonical text via :func:`apply_edit_script` (E1–E5); a
      rejected op leaves its line uncovered.
    - When the producer declares ``requires_full_coverage = False``
      (deterministic producers: no op == no edit), uncovered lines are
      filled with their canonical text so the validator's 1:1 check
      passes. An LLM producer keeps full-coverage semantics: a dropped
      target line stays missing → ProposalValidationError → retry.
    """
    canonical = {lm.line_id: lm.ocr_text for lm in chunk_lines}
    entries: list[dict[str, str]] = []

    span_ops = [op for op in script.ops if isinstance(op, ReplaceSpan)]
    for op in script.ops:
        if isinstance(op, ReplaceLine):
            entries.append({"line_id": op.line_id, "corrected_text": op.text})
    if span_ops:
        span_result = apply_edit_script(
            EditScript(ops=list(span_ops)),
            canonical,
            chunk_line_ids=set(canonical),
            guard_config=guard_config,
            line_by_id={lm.line_id: lm for lm in chunk_lines},
        )
        for lid, txt in span_result.text_by_id.items():
            entries.append({"line_id": lid, "corrected_text": txt})

    if not getattr(producer, "requires_full_coverage", True):
        covered = {e["line_id"] for e in entries}
        for lid, txt in canonical.items():
            if lid not in covered:
                entries.append({"line_id": lid, "corrected_text": txt})

    return {"lines": entries}


def _build_correction_request(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    all_lines_by_id: dict[str, LineManifest],
    producer: EditProducer,
    traces: dict[LineRef, LineTrace] | None,
) -> CorrectionRequest:
    """What this attempt asks the producer, and what the trace records
    having asked.

    The enrichment is what the producer actually sees, so it is also what
    the trace's input side must hold — recording the raw manifest text
    there would describe a call that never happened. §4.1: the page's
    vision envelope is copied in only when the producer asks for it, and
    the library never opens it (I4).
    """
    enriched = enrich_chunk_lines(
        chunk_lines,
        all_lines_by_id,
        include_geometry=getattr(producer, "wants_geometry", False),
        page_dims=ctx.page_dims,
    )
    enriched_by_id = {e.line_id: e for e in enriched}
    for lm in chunk_lines:
        ei = enriched_by_id.get(lm.line_id)
        if ei is not None:
            _set_trace(traces, lm, model_input_text=ei.ocr_text)

    return CorrectionRequest(
        granularity=chunk.granularity,
        document_id=chunk.document_id,
        page_id=chunk.page_id,
        block_id=chunk.block_id,
        lines=enriched,
        image_ref=(
            ctx.image_ref_by_page_id.get(chunk.page_id)
            if getattr(producer, "wants_image", False)
            else None
        ),
    )


def _record_proposal_traces(
    raw: dict[str, Any],
    chunk_lines: list[LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """Record what the producer PROPOSED, before any guard sees it.

    Deliberately the raw text: the proposal stage is the audit trail of
    what was actually said, and a normalised copy of it would answer a
    different question than the one an auditor is asking.
    """
    lm_by_id = {lm.line_id: lm for lm in chunk_lines}
    for rl in raw.get("lines", []) if isinstance(raw, dict) else []:
        if not isinstance(rl, dict):
            continue
        target = lm_by_id.get(rl.get("line_id", ""))
        if target is not None:
            _set_trace(
                traces, target, model_corrected_text=rl.get("corrected_text", "")
            )


def _declared_subs_content(chunk_lines: list[LineManifest]) -> dict[str, str]:
    """The ``SUBS_CONTENT`` the SOURCE declared, per opening line.

    Read straight off each line's own fields — no partner is resolved
    here, and none may be: this is the markup's own word for the unit,
    handed to the validator so a proposal cannot contradict it.
    """
    declared: dict[str, str] = {}
    for lm in chunk_lines:
        if lm.hyphen_role == HyphenRole.PART1 and lm.hyphen_subs_content:
            declared[lm.line_id] = lm.hyphen_subs_content
        elif lm.hyphen_role == HyphenRole.BOTH and lm.hyphen_forward_subs_content:
            declared[lm.line_id] = lm.hyphen_forward_subs_content
    return declared


def _capture_producer_ops(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    script: EditScript,
    response: ProposalBatch,
) -> None:
    """§4 — remember each TARGET line's ops and the text they produced.

    Captured pre-guard and pre-reconcile, and NOT emitted as the final
    EditScript from here: a line later reverted (duplicate, rejected by
    ``check_line``) or reconciled to different text must not leave a
    stale op behind — a dry-run consumer replaying it would diverge from
    the pipeline's own corrected XML. ``_build_final_edit_script``
    reconciles these against the FINAL per-line state, keeping the
    producer's op TYPE (e.g. a rules producer's ``replace_span``) where
    its output survived unchanged.
    """
    target_ids = set(chunk.targets())
    produced_by_line = {o.line_id: o.corrected_text for o in response.lines}
    ops_by_line: dict[str, list[EditOp]] = {}
    for op in script.ops:
        if op.line_id in target_ids and op.line_id in produced_by_line:
            ops_by_line.setdefault(op.line_id, []).append(op)
    for line_id, line_ops in ops_by_line.items():
        # Chunks are page-scoped, so chunk.page_id qualifies every target
        # line unambiguously.
        ctx.producer_ops[LineRef(page_id=chunk.page_id, line_id=line_id)] = (
            line_ops,
            produced_by_line[line_id],
        )


def _validate_and_capture(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    hyphen_pairs: dict[str, str],
    raw: dict[str, Any],
    script: EditScript,
    guard_config: GuardConfig,
    traces: dict[LineRef, LineTrace] | None,
) -> ProposalBatch:
    """Record what was proposed, check it, and capture what it applied.

    Raises the malformed-output family (all ``ValueError``) on a proposal
    the validator refuses, which is what puts the attempt loop back into
    its retry branch — and why the caller counts this call's tokens
    BEFORE getting here: they were spent either way.
    """
    _record_proposal_traces(raw, chunk_lines, traces)

    declared_subs = _declared_subs_content(chunk_lines)
    response = validate_llm_response(
        raw,
        [lm.line_id for lm in chunk_lines],
        hyphen_pairs if hyphen_pairs else None,
        {lm.line_id: lm.ocr_text for lm in chunk_lines},
        declared_subs if declared_subs else None,
        guard_config=guard_config,
        # The 1:1 count is enforced on targets; a missing context
        # line's output is not an error (it belongs to an adjacent chunk).
        target_line_ids=chunk.target_line_ids,
    )
    _capture_producer_ops(ctx=ctx, chunk=chunk, script=script, response=response)
    return response


async def _produce(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    producer: EditProducer,
    chunk_lines: list[LineManifest],
    all_lines_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    attempt: int,
    temperature: float,
) -> tuple[EditScript, Usage | None]:
    """Ask the producer once, and return what it said.

    Deliberately stops at the raw :class:`EditScript`: what came back is
    not yet known to be usable, and the caller must charge this call's
    tokens before finding out — they were spent either way.
    """
    payload = _build_correction_request(
        ctx=ctx,
        chunk=chunk,
        chunk_lines=chunk_lines,
        all_lines_by_id=all_lines_by_id,
        producer=producer,
        traces=traces,
    )
    # The producer gets a per-call envelope, not the engine's whole
    # RetryPolicy: the ramp (and the hyphen 0.0 pin) is decided by the
    # caller; the probe lets long I/O be abandoned mid-flight. Count every
    # invocation (this attempt hits the producer whether or not it
    # succeeds): the real cost.
    ctx.producer_calls += 1
    return await producer.produce(
        payload,
        options=ProducerOptions(
            attempt=attempt,
            temperature=temperature,
            should_abort=ctx.should_abort,
        ),
    )


async def _handle_failed_attempt(
    *,
    exc: Exception,
    ctx: RunContext,
    chunk: ChunkRequest,
    attempt: int,
    max_attempts: int,
    hyphen_already_seen: bool,
    retry_policy: RetryPolicy,
    emit: Callable[[ev.EngineEvent], None],
) -> tuple[bool, _RetryDecision, str]:
    """Decide what a failed attempt means, and pay for the retry if there
    is one.

    Re-raises anything outside the recoverable allowlist (ADR-008): only
    the two families the classifier can route degrade to
    retry-then-OCR-fallback. A programming error, an unwrapped SDK
    transport exception or a broken invariant FAILS the run — masking one
    as uncorrected OCR text would degrade EVERY chunk while still
    reporting success. Providers signal transport flakiness by wrapping it
    as ``ProviderTransientError`` (their contract).

    Returns ``(will_retry, decision, sanitised_msg)``. When ``will_retry``
    the backoff has already been slept and the ``retry`` event emitted.
    """
    if not isinstance(exc, _RECOVERABLE_ERROR_TYPES):
        raise exc
    # §5.1 — the pipeline no longer holds credentials; the pattern-based
    # redaction still masks secret-shaped substrings a producer may leak
    # into the message, and the consumer layer (which DOES hold the key)
    # sanitises again on its own error paths.
    msg = sanitize_error(str(exc))
    decision = _classify_retry(
        exc=exc,
        sanitised_msg=msg,
        attempt=attempt,
        hyphen_already_seen=hyphen_already_seen,
        policy=retry_policy,
    )
    will_retry = attempt < max_attempts and decision.is_retryable
    if will_retry:
        if decision.backoff > 0:
            await asyncio.sleep(decision.backoff)
        emit(
            ev.Retry(chunk_id=chunk.chunk_id, attempt=attempt, error=decision.error_tag)
        )
        ctx.retry_count += 1
    return will_retry, decision, msg


@dataclass(frozen=True)
class _AttemptOutcome:
    """What a chunk's attempt loop has to say when it stops.

    A five-slot tuple said the same thing and made every field a position
    to remember at the call site — including two that only mean anything
    on failure.
    """

    #: The validated batch, or ``None`` when no attempt produced one.
    response: ProposalBatch | None
    #: Attempts consumed, charged by the caller to the per-chunk budget.
    attempts_used: int
    #: On failure: the terminal error was retryable, so the same work is
    #: worth another try at a finer granularity. A hard error (e.g. a
    #: 4xx) is ``False`` — smaller chunks would hit the same wall.
    can_downgrade: bool
    #: The sanitised terminal error message, empty on success.
    last_msg: str
    #: Tokens this chunk spent across EVERY call of the loop, including
    #: calls whose response later failed validation — they were spent
    #: regardless, and the chunk_completed event reports the true total.
    usage: Usage | None


async def _attempt_chunk(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    producer: EditProducer,
    chunk_lines: list[LineManifest],
    hyphen_pairs: dict[str, str],
    all_lines_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    max_attempts: int,
    retry_policy: RetryPolicy,
    guard_config: GuardConfig,
    emit: Callable[[ev.EngineEvent], None],
) -> _AttemptOutcome:
    """Call the edit producer with retries; return the outcome.

    Retry strategy: up to ``max_attempts``, bounded by the caller to
    the remaining budget, with the temperature ramp and backoffs the
    injected :class:`RetryPolicy` defines — except after a
    ``HyphenIntegrityError``, which pins every later attempt to 0.0 (the
    producer mishandled a pair; a colder attempt sticks closer to source).
    """
    hyphen_violation = False
    attempts_used = 0
    last_msg = ""
    chunk_usage = Usage()

    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        # Temperature comes from the injected RetryPolicy. A hyphen
        # violation still pins the next attempt to 0.0 (the producer
        # mishandled the pair; a colder attempt sticks closer to source).
        temperature = 0.0 if hyphen_violation else retry_policy.temperature_for(attempt)
        try:
            script, usage = await _produce(
                ctx=ctx,
                chunk=chunk,
                producer=producer,
                chunk_lines=chunk_lines,
                all_lines_by_id=all_lines_by_id,
                traces=traces,
                attempt=attempt,
                temperature=temperature,
            )
            raw = _script_to_raw(
                script, chunk_lines, producer=producer, guard_config=guard_config
            )
            # Charged before validation: a response the validator goes
            # on to refuse still cost its tokens, and both the run's total
            # and this chunk's must say so.
            if usage is not None:
                ctx.usage = ctx.usage + usage
                chunk_usage = chunk_usage + usage
            response = _validate_and_capture(
                ctx=ctx,
                chunk=chunk,
                chunk_lines=chunk_lines,
                hyphen_pairs=hyphen_pairs,
                raw=raw,
                script=script,
                guard_config=guard_config,
                traces=traces,
            )
            return _AttemptOutcome(response, attempts_used, False, "", chunk_usage)

        except ProviderPermanentError:
            # ADR-008 — credentials/model rejected: retrying is pointless
            # and falling back would fake success. Fatal for the run.
            raise
        except Exception as exc:
            will_retry, decision, last_msg = await _handle_failed_attempt(
                exc=exc,
                ctx=ctx,
                chunk=chunk,
                attempt=attempt,
                max_attempts=max_attempts,
                hyphen_already_seen=hyphen_violation,
                retry_policy=retry_policy,
                emit=emit,
            )
            if will_retry:
                if decision.is_hyphen_violation:
                    hyphen_violation = True
                continue
            # Attempts exhausted (or non-retryable error class). Do NOT
            # fall back here — the caller decides between a granularity
            # downgrade and the OCR fallback. ``can_downgrade`` is
            # True only when the terminal error was retryable.
            return _AttemptOutcome(
                None, attempts_used, decision.is_retryable, last_msg, None
            )

    # max_attempts <= 0 (no budget left): nothing attempted.
    return _AttemptOutcome(None, attempts_used, False, last_msg, None)
