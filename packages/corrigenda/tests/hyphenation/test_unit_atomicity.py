"""A hyphen unit lives or falls back whole — never half of each.

Two ways to break that, and both are pinned here: a revert that reaches
only one member, leaving a joined word rewritten on one line and verbatim
on the other; and a planner cut that leaves a still-linked pair straddling
two chunks. Chains of three and four members are where it is decided — one
hop of partner extension is not enough, and the far endpoint of a chain is
the member a one-hop walk silently leaves corrected (ADR-010).

Two ``_line`` builders meet in this file: the hyphenation one (explicit
roles, string ids) is aliased ``_hyphen_line``, and the planner suite's
sequential ``_line(i, text)`` keeps its name because the cases moved here
call it that.
"""

from __future__ import annotations

import pytest

from corrigenda.core.acceptance import _apply_unit_reverts
from corrigenda.core.identity import line_ref
from corrigenda.core.planner import plan_page
from corrigenda.core.schemas import (
    ChunkGranularity,
    ChunkPlannerConfig,
    HyphenRole,
    LineManifest,
    LineStatus,
)

from tests.hyphenation._lines import _line as _hyphen_line
from tests.test_planner_budget_and_cross_chunk_guard import _chain, _line, _page


def _reconciled_chain(*ocr_texts: str) -> list[LineManifest]:
    """Build a coherently-reconciled hyphen chain a-b-…-z (PART1, BOTH…,
    PART2), every member CORRECTED."""
    lines = []
    for i, ocr in enumerate(ocr_texts):
        if i == 0:
            role = HyphenRole.PART1
        elif i == len(ocr_texts) - 1:
            role = HyphenRole.PART2
        else:
            role = HyphenRole.BOTH
        lm = _hyphen_line(f"c{i}", ocr, role=role)
        lm.corrected_text = ocr.replace("0", "o")  # a plausible correction
        lm.status = LineStatus.CORRECTED
        lines.append(lm)
    for i, lm in enumerate(lines):
        if i > 0:
            lm.hyphen_pair_line_id = lines[i - 1].line_id
        if 0 < i < len(lines) - 1:
            lm.hyphen_forward_pair_id = lines[i + 1].line_id
        elif i == 0:
            # PART1 carries its (forward) link in the plain pair fields.
            lm.hyphen_pair_line_id = lines[i + 1].line_id
    return lines


def _make_pipeline():
    from corrigenda.core.pipeline import CorrectionPipeline
    from tests._pipeline_harness import DictProvider, RecordingObserver

    return CorrectionPipeline.for_provider(
        DictProvider({}),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
    )


@pytest.mark.parametrize("flagged_index", [0, 2])
def test_f2_three_line_chain_reverts_atomically(flagged_index: int):
    """Flagging either endpoint of an a-b-c chain must revert ALL THREE
    members: pre-fix the extension was one-hop (b reverted, the far
    endpoint stayed corrected → mixed OCR+corrected pair inside the
    chain)."""
    chain = _reconciled_chain("m0t un-", "deux-", "tr0is fin")
    all_lines = {line_ref(lm): lm for lm in chain}
    pipeline = _make_pipeline()
    _apply_unit_reverts(
        reverts={line_ref(chain[flagged_index]): "adjacent_duplicate_detected"},
        all_lines=all_lines,
        traces=None,
    )
    for lm in chain:
        assert lm.corrected_text == lm.ocr_text, lm.line_id
        assert lm.status is LineStatus.FALLBACK, lm.line_id


def test_f2_four_line_chain_reverts_atomically():
    """Multi-hop: flag on the head of a-b-c-d must reach d (three hops)."""
    chain = _reconciled_chain("a0-", "b0-", "c0-", "d fin")
    all_lines = {line_ref(lm): lm for lm in chain}
    pipeline = _make_pipeline()
    _apply_unit_reverts(
        reverts={line_ref(chain[0]): "adjacent_duplicate_detected"},
        all_lines=all_lines,
        traces=None,
    )
    for lm in chain:
        assert lm.corrected_text == lm.ocr_text, lm.line_id


def test_duplicate_revert_extends_to_hyphen_partner():
    """Reverting one member of a reconciled pair used to leave a mixed
    OCR+corrected pair — the exact state reconcile_hyphen_pair forbids."""
    from corrigenda.core.pipeline import CorrectionPipeline
    from tests._pipeline_harness import DictProvider, RecordingObserver

    pipeline = CorrectionPipeline.for_provider(
        DictProvider({}),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
    )
    part1 = _line(0, "mot coupe-")
    part2 = _line(1, "suite du mot")
    part1.hyphen_role = HyphenRole.PART1
    part1.hyphen_pair_line_id = part2.line_id
    part2.hyphen_role = HyphenRole.PART2
    part2.hyphen_pair_line_id = part1.line_id
    part1.corrected_text = "mot coupé-"
    part2.corrected_text = "suite du mot"
    from corrigenda.core.identity import line_ref

    all_lines = {line_ref(lm): lm for lm in (part1, part2)}

    _apply_unit_reverts(
        reverts={line_ref(part2): "adjacent_duplicate_detected"},
        all_lines=all_lines,
        traces=None,
    )
    # Both sides reverted — no mixed pair survives.
    assert part2.corrected_text == part2.ocr_text
    assert part1.corrected_text == part1.ocr_text


