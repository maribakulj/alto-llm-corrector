"""Who is allowed to write a line's decision (`RM-01`).

A line's terminal decision is three fields — ``corrected_text``,
``status``, and the trace's ``fallback_reason`` — and today 22 statements
across 7 functions in 5 modules write the first two. Nothing says which
of them is authoritative; what keeps them coherent is the order the
document-wide passes happen to run in, which is itself unenforced (see
``test_finalize_pass_order.py``). The repository has already paid for
this once: `L9` was two lines keeping their source text while reporting
as ``CORRECTED``, and the shape that allowed it is still here.

This test is the ratchet for closing that. The allowlist below is the
debt, measured. `RM-01` empties it by routing every write through a
single ``core/decide.py``, one site per commit, and this file goes from
22 to 0 without ever needing a number raised.

Same semantics as ``test_orchestrator_budget.py``, deliberately: an entry
may shrink, never grow; an entry that reaches zero must be deleted rather
than left at zero; a write in a function that is not listed fails
immediately. ``core/decide.py`` is exempt in advance — it does not exist
yet, and writing the exemption now means `RM-01` adds a module instead of
also editing this rule.

One entry is not a fallback and should be looked at on its own when the
time comes: ``core/finalize.py::_preserve_break_chars`` rewrites the text
of an ACCEPTED correction rather than reverting anything. Whether it
belongs behind ``decide.accept()`` or stays a normalisation applied
before decisions materialise is a real question, not an oversight — it is
listed here because it writes the field, and the point of the list is
that nothing writing the field is invisible.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent.parent / "src" / "corrigenda"

#: The two manifest fields that carry a line's decision. ``fallback_reason``
#: lives on the trace and is characterised separately, in
#: ``test_fallback_reason_precedence.py``.
_DECISION_FIELDS = frozenset({"corrected_text", "status"})

#: The module that will own these writes. Exempt before it exists so
#: `RM-01` adds a file rather than also amending this test.
_SOLE_WRITER = "core/decide.py"

#: Every function writing a decision field, with its statement count.
#: Measured 2026-08-06 at `cf6cfc1`. `RM-01` takes these to zero.
_WRITE_SITES: dict[str, int] = {
    "core/acceptance.py::_apply_line_acceptance": 7,
    "core/acceptance.py::_apply_unit_reverts": 2,
    "core/finalize.py::_preserve_break_chars": 1,
    "core/outcome.py::_extend_to_units": 2,
    "core/outcome.py::_fall_back_to_source": 2,
    "core/reconcile.py::_reconcile_one_pair": 6,
    "core/routing.py::_confirm_skipped_lines": 2,
}

#: The debt, in one number. It may only go down.
_TOTAL_WRITES = 22


def _write_sites() -> dict[str, int]:
    """``path/to/module.py::QualifiedName`` → decision writes it contains.

    Keys match ``test_orchestrator_budget.py``'s convention so the two
    ratchets read the same way. Functions nested inside another function
    are attributed to the enclosing definition — a closure that reverts a
    line is still that function writing a decision.
    """
    sites: dict[str, int] = {}

    def writes(node: ast.AST) -> int:
        count = 0
        for sub in ast.walk(node):
            targets: list[ast.expr] = []
            if isinstance(sub, ast.Assign):
                targets = list(sub.targets)
            elif isinstance(sub, ast.AnnAssign):
                targets = [sub.target]
            count += sum(
                1
                for t in targets
                if isinstance(t, ast.Attribute) and t.attr in _DECISION_FIELDS
            )
        return count

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


def test_the_sole_writer_is_exempt_once_it_exists() -> None:
    """The exemption is written before the module is, so `RM-01` adds a
    file instead of also editing this test. When ``core/decide.py`` lands
    it may write decisions freely; nothing else may."""
    assert _SOLE_WRITER not in _write_sites()
    decide = SRC / _SOLE_WRITER
    if not decide.exists():
        pytest.skip("core/decide.py does not exist yet — RM-01 creates it")
    assert _write_sites(), "with decide.py in place, migration is under way"
