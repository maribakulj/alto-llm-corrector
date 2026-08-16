"""Which statements write an attribute, in every form Python spells it.

Two ratchets ask the syntax tree the same question — ``tests/decision/
test_decision_write_exclusivity.py`` about ``corrected_text`` and
``status``, ``tests/decision/test_fallback_reason_precedence.py`` about
``fallback_reason`` — and each answered it inline, with its own
``isinstance(target, ast.Attribute)``. The two answers agreed, and were
wrong in the same places: they saw ``line.status = x`` and missed
``a.status, b.status = x, y``, ``line.corrected_text += x``, and
``for line.status in ...``. A guard that cannot see a write does not
forbid it, and both guards stand in front of `S1` — the next refactor to
move code through the very modules they watch.

So the forms live here once. The next one that turns up is added in one
place and both ratchets tighten together, which is the property the
duplication had already cost us.

Deliberately NOT covered — named here because a silent omission is the
thing this module exists against:

- ``setattr(obj, "status", x)``, and the ``**fields`` → ``setattr``
  funnels built on it (``core/traces.py::_set_trace``, the local ``put``
  in ``core/rendering.py``). There the field is a string, not syntax, so
  no shape test can see it. The precedence census counts those funnels
  by NAME instead, and that list is closed by hand: a third funnel has
  to be added to it.
- comprehension targets (``[... for obj.attr in seq]``). Legal, absent
  from the package, and it would read as a mistake if it appeared.
"""

from __future__ import annotations

import ast


def _leaves(target: ast.expr) -> list[ast.expr]:
    """A target expression's leaves.

    Tuple, list and starred unpacking nest arbitrarily — ``(a.x, [b.y,
    *rest]) = z`` is one target holding three.
    """
    if isinstance(target, ast.Tuple | ast.List):
        return [leaf for elt in target.elts for leaf in _leaves(elt)]
    if isinstance(target, ast.Starred):
        return _leaves(target.value)
    return [target]


def written_attributes(node: ast.AST) -> list[str]:
    """Attribute names ``node`` itself assigns, one entry per write.

    This statement only: callers walk the tree and ask about every node,
    so recursing into nested statements would double-count. Names are
    returned rather than deduplicated — ``a.status, b.status = x, y`` is
    two writes, and a ratchet that counts writes has to see two.
    """
    targets: list[ast.expr]
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign | ast.AugAssign):
        targets = [node.target]
    elif isinstance(node, ast.For | ast.AsyncFor):
        targets = [node.target]
    elif isinstance(node, ast.withitem):
        targets = [] if node.optional_vars is None else [node.optional_vars]
    else:
        return []
    return [
        leaf.attr
        for target in targets
        for leaf in _leaves(target)
        if isinstance(leaf, ast.Attribute)
    ]
