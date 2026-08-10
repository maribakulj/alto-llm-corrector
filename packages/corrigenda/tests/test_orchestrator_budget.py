"""The orchestrator may only shrink, and no function is born oversized —
or born with fifteen parameters.

``core/pipeline.py`` was split into named components slice by slice, with
nothing but a line count in a plan document to say whether it was
progressing — so a slice that moved code *and* grew the file, or one that
lifted a stage out but left a 200-line function behind, would have read
exactly like a slice that worked. This module is the mechanical answer.

Five rules:

  1. **The orchestrator's budget is a ratchet.** ``_MODULE_BUDGET`` may be
     lowered when a slice lands and never raised. The 800-line target is
     reached; the ratchet is what keeps it reached, since the way an
     orchestrator regrows is one convenient method at a time.
  2. **A function over 100 lines must be named**, anywhere in the package.
     This is the rule that stops a split from laundering the problem:
     moving a 150-line method into a new module is not a split if it is
     still 150 lines when it lands.
  3. **A function taking more than 8 arguments must be named**, same scope.
  4. **A named function may only shrink** — in lines and in arguments.
  5. **Once it reaches a target its entry must go**, otherwise the list
     stops describing the remaining debt.

Two things changed here on 2026-08-06 (`RM-02`, `RM-10` in ``docs/PLAN.md``),
because the instrument was measuring the wrong thing over the wrong ground.

**Length alone rewards the defect it is supposed to prevent** (`RM-02`). A
gate on lines and nothing else is satisfied by pushing state out of a
function and into its signature, and that is what happened: the `S2` split
landed ``PageDriver._descend_granularity`` at 12 arguments and
``_attempt_chunk`` at 11, both comfortably under 100 lines. The histogram
tells the story on its own — fourteen functions in the 80-99 band and a
wall at 100. Nothing was wrong with the target; it was simply alone.
``_PARAMETER_TARGET`` is the second half, and the two are meant to be read
together: a function that satisfies one by violating the other has not
improved.

**The scan stopped at ``core/``** (`RM-10`). ``formats/`` was never looked
at, so the longest function in the package — ``_rebuild_line``, 203 lines,
on the path that writes the delivered file — was governed by nothing at
all, while the module that had already been cleaned up was governed
twice. The scan now covers ``src/corrigenda`` entire. The six ``formats/``
entries below are inscribed at their measured size; **inscribing is not a
plan to cut them.** ``formats/alto/rewriter.py`` is explicitly off-limits
until the byte-parity corpus is wider (`docs/PLAN.md`, § `RM`).

Keys are ``path/to/module.py::QualifiedName``. Both halves matter. The
path, because ``formats/alto/parser.py`` and ``formats/page/parser.py``
are two different files with functions of the same name. The qualified
name, because the previous key was the bare function name and silently
kept only the LAST definition of it in a file — ``core/confidence.py``
and ``core/quality.py`` each declare ``score_line`` / ``needs_correction``
twice (protocol, then implementation) and one of each pair was invisible
to this test.

A key names where a function lives TODAY. When a slice moves one, the key
moves with it — that is not a reset, and the pinned numbers may still only
go down. The lists are the debt, stated; they are not a queue anyone
should work through by default.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "corrigenda"
PIPELINE = SRC / "core" / "pipeline.py"

#: The target the plan sets for the orchestrator, in lines.
_MODULE_TARGET = 800

#: Today's ceiling for the orchestrator. Lower it as slices land; never raise.
_MODULE_BUDGET = 580

#: The longest a function may be once the split is finished.
_FUNCTION_TARGET = 100

#: The most arguments a function may take. ``self``/``cls`` do not count —
#: the question is how much a CALLER has to assemble, and a bound receiver
#: is not part of that.
_PARAMETER_TARGET = 8

#: Every function still over :data:`_FUNCTION_TARGET`, each with its current
#: ceiling. An entry may shrink, never grow; removing one is how a slice
#: records that it finished.
#:
#: The ``core/`` entries all predate `S2`. Two of them
#: (``link_hyphen_pairs``, ``reconcile_hyphen_pair``) are hyphen-partner
#: resolution, where the plan's standing rule says not to go without
#: finishing `S1` first. The six ``formats/`` entries were added by `RM-10`
#: at their measured size — they had never been under any gate.
#:
#: ``_loss_policy_pass`` left the list on 2026-08-06, and how it left is
#: the rule working as intended rather than a slice aimed at it: `RM-01`'s
#: order guard added four lines to it, the ratchet refused, and the remedy
#: it prescribes — lift a stage out, never raise the budget — took the
#: function from 107 to 91 by giving the sidecar construction its own
#: name.
_OVERSIZED: dict[str, int] = {
    "core/editing.py::_apply_line_ops": 114,
    "core/editing.py::apply_edit_script": 103,
    "core/hyphenation.py::enrich_chunk_lines": 101,
    "core/hyphenation.py::reconcile_hyphen_pair": 110,
    "core/pairing.py::link_hyphen_pairs": 119,
    "core/validator.py::validate_llm_response": 149,
    "formats/alto/parser.py::_parse_alto_file": 146,
    "formats/alto/parser.py::_parse_textline_hyphen_info": 105,
    "formats/alto/rewriter.py::_rebuild_line": 203,
    "formats/alto/rewriter.py::rewrite_alto_file": 161,
    "formats/page/parser.py::_parse_page_file": 125,
    "formats/page/rewriter.py::rewrite_page_file": 119,
}

#: Every function still over :data:`_PARAMETER_TARGET`, each with its current
#: ceiling. Same ratchet semantics as :data:`_OVERSIZED`.
#:
#: Read this list next to that one. It started at thirteen, nine of them on
#: the chunk path, wide for one reason: `S2` turned what used to be
#: ``self.retry_policy`` and friends into arguments, and the same handful of
#: per-run indices then travelled the whole chain by hand.
#:
#: `RM-03` bound three of those indices into
#: :class:`~corrigenda.core.workspace.PageWorkspace` and four entries left
#: this list outright. What remains is a different debt with a different
#: answer: the two ``pipeline`` constructors are configuration surface, not
#: threading, and ``_attempt_chunk``/``_build_correction_report`` assemble
#: from many sources rather than passing one thing along. `RM-03`
#: deliberately did not touch ``integrations/`` or ``producers/`` — the
#: list is a ceiling, not a queue.
_OVERPARAMETERISED: dict[str, int] = {
    "core/attempt.py::_attempt_chunk": 11,
    "core/driver.py::PageDriver._descend_granularity": 10,
    "core/driver.py::PageDriver._handle_chunk_failure": 9,
    "core/pipeline.py::CorrectionPipeline.__init__": 14,
    "core/pipeline.py::CorrectionPipeline.for_provider": 19,
    "core/report.py::_build_correction_report": 11,
    "formats/alto/rewriter.py::_emit_string": 11,
    "integrations/vision.py::VisionEditProducer.__init__": 11,
    "producers/llm_edit.py::LLMEditProducer.__init__": 9,
}


def _definitions() -> dict[str, tuple[int, int]]:
    """Every function in the package → ``(lines, arguments)``.

    Keyed ``path/to/module.py::QualifiedName``, where the qualification is
    the chain of enclosing CLASSES. Functions nested inside another function
    are not reported at all: their lines are already counted in the
    enclosing definition, and counting both would double-charge a closure.
    """
    found: dict[str, tuple[int, int]] = {}

    def visit(body: list[ast.stmt], rel: str, prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, rel, f"{prefix}{node.name}.")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = node.args
                names = [
                    a.arg
                    for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)
                    if a.arg not in ("self", "cls")
                ]
                lines = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                found[f"{rel}::{prefix}{node.name}"] = (lines, len(names))
                # Deliberately no descent: anything below is nested.

    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visit(tree.body, path.relative_to(SRC).as_posix(), "")
    return found


def _function_lengths() -> dict[str, int]:
    return {key: lines for key, (lines, _args) in _definitions().items()}


def _function_arities() -> dict[str, int]:
    return {key: args for key, (_lines, args) in _definitions().items()}


def test_the_scan_sees_the_whole_package() -> None:
    """A gate that stopped at ``core/`` left the longest function in the
    package ungoverned (`RM-10`). Pin the scope so it cannot narrow again."""
    keys = _definitions()
    assert any(k.startswith("core/") for k in keys)
    assert any(k.startswith("formats/alto/") for k in keys)
    assert any(k.startswith("formats/page/") for k in keys)
    assert any(k.startswith("integrations/") for k in keys)
    assert any(k.startswith("producers/") for k in keys)


def test_keys_are_unique_per_definition() -> None:
    """The previous key was the bare function name and silently dropped
    every same-named sibling in a file. Two pairs were invisible."""
    definitions = _definitions()
    for key in (
        "core/confidence.py::ConfidenceScorer.score_line",
        "core/confidence.py::HeuristicScorer.score_line",
        "core/quality.py::QEScorer.needs_correction",
        "core/quality.py::HeuristicQEScorer.needs_correction",
    ):
        assert key in definitions, f"{key} is not being measured"


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


def test_no_unnamed_function_exceeds_the_parameter_target() -> None:
    over = {
        key: count
        for key, count in _function_arities().items()
        if count > _PARAMETER_TARGET and key not in _OVERPARAMETERISED
    }
    assert not over, (
        f"{over} take more than {_PARAMETER_TARGET} arguments and are not on "
        "the known-overparameterised list. Splitting a function by handing "
        "its state to the halves is not a split — the state moved, the "
        "coupling did not."
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


@pytest.mark.parametrize("key", sorted(_OVERPARAMETERISED))
def test_known_overparameterised_functions_only_shrink(key: str) -> None:
    arities = _function_arities()
    assert key in arities, (
        f"{key} no longer exists — drop it from _OVERPARAMETERISED, the entry "
        "is the debt, not the function."
    )
    assert arities[key] <= _OVERPARAMETERISED[key], (
        f"{key} grew to {arities[key]} arguments, over its pinned "
        f"{_OVERPARAMETERISED[key]}. Known-overparameterised functions may "
        "only shrink."
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


def test_finished_signatures_are_not_still_listed() -> None:
    """Same rule for arguments: an entry that reached the target stops being
    debt and starts being noise."""
    arities = _function_arities()
    done = {
        key: arities[key]
        for key in _OVERPARAMETERISED
        if key in arities and arities[key] <= _PARAMETER_TARGET
    }
    assert not done, (
        f"{done} are within the {_PARAMETER_TARGET}-argument target — remove "
        "them from _OVERPARAMETERISED so the list still shows what is left."
    )