def test_duplicate_revert_extends_to_CROSS_PAGE_hyphen_partner():
    """Audit P1 — a hyphen pair straddling a PAGE boundary must revert
    atomically too. The flagged member's partner lives on another page,
    absent from the page-local ``line_by_id``; the page-qualified
    ``cross_page_partners`` index is the only way to reach it. Before the
    fix the page-local ``pid in line_by_id`` guard silently skipped it,
    leaving the reconciled cross-page pair half OCR / half corrected."""
    from corrigenda.core.pipeline import CorrectionPipeline
    from tests._pipeline_harness import DictProvider, RecordingObserver

    pipeline = CorrectionPipeline.for_provider(
        DictProvider({}),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
    )
    part1 = _line(0, "mot coupe-")
    part2 = _line(1, "suite du mot")
    # PART1 on page A (last line), PART2 on page B (first line).
    part1.page_id = "pA"
    part2.page_id = "pB"
    part1.hyphen_role = HyphenRole.PART1
    part1.hyphen_pair_line_id = part2.line_id
    part1.hyphen_pair_page_id = "pB"
    part2.hyphen_role = HyphenRole.PART2
    part2.hyphen_pair_line_id = part1.line_id
    part2.hyphen_pair_page_id = "pA"
    part1.corrected_text = "mot coupé-"
    part2.corrected_text = "suite du mot"

    # The document-wide page-qualified index is the only lookup the
    # global pass holds — the cross-page partner is just another entry.
    from corrigenda.core.identity import line_ref

    all_lines = {line_ref(part1): part1, line_ref(part2): part2}

    _apply_unit_reverts(
        reverts={line_ref(part1): "adjacent_duplicate_detected"},
        all_lines=all_lines,
        traces=None,
    )
    # Both members reverted despite the partner living on another page.
    assert part1.corrected_text == part1.ocr_text
    assert part2.corrected_text == part2.ocr_text
    assert part2.status is LineStatus.FALLBACK


def test_line_mode_cap_unlinks_the_cut_pair():
    """A chain longer than the cap is truncated — but the pair straddling
    the cut must be UNLINKED so no still-linked pair spans two chunks
    (pair atomicity, CLAUDE.md)."""
    lines = [_line(i, f"mot{i}-") for i in range(12)]
    _chain(lines)
    cfg = ChunkPlannerConfig(
        max_input_chars_per_request=10_000,
        max_lines_per_request=5,
        line_window_size=3,
        line_window_overlap=1,
    )
    plan = plan_page(_page(lines), "d1", cfg, force_granularity=ChunkGranularity.LINE)
    by_id = {lm.line_id: lm for lm in lines}
    for chunk in plan.chunks:
        ids = set(chunk.line_ids)
        for lid in ids:
            lm = by_id[lid]
            for pid in (lm.hyphen_pair_line_id, lm.hyphen_forward_pair_id):
                assert pid is None or pid in ids, (
                    f"{lid} still linked to {pid} outside its chunk"
                )


def test_line_mode_cap_records_the_split_on_the_plan():
    """The over-cap cut is a recorded unit operation (ADR-010), not a
    silent pointer side effect: every severed link rides on the plan,
    and each recorded pair really is unlinked afterwards."""
    lines = [_line(i, f"mot{i}-") for i in range(12)]
    _chain(lines)
    cfg = ChunkPlannerConfig(
        max_input_chars_per_request=10_000,
        max_lines_per_request=5,
        line_window_size=3,
        line_window_overlap=1,
    )
    plan = plan_page(_page(lines), "d1", cfg, force_granularity=ChunkGranularity.LINE)
    # 12-line chain under a 5-line cap → chunks of 5+5+2, two cuts.
    assert [(s.tail_line_id, s.head_line_id) for s in plan.hyphen_splits] == [
        ("l4", "l5"),
        ("l9", "l10"),
    ]
    assert all(s.page_id == "p1" for s in plan.hyphen_splits)
    by_id = {lm.line_id: lm for lm in lines}
    for s in plan.hyphen_splits:
        tail, head = by_id[s.tail_line_id], by_id[s.head_line_id]
        assert tail.hyphen_forward_pair_id is None
        assert head.hyphen_pair_line_id != s.tail_line_id
