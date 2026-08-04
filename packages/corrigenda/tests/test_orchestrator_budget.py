"""The orchestrator may only shrink, and no function is born oversized.

``core/pipeline.py`` is being split into named components. The split was
happening slice by slice with nothing but a line count in a plan document to
say whether it was progressing — so a slice that moved code *and* grew the
file, or one that lifted a stage out but left a 200-line function behind,
would have read exactly like a slice that worked.

Three rules, all mechanical:

  1. **The orchestrator's budget is a ratchet.** ``_MODULE_BUDGET`` may be
     lowered when a slice lands and never raised. It is not the target — the
     target is 800 lines — it is the promise that the number in front of us
     today is the worst it will ever be.
  2. **A function over 100 lines must be named**, anywhere in ``core``, not
     only in the orchestrator. This is the rule that stops the split from
     laundering the problem: moving a 150-line method into a new module is
     not a split if it is still 150 lines when it lands.
  3. **A named function may only shrink**, and once it reaches the target its
     entry must go — otherwise the list stops describing the remaining debt.

``_OVERSIZED`` is that list, and it is longer than the orchestrator: three of
its entries (``_render_outputs``, ``_route_and_filter_chunks``,
``_reconcile_chunk_hyphens``) are functions earlier S2 slices moved OUT of
``pipeline.py`` at their original size. The orchestrator got shorter and the
100-line target did not get closer, and nothing was measuring the difference.
It is measured now. Empty is the goal.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).parent.parent / "src" / "corrigenda" / "core"
PIPELINE = CORE / "pipeline.py"

#: The target the plan sets for the orchestrator, in lines.
_MODULE_TARGET = 800

#: Today's ceiling for the orchestrator. Lower it as slices land; never raise.
_MODULE_BUDGET = 970

#: The longest a function may be once the split is finished.
_FUNCTION_TARGET = 100

#: Every ``core`` function still over :data:`_FUNCTION_TARGET`, keyed
#: ``module.py::name``, each with its current ceiling. An entry may shrink,
#: never grow; removing one is how a slice records that it finished.
_OVERSIZED: dict[str, int] = {
    "acceptance.py::_loss_policy_pass": 107,
    "editing.py::_apply_line_ops": 114,
    "editing.py::apply_edit_script": 103,
    "hyphenation.py::enrich_chunk_lines": 101,
    "hyphenation.py::reconcile_hyphen_pair": 110,
    "pairing.py::link_hyphen_pairs": 119,
    "pipeline.py::_run_chunk": 104,
    "reconcile.py::_reconcile_chunk_hyphens": 158,
    "rendering.py::_render_outputs": 140,
    "routing.py::_route_and_filter_chunks": 110,
    "validator.py::validate_llm_response": 149,
}


def _function_lengths() -> dict[str, int]:
    """Every function defined in ``core``, keyed ``module.py::name``.

    Nested definitions are skipped: their lines are already counted in the
    enclosing definition, and counting both would double-charge a closure.
    """
    lengths: dict[str, int] = {}
    for path in sorted(CORE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nested: set[str] = set()
        local: dict[str, int] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            local[node.name] = (
                node.end_lineno - node.lineno + 1 if node.end_lineno else 0
            )
            nested |= {
                child.name
                for child in ast.walk(node)
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                and child is not node
            }
        for name, size in local.items():
            if name not in nested:
                lengths[f"{path.name}::{name}"] = size
    return lengths


def test_orchestrator_budget_is_a_ratchet() -> None:
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


def test_no_unnamed_function_exceeds_the_target() -> None:
    over = {
        key: size
        for key, size in _function_lengths().items()
        if size > _FUNCTION_TARGET and key not in _OVERSIZED
    }
    assert not over, (
        f"{over} exceed the {_FUNCTION_TARGET}-line target and are not on the "
        "known-oversized list. Moving a long function into a new module is "
        "not a split — break it up where it lands."
    )


@pytest.mark.parametrize("key", sorted(_OVERSIZED))
def test_known_oversized_functions_only_shrink(key: str) -> None:
    lengths = _function_lengths()
    assert key in lengths, (
        f"{key} no longer exists — drop it from _OVERSIZED, the entry is the "
        "debt, not the function."
    )
    assert lengths[key] <= _OVERSIZED[key], (
        f"{key} grew to {lengths[key]} lines, over its pinned {_OVERSIZED[key]}. "
        "Known-oversized functions may only shrink."
    )


def test_finished_functions_are_not_still_listed() -> None:
    """Once a function reaches the target, its entry must go — otherwise the
    list stops describing the remaining debt."""
    lengths = _function_lengths()
    done = {
        key: lengths[key]
        for key in _OVERSIZED
        if key in lengths and lengths[key] <= _FUNCTION_TARGET
    }
    assert not done, (
        f"{done} are within the {_FUNCTION_TARGET}-line target — remove them "
        "from _OVERSIZED so the list still shows what is left."
    )
