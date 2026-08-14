"""Who is allowed to write a line's decision (`RM-01`).

A line's terminal decision is three fields — ``corrected_text``,
``status``, and the trace's ``fallback_reason``. Twenty-two statements
across seven functions in five modules wrote the first two when this
ratchet was set, and nothing said which was authoritative; what kept them
coherent was the order the document-wide passes happen to run in, itself
unenforced (see ``test_finalize_pass_order.py``). The repository has
already paid for this once: `L9` was two lines keeping their source text
while reporting as ``CORRECTED``.

The allowlist below is what is left, and as of `RM-01` phase 3 it is
**empty**: every write goes through ``core/decide.py``. It got there one
site per commit, 22 → 15 → 13 → 6 → 0, without a number ever being
raised.

From here the file changes job. It stopped being a burn-down and became
a boundary: the interesting assertion is no longer "the list shrank" but
``test_no_unlisted_function_writes_a_decision``, which now fails on the
FIRST statement anywhere in the package that writes ``corrected_text`` or
``status`` outside the sole writer.

The burn-down machinery went with the burn-down. Two tests here walked
``_WRITE_SITES`` entry by entry — shrink-only, and delete-at-zero, the
semantics ``test_orchestrator_budget.py`` still runs on its own non-empty
dicts. At zero they walked nothing: one skipped every run with "got empty
parameter set", the other passed green on an empty loop. The list itself
stays, as the record of what was migrated and as the comparand below,
but nothing iterates it any more — the docstring above already forbids
refilling it, so the only path that would have woken those two tests is
a path the file rules out.

``core/decide.py`` is exempt — it is the destination. Which makes it the
one thing that must be checked positively, and
``test_only_the_sole_writer_is_exempt`` is where: an empty scan is the
right answer here AND what a broken scan returns, so something has to
assert the scanner can still see a write. What counts as one is
``tests/_ast_writes.py``'s business.
"""

from __future__ import annotations

import ast

from tests._ast_writes import written_attributes
from tests._paths import SRC

SRC = SRC

#: The two manifest fields that carry a line's decision. ``fallback_reason``
#: lives on the trace and is characterised separately, in
#: ``test_fallback_reason_precedence.py``.
_DECISION_FIELDS = frozenset({"corrected_text", "status"})

#: The module that owns these writes. The exemption predates the module —
#: written that way so `RM-01` added a file rather than also amending this
#: test — and outlives the migration unchanged.
_SOLE_WRITER = "core/decide.py"

#: Every function writing a decision field outside the sole writer, with
#: its statement count. Measured at 22 writes across 7 functions when the
#: ratchet was set (2026-08-06, `cf6cfc1`); emptied by `RM-01` phase 3.
#: It must STAY empty — an entry here now is a regression, not a plan.
_WRITE_SITES: dict[str, int] = {}

#: The debt, in one number. It may only go down.
_TOTAL_WRITES = 0


def _write_sites() -> dict[str, int]:
    """``path/to/module.py::QualifiedName`` → decision writes it contains.

    Keys match ``test_orchestrator_budget.py``'s convention so the two
    ratchets read the same way. Functions nested inside another function
    are attributed to the enclosing definition — a closure that reverts a
    line is still that function writing a decision.

    What counts as a write is ``tests/_ast_writes.py``'s business, and
    deliberately not this file's: the predicate lived here inline, saw
    only ``line.status = x``, and missed the tuple and augmented forms —
    so the boundary below forbade one spelling of the violation and
    waved the others through.
    """
    sites: dict[str, int] = {}

    def writes(node: ast.AST) -> int:
        return sum(
            1
            for sub in ast.walk(node)
            for name in written_attributes(sub)
            if name in _DECISION_FIELDS
        )

    def visit(body: list[ast.stmt], rel: str, prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, rel, f"{prefix}{node.name}.")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                count = writes(node)
                if count:
                    sites[f"{rel}::{prefix}{node.name}"] = count

    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel == _SOLE_WRITER:
            continue
        visit(ast.parse(path.read_text(encoding="utf-8")).body, rel, "")
    return sites


def test_no_unlisted_function_writes_a_decision() -> None:
    """A new write site is the regression this whole file exists to catch."""
    unlisted = {
        key: count for key, count in _write_sites().items() if key not in _WRITE_SITES
    }
    assert not unlisted, (
        f"{unlisted} write corrected_text/status and are not on the known "
        "list. A line's decision is written in too many places already "
        "(RM-01); route it through core/decide.py rather than adding an "
        "eighth site."
    )


def test_the_total_is_the_debt_and_only_goes_down() -> None:
    """One number, so progress is legible without diffing a dict."""
    total = sum(_write_sites().values())
    assert total <= _TOTAL_WRITES, (
        f"{total} decision writes, up from the pinned {_TOTAL_WRITES}. "
        "RM-01 takes this to zero outside core/decide.py; it does not go up "
        "on the way."
    )
    assert sum(_WRITE_SITES.values()) == _TOTAL_WRITES, (
        "_TOTAL_WRITES disagrees with _WRITE_SITES — lower both together "
        "when a site is migrated."
    )


def test_only_the_sole_writer_is_exempt() -> None:
    """The exempt module has to be a writer, or the boundary is vacuous.

    This is the anti-vacuity guard: ``test_no_unlisted_...`` above passes
    on an empty scan, and an empty scan is also what a broken scan
    returns. If the one module allowed to write the field has stopped
    writing it, the scan is not measuring what it claims to."""
    assert (
        (SRC / _SOLE_WRITER).read_text(encoding="utf-8").count(".corrected_text = ")
    ), "the sole writer must actually write the field it is exempt for"
