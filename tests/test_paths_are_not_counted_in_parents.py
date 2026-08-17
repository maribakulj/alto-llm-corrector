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
  * The seven sites fixed one slice earlier were guarded by a skip
    conditioned on the fixture being present. Moved, they would have
    resolved to nothing, skipped, and reported success. (Written in words:
    this module scans for that shape too, and would otherwise report its
    own prose — the second time it has had to do this.)

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

#: The second shape, and the one that got through. Flattening the tree on
#: 2026-08-16 broke a line that took a name already derived from the file
#: and climbed two more levels off it — depth arithmetic the pattern above
#: cannot see, because ``Path(__file__)`` is nowhere near it. (Written in
#: words for the same reason as the docstring: this module scans for the
#: shape and would otherwise report itself, which it did on the first run.)
#: Climbing two or more levels off ANY name is the tell — one hop up is
#: ordinary, "the directory this file is in"; a chain of them is a claim
#: about how deep the tree is.
_CLIMBS_FROM_A_NAME = re.compile(r"\b\w+\.parent\.parent\b|\b\w+\.parents\[[1-9]")

#: A test that skips when a COMMITTED fixture is missing. The condition can
#: never be true in a healthy checkout, so the guard protects nothing — but
#: the day the fixture moves or is deleted, it converts a loud failure into
#: a silent skip, and a suite that quietly stops running looks exactly like
#: a suite that passes. Two of these survived until 2026-08-16, on files
#: this repository commits.
#:
#: A fixture that is genuinely optional — fetched, generated, behind an
#: extra — is a different case and belongs behind `importorskip` or an
#: explicit marker, which name the reason rather than testing for a file.
#: Three forms, because it only knew one and two escaped through the others.
#: Measured 2026-08-17: ``tests/test_chunk_planner.py`` and
#: ``tests/test_research_boundary.py`` both tested a COMMITTED fixture's
#: existence and skipped imperatively, and this guard reported nothing.
#: Moving ``examples/X0000002.xml`` aside then made
#: ``test_corpus_chains_never_split`` SKIP while all four tests here PASSED —
#: word for word the failure this file exists to prevent.
#:
#: Every pattern is assembled from fragments, and this comment describes the
#: forms rather than quoting them, because the first version of it matched
#: ITSELF: the guard read its own documentation and reported the file as an
#: offender.
_EXISTS = "exists" + r"\(\)"
_SKIPS_ON_A_FILE = re.compile(
    "|".join(
        (
            # a skipif marker whose condition negates an existence check,
            # however the path is spelled — bare name or an expression in
            # parentheses
            "skip" + r"if\(\s*not\s+[^\n]*?\." + _EXISTS,
            # a negated existence check whose body calls the skip helper on
            # the next line, with or without a trailing comment
            r"if\s+not\s+[^:\n]*?\."
            + _EXISTS
            + r"[^:\n]*:\s*(?:#[^\n]*)?\n\s*pytest\."
            + "skip",
        )
    )
)

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
        source = path.read_text(encoding="utf-8")
        hits = len(_CLIMBS.findall(source)) + len(_CLIMBS_FROM_A_NAME.findall(source))
        if hits:
            offenders[relative] = hits
    assert not offenders, (
        f"module(s) computing a path from their own depth: {offenders}. "
        "Import REPO / PKG / SRC / TESTS / EXAMPLES from tests._paths "
        "instead — a test file that knows how deep it sits cannot be moved, "
        "and moving it may make it SKIP rather than fail."
    )


def test_no_test_skips_because_a_committed_fixture_is_missing() -> None:
    """A missing fixture must break the suite, not quieten it.

    This is the same failure this module was written for, wearing its
    other costume: instead of resolving a path one level too shallow and
    skipping, the test asks whether the file is there and skips politely
    when it is not. Both end with a green run that verified nothing.
    """
    offenders = {}
    for path in _modules():
        relative = str(path.relative_to(TESTS))
        hits = _SKIPS_ON_A_FILE.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders[relative] = len(hits)
    assert not offenders, (
        f"test(s) skipping on a fixture's existence: {offenders}. The "
        "fixtures in examples/ are committed — the condition cannot fire "
        "in a healthy checkout, and the day it can, it turns a loud "
        "failure into a silent skip. Let the test fail. If the fixture is "
        "genuinely optional, say WHY with importorskip or a marker."
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
