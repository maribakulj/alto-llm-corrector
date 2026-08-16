"""What `lidenbrock.__all__` holds, recomputed on every run.

`S3b` cut the surface to a computed closure on 2026-08-01 and
``test_public_api_snapshot`` pins the resulting list. This module is its
complement: the snapshot says *which names*, this one says *why those* — it
redoes the calculation instead of trusting the list, so a change to a
signature or a returned field is caught by the rule rather than by a diff of
sixty-six strings.

The library makes **two** promises, and each is a closure that must be
complete:

  * what the façade RETURNS — 34 types, all exported. A caller typing the
    value it was handed can name every part of it.
  * what the PRODUCER SEAM accepts — 17 types, all exported. The README's
    first sentence promises corrections "by LLM, rules engine, or any custom
    EditProducer", so an implementer typing the protocol it fills can name
    every part of that too.

There is a **third** seam, and it is deliberately left open:
``CorrectionPipeline``'s optional injections — ``format_adapter``,
``qe_scorer``, ``routing_policy``, ``confidence_policy``,
``confidence_scorers``. Closing it would drag in nine more names, listed
below. They stay at their module paths, which ``docs/versioning.md``
documents as a supported door, for two reasons already written in
``test_public_api_snapshot``: ``RewriteResult``/``RewriteMetrics``/
``AlignedPair``/``TokenAlignment``/``FormatAdapter`` are the rewriter's
internal accounting vocabulary that `R5`/`R8`/`L8` have been moving all
year, and blessing it under SemVer would promise a stability nothing
supports; ``ConfidencePolicy``/``RoutingPolicy``/``QEScorer``/
``ConfidenceScorer`` are research knobs whose defaults do nothing, and a
top-level export reads as "ready".

**Why this file exists at all is a correction.** On 2026-08-11 the closure
was recomputed with ``CorrectionPipeline`` as a seed, which pulls the third
seam in, and the nine names below looked like *holes* — leading to a written
conclusion that the surface was "four too big and nine too small" and that
`S3b`'s target should be inverted. That was wrong, and the error is
instructive: seeding a public-surface calculation with a constructor's
OPTIONAL knobs measures what the library can be configured with, not what it
promises. The two promises are the seeds; the third seam is a decision.

So the nine are pinned here as the **cost of a decision**, not as a defect.
If someone later decides the third seam is public, this set goes to empty in
the same commit that exports them — and the snapshot, the CHANGELOG and
``docs/versioning.md`` move with it.
"""

from __future__ import annotations

import dataclasses
import inspect
import typing

import lidenbrock
from lidenbrock import facade

#: Exported without being reachable from either promise — on purpose, with
#: the reason. This is the list that has to stay short: a surface reaches 95
#: one defensible addition at a time, and the defence is the point.
_DELIBERATE: dict[str, str] = {
    "load": "the façade itself",
    "correct": "the façade itself",
    "correct_sync": "the façade itself",
    "__version__": "a dunder",
    "sanitize_error": "the one helper the backend imports from the top (3 sites)",
    "LidenbrockError": "the error hierarchy is the API, not a returned type",
    "CorrectionError": "deprecation alias, removed at 1.0",
    "ParseError": "the error hierarchy",
    "DuplicateIdError": "the error hierarchy",
    "ProposalValidationError": "the error hierarchy",
    "ValidationError": "deprecation alias, removed at 1.0",
    "CorrectionAborted": "the error hierarchy",
    "CorrectionPipeline": "the advanced door itself — what the backend uses",
    "RetryPolicy": "§15: injection is the ONLY way a consumer adapts the lib",
    "GuardConfig": "§15 injection point",
    "ChunkPlannerConfig": "§15 injection point",
    "PairingPolicy": "§15 injection point",
    "LossPolicy": "§15 injection point",
    "ProducerMetadata": "what a producer declares about itself (§11 provenance)",
    "ImageRef": "`I4` — the pure core CARRIES it for a producer that asks for "
    "pixels, and never opens it",
    "PageImage": "`I4`, same reason",
    "EditOp": "the edit protocol's own vocabulary, exported with EditScript",
    "EDIT_PROTOCOL_VERSION": "the version a consumer dispatches on (`D5`)",
}

#: What closing the THIRD seam would cost. Not holes — the price of a
#: decision taken on 2026-08-01 and re-affirmed on 2026-08-12.
_THIRD_SEAM = {
    "AlignedPair",
    "ConfidencePolicy",
    "ConfidenceScorer",
    "FormatAdapter",
    "QEScorer",
    "RewriteMetrics",
    "RewriteResult",
    "RoutingPolicy",
    "TokenAlignment",
}


def _types_in(annotation: object) -> set[type]:
    found: set[type] = set()
    stack = [annotation]
    while stack:
        current = stack.pop()
        if current is None:
            continue
        if typing.get_origin(current) is not None:
            stack.extend(typing.get_args(current))
            continue
        if inspect.isclass(current):
            found.add(current)
    return found


def _hints(function: object) -> set[object]:
    try:
        return set(typing.get_type_hints(function).values())
    except Exception:  # pragma: no cover - an unresolvable hint is not a gap
        return set()


