"""Adversarial-review fixes over the audit remediation wave.

Each test pins one confirmed review finding:

  * planner: pydantic ``model_copy(update=…)`` BYPASSES validation, so the
    window walk needs its own progress guard (reproduced infinite loop);
  * ALTO parser: empty-string block IDs crashed the IDNEXT walk with a
    raw KeyError; an IDNEXT pointing outside the page (cross-page article
    continuation — a legitimate METS/ALTO pattern) must end the chain,
    not void the whole declared order;
  * ALTO parser: without ``PrintSpace``, margin-nested blocks must stay
    out of correction scope (the recursive walk swept them in);
  * parsers: the duplicate-ID gate must scan the WHOLE tree (the
    rewriters match document-wide, so a margin line reusing a body ID
    used to explode only at rewrite time, after the full LLM spend);
  * identity: block IDs are page-scoped — per-page OCR exports reusing
    block_0/block_1 on every page are legitimate.

Shrinking on purpose: the five hyphen findings (the LINE-mode cap cut,
synthetic geometry, the partner and cross-page-partner reverts) moved to
``tests/hyphenation/`` (`RM-05b`).
"""

from __future__ import annotations

from pathlib import Path


from corrigenda.core.planner import plan_page
from corrigenda.core.schemas import (
    ChunkGranularity,
    ChunkPlannerConfig,
)
from corrigenda.formats.alto.parser import parse_alto_file

from tests.identity._docs import _alto_doc, _tb, _write

from tests.test_planner_budget_and_cross_chunk_guard import _line, _page

# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def test_window_walk_survives_validation_bypass():
    """model_copy(update=…) bypasses the P2-5 validator; without the
    progress clamp this spun forever (reproduced before the fix)."""
    cfg = ChunkPlannerConfig().model_copy(
        update={"line_window_size": 8, "line_window_overlap": 8}
    )
    lines = [_line(i, "abc") for i in range(20)]
    plan = plan_page(_page(lines), "d1", cfg, force_granularity=ChunkGranularity.WINDOW)
    covered = {lid for c in plan.chunks for lid in c.targets()}
    assert covered == {lm.line_id for lm in lines}


# ---------------------------------------------------------------------------
# ALTO parser — IDNEXT robustness + margins
# ---------------------------------------------------------------------------


def test_alto_empty_string_block_id_does_not_crash(tmp_path: Path):
    """ID=\"\" used to KeyError the IDNEXT chain walk."""
    body = (
        "<PrintSpace>"
        + _tb("B1", "un", idnext="B2", vpos=10)
        + _tb("", "sans id", vpos=50)
        + _tb("B2", "deux", vpos=90)
        + "</PrintSpace>"
    )
    pages, _ = parse_alto_file(_write(tmp_path, _alto_doc(body)), "t.xml")
    texts = [lm.ocr_text for lm in pages[0].lines]
    assert sorted(texts) == sorted(["un", "sans id", "deux"])


def test_alto_idnext_to_next_page_ends_chain_without_voiding_order(tmp_path: Path):
    """A cross-page IDNEXT (valid METS/ALTO continuation) must be treated
    as end-of-chain — the rest of the page's declared order is KEPT
    (before the fix the whole declaration fell back to document order)."""
    body = (
        "<PrintSpace>"
        + _tb("B1", "premier", idnext="B3", vpos=10)
        + _tb("B2", "troisieme", idnext="NEXT_PAGE_BLOCK", vpos=50)
        + _tb("B3", "deuxieme", idnext="B2", vpos=90)
        + "</PrintSpace>"
    )
    pages, _ = parse_alto_file(_write(tmp_path, _alto_doc(body)), "t.xml")
    assert [lm.ocr_text for lm in pages[0].lines] == [
        "premier",
        "deuxieme",
        "troisieme",
    ]


def test_alto_margin_blocks_stay_out_of_scope_without_printspace(tmp_path: Path):
    """No PrintSpace: the whole Page is the container, but margin-nested
    blocks (running heads, page numbers) must remain excluded — the
    historical direct-children lookup excluded them implicitly."""
    body = (
        "<TopMargin>"
        + _tb("M1", "titre courant", vpos=5)
        + "</TopMargin>"
        + _tb("B1", "corps du texte", vpos=100)
    )
    pages, _ = parse_alto_file(_write(tmp_path, _alto_doc(body)), "t.xml")
    assert [lm.ocr_text for lm in pages[0].lines] == ["corps du texte"]


# ---------------------------------------------------------------------------
# Identity — block scope
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pairing — synthetic geometry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# PAGE — whole-tree duplicate gate
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pipeline — pair-atomic duplicate revert
# ---------------------------------------------------------------------------
