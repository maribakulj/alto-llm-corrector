"""No test module may compute a repository path from its own depth.

``Path(__file__)`` plus four ``.parent`` hops, then ``/ "examples"``, is
correct until the file moves — and `RM-05b` moves test files on purpose.
The failure mode is what makes this worth a test rather than a convention:

(The chain is spelled out in words rather than written here, because this
module scans for it and would otherwise fail on its own docstring. It did,
on the first run.)

  * ``test_line_ref.py`` moved into ``tests/identity/`` and resolved
    ``examples/sample.xml`` one directory too shallow. It failed loudly,
    which was the lucky outcome.
  * The seven sites fixed one slice earlier were guarded by
    ``skipif(not PATH.exists())``. Moved, they would have resolved to
    nothing, skipped, and reported success.

A suite that silently stops running is worse than one that breaks, so the
arithmetic lives in :mod:`tests._paths` and nowhere else.

Three modules are exempt, each for a reason that survives a move:
``_paths`` itself is the definition; ``corpus_gt/derive_ocr17.py`` and
``external_corpus/fetch.py`` are standalone scripts, run by hand outside
pytest, and anchor on their OWN directory rather than on the tree above
them.
"""

from __future__ import annotations

import re

from tests._paths import TESTS

#: ``Path(__file__)`` followed by anything that climbs: ``.parent``,
#: ``.parents[n]``, or ``.resolve()`` in between. A bare ``Path(__file__)``
#: that never climbs is not depth arithmetic and is not matched.
_CLIMBS = re.compile(r"Path\(__file__\)(?:\.resolve\(\))?\.(parent\b|parents\[)")

#: Files allowed to know where they are.
_ANCHORED_ON_PURPOSE = {
    "_paths.py": "the definition — something has to compute it once",
    "corpus_gt/derive_ocr17.py": (
        "a standalone script, run by hand; anchors on its own directory"
    ),
    "external_corpus/fetch.py": (
        "a standalone fetch script; anchors on its own directory"
    ),
}


def _modules() -> list:
    return sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_module_walks_up_from_its_own_file() -> None:
    offenders = {}
    for path in _modules():
        relative = str(path.relative_to(TESTS))
        if relative in _ANCHORED_ON_PURPOSE:
            continue
        hits = _CLIMBS.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders[relative] = len(hits)
    assert not offenders, (
        f"module(s) computing a path from their own depth: {offenders}. "
        "Import REPO / PKG / SRC / TESTS / EXAMPLES from tests._paths "
        "instead — a test file that knows how deep it sits cannot be moved, "
        "and moving it may make it SKIP rather than fail."
    )


def test_the_exemptions_are_still_there_and_still_climb() -> None:
    """An exemption that stopped needing one is a hole with a name on it."""
    for relative, reason in _ANCHORED_ON_PURPOSE.items():
        path = TESTS / relative
        assert path.exists(), f"exempt file is gone: {relative} ({reason})"
        assert _CLIMBS.search(path.read_text(encoding="utf-8")), (
            f"{relative} no longer walks up from __file__ — drop its "
            "exemption rather than leaving a name in the list."
        )


def test_the_scan_reads_the_whole_suite() -> None:
    """Green by vacuity would look exactly like green."""
    seen = _modules()
    assert len(seen) >= 100, (
        f"only {len(seen)} modules scanned under {TESTS} — the walk is not "
        "seeing the suite, and this guard proves nothing."
    )