def _referenced_by(cls: type) -> set[object]:
    """Every annotation a CALLER of ``cls`` has to be able to name.

    Fields, plus the signatures of its public methods and its constructor —
    and nothing private. Following ``_``-prefixed methods is what made the
    first run of this measurement report the engine's internals as part of
    the public door.
    """
    referenced: set[object] = set()
    if hasattr(cls, "model_fields"):
        referenced |= {f.annotation for f in cls.model_fields.values()}
    elif dataclasses.is_dataclass(cls):
        try:
            referenced |= set(typing.get_type_hints(cls).values())
        except Exception:  # pragma: no cover
            pass
    for name, function in inspect.getmembers(cls, inspect.isfunction):
        if name.startswith("_") and name != "__init__":
            continue
        referenced |= _hints(function)
    return referenced


def _closure(seeds: set[type]) -> set[str]:
    seen: set[type] = set()
    queue = list(seeds)
    while queue:
        current = queue.pop()
        if current in seen or not inspect.isclass(current):
            continue
        if not getattr(current, "__module__", "").startswith("lidenbrock"):
            continue
        seen.add(current)
        for annotation in _referenced_by(current):
            queue.extend(_types_in(annotation))
    return {cls.__name__ for cls in seen}


def _return_closure() -> set[str]:
    seeds: set[type] = set()
    for function in (facade.load, facade.correct, facade.correct_sync):
        seeds |= _types_in(typing.get_type_hints(function).get("return"))
    return _closure(seeds)


def _producer_seam_closure() -> set[str]:
    """The second promise. ``CorrectionPipeline`` is deliberately NOT a seed.

    It accepts the third seam's optional injections, so seeding with it
    measures what the library can be configured with rather than what it
    promises — the exact error this file was born correcting.
    """
    return _closure(
        {
            lidenbrock.EditProducer,
            lidenbrock.PipelineObserver,
            lidenbrock.CorrectionRequest,
        }
    )


def _third_seam_closure() -> set[str]:
    return _closure({lidenbrock.CorrectionPipeline}) - _producer_seam_closure()


def test_the_facade_closure_is_fully_exported() -> None:
    """`V5`'s checkable half, and the reason to run it on every commit.

    A type reachable from a returned value that a caller cannot import is a
    value nobody can name. This is where that gets caught — when the field is
    added, not when someone tries to use it.
    """
    missing = sorted(_return_closure() - set(lidenbrock.__all__))
    assert not missing, (
        f"type(s) reachable from what the façade returns but absent from "
        f"lidenbrock.__all__: {missing}. Either export them or stop returning "
        "a value that carries them."
    )


def test_the_return_closure_has_not_quietly_shrunk() -> None:
    """Green by vacuity looks exactly like green."""
    closure = _return_closure()
    assert len(closure) >= 30, (
        f"the façade-return closure collapsed to {len(closure)} types — the "
        "walk stopped following annotations, and the test above now proves "
        "nothing. It was 34 on 2026-08-11."
    )


def test_the_producer_seam_is_fully_exported() -> None:
    """The second promise, held to the same standard as the first."""
    missing = sorted(_producer_seam_closure() - set(lidenbrock.__all__))
    assert not missing, (
        f"type(s) an EditProducer implementer must name but cannot import "
        f"from the top: {missing}. The README promises this seam; a promise "
        "with a name you cannot say is not one."
    )


def test_the_third_seam_costs_exactly_what_was_decided() -> None:
    """The price of leaving ``CorrectionPipeline``'s knobs at module paths.

    Growing this set means a new optional injection named a new type — worth
    knowing, since each one raises the price of ever closing the seam.
    Shrinking it means someone exported one, which is a surface decision and
    should arrive with the snapshot, the CHANGELOG and versioning.md.
    """
    cost = _third_seam_closure() - set(lidenbrock.__all__)
    assert cost == _THIRD_SEAM, (
        f"the third seam's cost changed.\n"
        f"  added:   {sorted(cost - _THIRD_SEAM)}\n"
        f"  removed: {sorted(_THIRD_SEAM - cost)}\n"
        "These stay at their module paths on purpose "
        "(see test_public_api_snapshot). Changing that is a decision, not a "
        "refactor."
    )


def test_nothing_is_exported_outside_both_promises_but_the_named() -> None:
    """A symbol in neither promise is how a surface reaches 95."""
    outside = set(lidenbrock.__all__) - _return_closure() - _producer_seam_closure()
    unexpected = sorted(outside - set(_DELIBERATE))
    assert not unexpected, (
        f"symbol(s) exported without being reachable from either promise and "
        f"without a stated reason: {unexpected}. That is how a surface grows "
        "to 95 — one defensible addition at a time, undefended."
    )
    stale = sorted(set(_DELIBERATE) - outside - {"load", "correct", "correct_sync"})
    assert not stale, (
        f"these are listed as deliberate exceptions but are now reachable "
        f"from a promise (or gone): {stale}. Drop them — an exception nobody "
        "removes stops being one."
    )
