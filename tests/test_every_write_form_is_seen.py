"""What ``tests/_ast_writes.py`` must see, and what it must not.

Written because both decision ratchets shipped with the same blind spot
and neither could tell: their scans returned ``{}`` and ``(2, 0)``
whether the package was clean or the write was merely spelled in a form
the scan did not parse. A scanner with no test of its own is a green
light wired to nothing — the same failure mode ``tests/_paths.py``
records for the six ``skipif``-guarded tests that would have stopped
running and said nothing.

The cases below are the whole contract. Each is a form of Python, not a
site in the package: the point is that the guard sees the SHAPE, so it
keeps holding when the package changes.
"""

from __future__ import annotations

import ast

import pytest

import tests._ast_writes
from tests._ast_writes import written_attributes

#: A field name with no meaning outside this file — the cases test the
#: syntax, not ``status``.
_FIELD = "status"


def _writes(source: str) -> int:
    """How many writes of ``_FIELD`` the helper sees in ``source``."""
    return sum(
        written_attributes(node).count(_FIELD) for node in ast.walk(ast.parse(source))
    )


#: (label, source, expected writes). The four that a bare
#: ``isinstance(target, ast.Attribute)`` missed are marked; they are why
#: this file exists.
_FORMS = [
    ("plain", "obj.status = x", 1),
    ("annotated", "obj.status: int = x", 1),
    ("chained", "a.status = b.status = x", 2),
    ("tuple — MISSED before", "a.status, b.other = x, y", 1),
    ("tuple, both sides — MISSED before", "a.status, b.status = x, y", 2),
    ("list — MISSED before", "[a.status, b.status] = pair", 2),
    ("nested tuple — MISSED before", "(a.status, (b.status, c.other)) = z", 2),
    ("starred — MISSED before", "*a.status, rest = z", 1),
    ("augmented — MISSED before", "obj.status += x", 1),
    ("for target — MISSED before", "for obj.status in seq:\n    pass", 1),
    ("with target — MISSED before", "with ctx() as obj.status:\n    pass", 1),
    ("inside a nested function", "def f():\n    def g():\n        o.status = x", 1),
]

#: Forms that must NOT count. A scanner that over-counts is as useless as
#: one that under-counts: the ratchets pin exact numbers.
_NOT_WRITES = [
    ("read", "y = obj.status"),
    ("plain name", "status = x"),
    ("another attribute", "obj.ocr_text = x"),
    ("keyword argument", "LineDecision(status=x)"),
    ("dict key", "d['status'] = x"),
    ("subscript", "d.other[status] = x"),
]


@pytest.mark.parametrize(("label", "source", "expected"), _FORMS, ids=lambda v: str(v))
def test_every_assignment_form_counts(label: str, source: str, expected: int) -> None:
    assert _writes(source) == expected, (
        f"{label}: the helper sees {_writes(source)} write(s) of {_FIELD!r}, "
        f"expected {expected}. A form the scan cannot parse is a write the "
        "decision ratchets do not forbid."
    )


@pytest.mark.parametrize(("label", "source"), _NOT_WRITES, ids=lambda v: str(v))
def test_reads_and_lookalikes_do_not_count(label: str, source: str) -> None:
    assert _writes(source) == 0, (
        f"{label}: counted as a write of {_FIELD!r}. The ratchets pin exact "
        "numbers, so over-counting breaks them as surely as under-counting."
    )


def test_setattr_is_a_named_omission_not_an_oversight() -> None:
    """``setattr`` puts the field in a string, where no shape test reaches.

    Pinned so the omission stays a decision: whoever makes the helper see
    it has to delete this test on purpose, and whoever relies on the
    helper knows the hole is there. ``core/traces.py::_set_trace`` and
    ``core/rendering.py``'s ``put`` are the two funnels in the package;
    ``test_fallback_reason_precedence.py`` counts them by name instead."""
    assert _writes("setattr(obj, 'status', x)") == 0
    doc = tests._ast_writes.__doc__
    assert doc is not None and "setattr" in doc, (
        "the helper's docstring must keep naming setattr as uncovered — an "
        "unnamed hole is the failure this whole file is about"
    )
