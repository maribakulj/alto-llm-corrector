"""The orchestrator may only shrink, and no new method is born oversized.

``core/pipeline.py`` is being split into named components. The split was
happening slice by slice with nothing but a line count in a plan document to
say whether it was progressing — so a slice that moved code *and* grew the
file, or one that lifted a stage out but left a 200-line method behind, would
have read exactly like a slice that worked.

Two rules, both mechanical:

  1. **The module budget is a ratchet.** ``_MODULE_BUDGET`` may be lowered
     when a slice lands and never raised. It is not the target — the target
     is 800 lines — it is the promise that the number in front of us today
     is the worst it will ever be.
  2. **A method over 100 lines must be named.** ``_OVERSIZED`` is the
     explicit, shrinking list of methods that still exceed the target, with
     the size each is pinned at. A method that is not on the list and
     exceeds 100 lines fails: that is the case of a slice that lifts one
     stage out by inlining it into another.

Both lists are meant to reach their target and then this file asserts the
plain rule with no exceptions in it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PIPELINE = Path(__file__).parent.parent / "src" / "corrigenda" / "core" / "pipeline.py"

#: The target the plan sets for the orchestrator, in lines.
_MODULE_TARGET = 800

#: Today's ceiling. Lower it as slices land; never raise it.
_MODULE_BUDGET = 1450

#: The longest a method may be once the split is finished.
_METHOD_TARGET = 100

#: Methods still over :data:`_METHOD_TARGET`, each with its current ceiling.
#: Removing an entry is how a slice records that it finished a method; an
#: entry may shrink, never grow. Empty is the goal.
_OVERSIZED: dict[str, int] = {
    "_attempt_chunk": 221,
    "_process_page": 165,
    "_run_chunk": 158,
}


def _method_lengths() -> dict[str, int]:
    """Every function/method defined in the orchestrator, by source lines.

    Nested definitions are skipped: their lines are already counted in the
    enclosing definition, and counting both would double-charge a closure.
    """
    tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
    lengths: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        nested = {
            child.name
            for child in ast.walk(node)
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            and child is not node
        }
        lengths[node.name] = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
        for name in nested:
            lengths.pop(name, None)
    return lengths


def test_module_budget_is_a_ratchet() -> None:
    actual = len(PIPELINE.read_text(encoding="utf-8").splitlines())
    assert actual <= _MODULE_BUDGET, (
        f"core/pipeline.py grew to {actual} lines, over its {_MODULE_BUDGET}-line "
        "budget. The budget only goes down: lift a stage out into its own "
        "module rather than raising it."
    )


def test_budget_stays_ahead_of_the_file() -> None:
    """A budget left far above the file it guards guards nothing."""
    actual = len(PIPELINE.read_text(encoding="utf-8").splitlines())
    if actual > _MODULE_TARGET:
        assert _MODULE_BUDGET - actual <= 50, (
            f"core/pipeline.py is {actual} lines but the budget is "
            f"{_MODULE_BUDGET} — lower _MODULE_BUDGET to match what the last "
            "slice actually achieved, so the next slice inherits the gain."
        )


def test_no_unnamed_method_exceeds_the_target() -> None:
    over = {
        name: size
        for name, size in _method_lengths().items()
        if size > _METHOD_TARGET and name not in _OVERSIZED
    }
    assert not over, (
        f"{over} exceed the {_METHOD_TARGET}-line target and are not on the "
        "known-oversized list. A split that moves work from one long method "
        "into another is not a split — extract the stage instead."
    )


@pytest.mark.parametrize("name", sorted(_OVERSIZED))
def test_known_oversized_methods_only_shrink(name: str) -> None:
    lengths = _method_lengths()
    assert name in lengths, (
        f"{name} no longer exists in core/pipeline.py — drop it from "
        "_OVERSIZED, the entry is the debt, not the method."
    )
    assert lengths[name] <= _OVERSIZED[name], (
        f"{name} grew to {lengths[name]} lines, over its pinned "
        f"{_OVERSIZED[name]}. Known-oversized methods may only shrink."
    )


def test_finished_methods_are_not_still_listed() -> None:
    """Once a method reaches the target, its entry must go — otherwise the
    list stops describing the remaining debt."""
    lengths = _method_lengths()
    done = {
        name: lengths[name]
        for name in _OVERSIZED
        if name in lengths and lengths[name] <= _METHOD_TARGET
    }
    assert not done, (
        f"{done} are within the {_METHOD_TARGET}-line target — remove them "
        "from _OVERSIZED so the list still shows what is left."
    )
