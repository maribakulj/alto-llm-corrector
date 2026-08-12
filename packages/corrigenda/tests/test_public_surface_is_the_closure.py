"""What `corrigenda.__all__` should hold, computed rather than chosen.

`V5` says the public surface is *the closure of what the façade returns*, and
`S3` established that closure by calculation for a reason worth repeating:
choosing a surface by hand is how the package reached 95 symbols.

This module recomputes both closures on every run and pins the gaps.

**Closure of the façade returns — 34 types, all exported.** That half of `V5`
is met, and this test is what keeps it met: a new field on ``CorrectionResult``
whose type is not exported fails here, at the moment it is added, instead of
being discovered by a consumer who cannot name the value they are holding.

**Closure of the advanced door — 58 types, nine of them NOT exported.** This is
the measurement that supersedes `S3b`'s target, and it points the opposite way
to the plan's arithmetic (95 → 54, "cut 41"):

  * exactly **four** exported symbols sit outside EVERY closure and are
    demotable on the plan's own criterion;
  * **nine** types the advanced door's own signatures require cannot be
    imported from the top at all. Someone implementing ``EditProducer``, or
    passing ``format_adapter=``, has to reach into a module path for
    ``FormatAdapter``, ``RewriteResult``, ``ConfidenceScorer``, ``QEScorer``,
    ``RoutingPolicy`` or ``ConfidencePolicy``.

That second half explains an observation `S3` already recorded without
connecting it: the backend — the only real integrator — does not use
``load``/``correct``/``correct_sync``, it goes through the low-level door. It
had no choice. **The top-level namespace is a shop window the repository
itself does not use**, and part of the reason is that the door it does use was
never fully exported.

So the surface is not 41 symbols too big. It is four too big and nine too
small, and the open question is not "cut what" but **"is the advanced door
public?"** — which no closure can answer, because a door that is public has to
be closed over, and a door that is not means demoting ``CorrectionPipeline``
itself. That decision is written up in `docs/PLAN.md`; this file only holds it
still while it is made.

Nothing here asserts the surface *should* change. It asserts that both gaps
are exactly the ones measured on 2026-08-11, so the next session inherits a
fact instead of re-deriving one — twice, as this one did: the first two
attempts followed private methods into the engine and dropped the
constructor's parameters, which made the door's closure look like the whole
package.
"""

from __future__ import annotations

import dataclasses
import inspect
import typing

import corrigenda
from corrigenda import facade

#: Exported, and outside both closures. The façade entry points, the error
#: hierarchy and ``sanitize_error`` are here by design — they are not types a
#: return value drags in, they are the API itself.
_DELIBERATE = {
    "load",
    "correct",
    "correct_sync",
    "__version__",
    "sanitize_error",
    "CorrigendaError",
    "CorrectionError",
    "ParseError",
    "DuplicateIdError",
    "ProposalValidationError",
    "ValidationError",
    "CorrectionAborted",
}

#: Exported, outside both closures, and NOT deliberate — demotable on `S3`'s
#: own criterion. Measured 2026-08-11.
_OUTSIDE_EVERY_CLOSURE = {
    "EDIT_PROTOCOL_VERSION",
    "EditOp",
    "ImageRef",
    "PageImage",
}

#: Required by the advanced door's own signatures, and not exported. The
#: number this list should reach is a decision, not a measurement.
_DOOR_GAPS = {
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
        if not getattr(current, "__module__", "").startswith("corrigenda"):
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


def _door_closure() -> set[str]:
    return _closure(
        {
            corrigenda.CorrectionPipeline,
            corrigenda.EditProducer,
            corrigenda.PipelineObserver,
            corrigenda.CorrectionRequest,
        }
    )


def test_the_facade_closure_is_fully_exported() -> None:
    """`V5`'s checkable half, and the reason to run it on every commit.

    A type reachable from a returned value that a caller cannot import is a
    value nobody can name. This is where that gets caught — when the field is
    added, not when someone tries to use it.
    """
    missing = sorted(_return_closure() - set(corrigenda.__all__))
    assert not missing, (
        f"type(s) reachable from what the façade returns but absent from "
        f"corrigenda.__all__: {missing}. Either export them or stop returning "
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


def test_the_door_gaps_are_the_measured_ones() -> None:
    """The advanced door is not closed, and by exactly this much.

    Growing this set means a new door signature names a type a caller cannot
    import. Shrinking it means someone exported one — which is a surface
    decision, so it should arrive with the plan updated.
    """
    gaps = _door_closure() - set(corrigenda.__all__)
    assert gaps == _DOOR_GAPS, (
        f"the advanced door's unexported types changed.\n"
        f"  added:   {sorted(gaps - _DOOR_GAPS)}\n"
        f"  removed: {sorted(_DOOR_GAPS - gaps)}\n"
        "If the door is public these belong in __all__; if it is not, "
        "CorrectionPipeline does not either. `docs/PLAN.md` holds that "
        "question — answer it there, then update this set."
    )


def test_nothing_is_exported_outside_every_closure_but_the_named() -> None:
    """Four symbols, named, demotable on `S3`'s own criterion."""
    outside = set(corrigenda.__all__) - _return_closure() - _door_closure()
    unexpected = sorted(outside - _DELIBERATE - _OUTSIDE_EVERY_CLOSURE)
    assert not unexpected, (
        f"symbol(s) exported without being reachable from anything the "
        f"library returns or accepts: {unexpected}. That is how a surface "
        "grows to 95 — one deliberate addition at a time."
    )
    vanished = sorted(_OUTSIDE_EVERY_CLOSURE - outside)
    assert not vanished, (
        f"these were measured outside every closure and no longer are: "
        f"{vanished}. Good news, but the list has to follow."
    )
