"""Classifying an exception inside the chunk retry loop.

Pure: given an exception, the attempt number and the per-chunk hyphen latch,
say whether to retry, how long to wait, and what to call it. No chunk, no
observer, no traces — which is what makes it testable on its own and what
made it worth lifting out of the 3200-line orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass

import json

from saknussemm.core.protocols import ProviderTransientError
from saknussemm.core.schemas import DEFAULT_RETRY_POLICY, RetryPolicy
from saknussemm.core.validator import HyphenIntegrityError


@dataclass(frozen=True)
class _RetryDecision:
    """Pure result of classifying a retry-loop exception.

    Decoupled from the retry loop so the classifier can be tested in
    isolation (no chunk, no observer, no traces — just the exception
    and the per-chunk hyphen latch).
    """

    is_retryable: bool
    backoff: float
    error_tag: str
    is_hyphen_violation: bool


def _classify_retry(
    *,
    exc: BaseException,
    sanitised_msg: str,
    attempt: int,
    hyphen_already_seen: bool,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> _RetryDecision:
    """Decide what to do with an exception during the LLM retry loop.

    Three retryable branches:
      - ``HyphenIntegrityError`` (first occurrence per chunk):
        backoff 0, fixed tag ``"hyphen_integrity_violation"``.
      - ``ProviderTransientError`` (transport): backoff = attempt * 2.
      - other ``ValueError`` / ``JSONDecodeError`` (malformed LLM
        output): backoff = attempt.

    Anything else (or a second hyphen-integrity violation in the same
    chunk) is non-retryable from THIS decision's standpoint — the
    caller short-circuits to the OCR fallback.

    Caller passes ``sanitised_msg`` (already run through
    ``sanitize_error``) so we don't re-sanitise here.
    """
    is_hyphen_violation = isinstance(exc, HyphenIntegrityError)
    is_transient_http = isinstance(exc, ProviderTransientError)
    # A repeated HyphenIntegrityError on the same chunk falls into the
    # LLM-output-error path (linear backoff): the per-chunk latch only
    # exempts the FIRST occurrence; subsequent ones are treated like
    # any other malformed LLM output.
    is_llm_output_error = isinstance(exc, (ValueError, json.JSONDecodeError))

    if is_hyphen_violation and not hyphen_already_seen:
        return _RetryDecision(
            is_retryable=True,
            backoff=0,
            error_tag="hyphen_integrity_violation",
            is_hyphen_violation=True,
        )
    if is_transient_http:
        return _RetryDecision(
            is_retryable=True,
            backoff=attempt * policy.transient_backoff_base,
            error_tag=sanitised_msg[:120],
            is_hyphen_violation=False,
        )
    if is_llm_output_error:
        return _RetryDecision(
            is_retryable=True,
            backoff=attempt * policy.output_backoff_base,
            error_tag=sanitised_msg[:120],
            is_hyphen_violation=False,
        )
    return _RetryDecision(
        is_retryable=False,
        backoff=0,
        error_tag=sanitised_msg[:120],
        is_hyphen_violation=False,
    )


@dataclass
class ChunkBudget:
    """Attempts left for one original chunk and its whole descent.

    Was ``budget: list[int]`` — a one-element list used as a mutable cell,
    because a descent has to spend from the SAME purse as the chunk that
    spawned it and an ``int`` would have been copied at the call boundary.
    The trick worked and cost a reader two questions at every site: why a
    list, and what the element means. `RM-03` gives it a name.

    Deliberately not frozen. It is the one genuinely mutable thing on the
    chunk path, and pretending otherwise would mean returning a new budget
    through six call frames to say what ``spend`` says here.
    """

    remaining: int

    def spend(self, attempts: int) -> None:
        """Charge attempts already made. Never raises: a descent that
        overspends its last sub-chunk is charged and then refused by
        :attr:`exhausted`, which is the historical behaviour."""
        self.remaining -= attempts

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def attempts_allowed(self, cap: int) -> int:
        """How many attempts the next call may make: the policy's cap,
        bounded by what is left, never negative."""
        return min(cap, max(self.remaining, 0))


__all__ = ["ChunkBudget"]
