"""Where the repository's fixed directories are, computed once.

A test module that writes ``Path(__file__).parent.parent.parent.parent /
"examples"`` has hard-coded its own depth in the tree. That is invisible
while nothing moves, and `RM-05b` moves test files by design: the first
slice caught seven such sites in the files it was about to move, and the
second slice was still bitten by an eighth in a file it had not thought to
scan — ``test_line_ref.py`` resolved ``examples/sample.xml`` one directory
too shallow and failed outright.

Failing outright was the lucky half. Six of the original seven sat behind
a skip conditioned on the fixture being present — spelled out in words
rather than in code, because a sibling module scans for that shape and
would report this docstring. Had those six moved, they would have stopped
running and said nothing.

So the arithmetic lives here, once, in the one module that is never going
to move — and ``test_paths_are_not_counted_in_parents.py`` keeps it that
way.
"""

from __future__ import annotations

from pathlib import Path

#: The repository root — ``tests/`` sits directly under it since the tree
#: was flattened on 2026-08-16.
REPO = Path(__file__).resolve().parents[1]

#: The library's distribution root (``pyproject.toml`` lives here). The
#: same directory as ``REPO`` now, and kept as a distinct name on purpose:
#: the two answer different questions, and a caller asking for the
#: distribution root should not have to know they currently coincide.
PKG = REPO

#: The library's importable source tree.
SRC = PKG / "src" / "saknussemm"

#: This directory.
TESTS = PKG / "tests"

#: The sample ALTO/PAGE documents every corpus-backed test reads.
EXAMPLES = REPO / "examples"
