"""What made the acceptance site safe to translate (`RM-01`, site 6/7).

``acceptance._apply_line_acceptance`` did not write a fallback: it wrote
``lm.corrected_text = result.text`` and then chose a status in an
``if``/``else``. Translating that into ``decide.accept`` /
``decide.fall_back`` is only correct while one property of
``guards.check_line`` holds:

    **every branch that rejects returns ``text=source_ocr``.**

If a rejection branch ever returned something else — a repaired text, a
truncation, a partial — then ``fall_back``, which writes ``ocr_text`` by
construction, would silently replace the guard's chosen text with the raw
source. That is a corruption of the delivered file, produced by a
refactor that looks like a rename.

It also has to carry a reason: ``fall_back`` records one, and a rejection
with ``reason=None`` would put the literal fallback ``"rejected"`` on the
trace where a real cause belongs.

Both are pinned here, structurally rather than by example, so that adding
a sixth rejection branch to ``check_line`` without returning the source
text fails immediately instead of at the next byte-parity run.
"""

from __future__ import annotations

import ast

import pytest

from saknussemm.core.guards import check_line
from saknussemm.core.schemas import GuardConfig

from tests._paths import SRC

SRC = SRC


def _check_line_returns() -> list[dict[str, str]]:
    """Every ``AcceptanceResult(...)`` ``check_line`` returns, as source."""
    tree = ast.parse((SRC / "core" / "guards.py").read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "check_line"
    )
    return [
        {kw.arg: ast.unparse(kw.value) for kw in node.value.keywords if kw.arg}
        for node in ast.walk(fn)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
    ]


def test_every_rejection_branch_returns_the_source_text() -> None:
    """The property ``decide.fall_back`` relies on at this site."""
    returns = _check_line_returns()
    assert returns, "check_line's returns are no longer statically readable"
    rejections = [r for r in returns if r.get("accepted") == "False"]
    assert rejections, "no rejection branch found — the scan is broken"
    wrong = [r for r in rejections if r.get("text") != "source_ocr"]
    assert not wrong, (
        f"{wrong} reject without returning source_ocr. "
        "acceptance._apply_line_acceptance translates a rejection into "
        "decide.fall_back, which writes ocr_text by construction — a branch "
        "returning anything else would have its text silently replaced."
    )


def test_every_rejection_branch_carries_a_reason() -> None:
    returns = _check_line_returns()
    unnamed = [
        r
        for r in returns
        if r.get("accepted") == "False" and not r.get("reason", "").strip("'\"")
    ]
    assert not unnamed, (
        f"{unnamed} reject without a reason — decide.fall_back would record "
        "the literal placeholder instead of a cause."
    )


@pytest.mark.parametrize(
    ("source", "proposal"),
    [
        ("le chat noir dort", "ZZZZ QQQQ WWWW"),  # too_different_from_source
        ("une souris", "le chat noir dort tranquillement ici"),  # length + distance
        ("", "quelque chose"),  # degenerate source
    ],
)
def test_a_rejected_proposal_yields_the_source_at_runtime(
    source: str, proposal: str
) -> None:
    """The static scan says what the branches return; this says the object
    actually built agrees with it.

    The rejection is **asserted**, not assumed. It used to be
    ``if result.accepted: pytest.skip(...)``, which conditioned the whole
    verdict on the guard still rejecting — so the test disarmed itself
    exactly when it mattered. Measured 2026-08-17: with guard 1 made to
    accept, all three parameters **SKIPPED** instead of failing, and the
    file's two static scans stayed green; only one test elsewhere in the
    suite noticed.

    If a guard change makes one of these pairs acceptable, this must go red
    and the pair must be replaced by one the guards still refuse — the
    file's subject is what a REJECTION returns, and a fixture that stopped
    being rejected has stopped being a fixture.
    """
    result = check_line(source, proposal, None, None, config=GuardConfig())
    assert not result.accepted, (
        f"{proposal!r} against {source!r} is now ACCEPTED, so this pair says "
        "nothing about what a rejection returns. Replace it with a pair the "
        "guards still refuse rather than letting the case skip: a test that "
        "steps aside when its premise fails is a test that reports success "
        "for the one reason it exists to catch."
    )
    assert result.text == source
    assert result.reason
