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

Same semantics as ``test_orchestrator_budget.py``, deliberately: an entry
may shrink, never grow; an entry that reaches zero must be deleted rather
than left at zero; a write in a function that is not listed fails
immediately. ``core/decide.py`` is exempt — it is the destination, and
the exemption was written before the module existed so that `RM-01` adds
a file rather than also amending this rule.
"""

from __future__ import annotations

import ast

import pytest

from tests._ast_writes import written_attributes
from tests._paths import SRC

SRC = SRC

#: The two manifest fields that carry a line's decision. ``fallback_reason``
#: lives on the trace and is characterised separately, in
#: ``test_fallback_reason_precedence.py``.
_DECISION_FIELDS = frozenset({"corrected_text", "status"})

#: The module that will own these writes. Exempt before it exists so
#: `RM-01` adds a file rather than also amending this test.
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


@pytest.mark.parametrize("key", sorted(_WRITE_SITES))
def test_known_write_sites_only_shrink(key: str) -> None:
    sites = _write_sites()
    if key not in sites:
        pytest.fail(
            f"{key} no longer writes a decision — remove its entry, the "
            "entry is the debt, not the function."
        )
    assert sites[key] <= _WRITE_SITES[key], (
        f"{key} grew to {sites[key]} decision writes, over its pinned "
        f"{_WRITE_SITES[key]}. Known write sites may only shrink."
    )


def test_emptied_sites_are_not_still_listed() -> None:
    """`RM-01` migrates one site per commit; an entry that reached zero has
    to go, or the list stops describing what is left."""
    sites = _write_sites()
    done = sorted(key for key in _WRITE_SITES if key not in sites)
    assert not done, (
        f"{done} no longer write a decision — drop them from _WRITE_SITES "
        "so the remaining entries are the remaining work."
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
    """``core/decide.py`` may write decisions freely; nothing else may.

    Deliberately holds at the END state too: when ``_WRITE_SITES`` is
    empty the scan returns nothing and the exemption is still the only
    one. A test that asserted "migration under way" would start failing
    exactly when `RM-01` finished."""
    assert not [key for key in _write_sites() if key.startswith(_SOLE_WRITER)]
    if not (SRC / _SOLE_WRITER).exists():
        pytest.skip("core/decide.py does not exist yet — RM-01 creates it")
    assert (
        (SRC / _SOLE_WRITER).read_text(encoding="utf-8").count(".corrected_text = ")
    ), "the sole writer must actually write the field it is exempt for"
