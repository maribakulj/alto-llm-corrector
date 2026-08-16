"""Which test files can break when the hyphen unit changes.

Gathering the suite was for `S1`, and gathering alone does not hold: a
test written next month lands wherever its author happens to be, the
directory silently stops being the whole net, and `S1` reopens the same
question it opened this time — *which files break if I touch this?*

So the answer is pinned rather than hoped for. Every module that reaches
``saknussemm.core.pairing``, ``.units`` or ``.hyphenation`` lives in this
directory, except five named below, each for a reason that is not "it grew
there".

The list is a ratchet in the ordinary way: a sixth file is a decision
someone makes on purpose, and the failure names it.

The match is on the IMPORT PATH, not on the bare module name — the first
run of this test caught its own author listing ``test_parser.py``, which
only cites ``core.pairing.HYPHEN_CHARS`` in a docstring. Naming a module
in prose is not a way to break when it changes.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._paths import TESTS

#: This directory, named rather than derived — a guard that asks where it
#: is would move with the files it is supposed to keep in place.
HERE = "hyphenation"

#: The three modules `S1` will rewrite. A test that imports one of them is
#: a test that can break when it does.
_HYPHEN_MODULES = re.compile(r"saknussemm\.core\.(pairing|units|hyphenation)\b")

#: Test modules outside this directory that reach one of the three, and
#: why each one is not a hyphenation test that wandered off.
_ELSEWHERE: dict[str, str] = {
    "decision/test_reconcile_translation.py": (
        "classify_reconcile_outcome is read as a DECISION writer — the "
        "subject is which pass writes the outcome, not what a pair becomes"
    ),
    "test_edit_producer.py": (
        "enrich_chunk_lines is called to build a realistic payload; the "
        "subject is the producer contract"
    ),
    "test_import_contract.py": (
        "names the modules as strings in a subprocess import probe — it "
        "never imports them"
    ),
    "test_internal_seams_are_named.py": (
        "names them as strings in the map of which internals the suite may "
        "reach — it classifies them, it does not call them"
    ),
    "test_payload_truthfulness.py": (
        "reads the partner refs to check what the PAYLOAD tells a producer "
        "— the subject is the request, not the pair"
    ),
    "test_smoke.py": ("imports every public module by name to prove the package loads"),
}


def _modules() -> list[Path]:
    return sorted(p for p in TESTS.rglob("test_*.py") if "__pycache__" not in p.parts)


def _reaches_hyphen_code(path: Path) -> bool:
    return _HYPHEN_MODULES.search(path.read_text(encoding="utf-8")) is not None


def test_every_other_hyphen_test_is_named() -> None:
    strays = [
        str(p.relative_to(TESTS))
        for p in _modules()
        if p.parent.name != HERE and _reaches_hyphen_code(p)
    ]
    unlisted = sorted(set(strays) - set(_ELSEWHERE))
    assert not unlisted, (
        f"test module(s) reaching the hyphen unit from outside "
        f"tests/{HERE}/: {unlisted}. If the subject is the hyphen unit, it "
        f"belongs in tests/{HERE}/ where `S1` will look for it. If it is "
        "not, add it here with the reason — the point of the list is that "
        "every exception has one."
    )


def test_the_named_exceptions_still_exist_and_still_qualify() -> None:
    """A stale allowlist entry hides the next stray behind a name."""
    gone = [name for name in _ELSEWHERE if not (TESTS / name).exists()]
    assert not gone, f"the allowlist names file(s) that moved or died: {gone}"

    clean = [
        name
        for name in _ELSEWHERE
        if (TESTS / name).exists() and not _reaches_hyphen_code(TESTS / name)
    ]
    assert not clean, (
        f"these no longer reach the hyphen unit and should leave the "
        f"allowlist: {clean}. An exception nobody removes stops being one."
    )


def test_the_scan_sees_the_directory_it_guards() -> None:
    """Guard against green by vacuity: the regex has to match something."""
    here = [p for p in _modules() if p.parent.name == HERE and _reaches_hyphen_code(p)]
    assert len(here) >= 10, (
        f"only {len(here)} modules in tests/{HERE}/ match the hyphen-module "
        "pattern — the pattern has drifted and the guard now proves nothing."
    )
