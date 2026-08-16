"""Where the repository's fixed directories are, computed once.

A test module that writes ``Path(__file__).parent.parent.parent.parent /
"examples"`` has hard-coded its own depth in the tree. That is invisible
while nothing moves, and `RM-05b` moves test files by design: the first
slice caught seven such sites in the files it was about to move, and the
second slice was still bitten by an eighth in a file it had not thought to
scan — ``test_line_ref.py`` resolved ``examples/sample.xml`` one directory
too shallow and failed outright.

Failing outright was the lucky half. Six of the original seven sat behind
``skipif(not PATH.exists())``: had they moved, they would have stopped
running and said nothing.

So the arithmetic lives here, once, in the one module that is never going
to move — and ``test_paths_are_not_counted_in_parents.py`` keeps it that
way.
"""

from __future__ import annotations

from pathlib import Path

#: The repository root — ``packages/lidenbrock/tests`` is three deep.
REPO = Path(__file__).resolve().parents[3]

#: The library's distribution root (``pyproject.toml`` lives here).
PKG = REPO / "packages" / "lidenbrock"

#: The library's importable source tree.
SRC = PKG / "src" / "lidenbrock"

#: This directory.
TESTS = PKG / "tests"

#: The sample ALTO/PAGE documents every corpus-backed test reads.
EXAMPLES = REPO / "examples"
