"""Tests for alto/hyphenation.py"""
from __future__ import annotations

import pytest

from app.alto.hyphenation import (
    enrich_chunk_lines,
    reconcile_hyphen_pair,
    should_stay_in_same_chunk,
)
from app.schemas import Coords, HyphenRole, LineManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_line(
    line_id: str,
    ocr_text: str,
    hyphen_role: HyphenRole = HyphenRole.NONE,
    hyphen_pair_line_id: str | None = None,
    hyphen_subs_content: str | None = None,
    hyphen_source_explicit: bool = False,
    prev_line_id: str | None = None,
    next_line_id: str | None = None,
) -> LineManifest:
    return LineManifest(
        line_id=line_id,
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=200, height=20),
        ocr_text=ocr_text,
        hyphen_role=hyphen_role,
        hyphen_pair_line_id=hyphen_pair_line_id,
        hyphen_subs_content=hyphen_subs_content,
        hyphen_source_explicit=hyphen_source_explicit,
        prev_line_id=prev_line_id,
        next_line_id=next_line_id,
    )


# ---------------------------------------------------------------------------
# enrich_chunk_lines
# ---------------------------------------------------------------------------

def test_enrich_part1_has_join_with_next():
    part1 = make_line(
        "TL1", "Il por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_source_explicit=True,
        next_line_id="TL2",
    )
    part2 = make_line(
        "TL2", "te ouverte",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        hyphen_source_explicit=True,
        prev_line_id="TL1",
    )
    all_lines = {"TL1": part1, "TL2": part2}
    result = enrich_chunk_lines([part1, part2], all_lines)

    inp1 = result[0]
    assert inp1.hyphen_join_with_next is True
    assert inp1.hyphen_join_with_prev is None
    assert inp1.hyphenation_role == "HypPart1"
    assert inp1.hyphen_candidate is True


def test_enrich_part2_has_join_with_prev():
    part1 = make_line(
        "TL1", "Il por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        next_line_id="TL2",
    )
    part2 = make_line(
        "TL2", "te ouverte",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        prev_line_id="TL1",
    )
    all_lines = {"TL1": part1, "TL2": part2}
    result = enrich_chunk_lines([part1, part2], all_lines)

    inp2 = result[1]
    assert inp2.hyphen_join_with_prev is True
    assert inp2.hyphen_join_with_next is None
    assert inp2.hyphenation_role == "HypPart2"
    assert inp2.hyphen_candidate is True


def test_enrich_logical_candidate_present_when_known():
    part1 = make_line(
        "TL1", "por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    all_lines = {"TL1": part1}
    result = enrich_chunk_lines([part1], all_lines)
    assert result[0].logical_join_candidate == "porte"


def test_enrich_no_hyphen_fields_on_normal_line():
    line = make_line("TL1", "Texte normal.")
    result = enrich_chunk_lines([line], {"TL1": line})
    inp = result[0]
    assert inp.hyphenation_role is None
    assert inp.hyphen_candidate is None
    assert inp.hyphen_join_with_next is None
    assert inp.hyphen_join_with_prev is None
    assert inp.logical_join_candidate is None


# ---------------------------------------------------------------------------
# reconcile_hyphen_pair
# ---------------------------------------------------------------------------

def test_reconcile_explicit_preserves_boundaries():
    """Explicit pair with known SUBS_CONTENT: boundaries stay, subs resolved."""
    part1 = make_line(
        "TL1", "Il por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    part2 = make_line(
        "TL2", "te ouverte",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        hyphen_subs_content="porte",
        hyphen_source_explicit=True,
    )
    t1, t2, subs = reconcile_hyphen_pair(part1, part2, "Il por-", "te ouverte")
    # Physical boundaries preserved
    assert t1 == "Il por-"
    assert t2 == "te ouverte"
    # SUBS_CONTENT resolved: left_bare="por" + right="te" = "porte"
    assert subs == "porte"


def test_reconcile_explicit_llm_completed_word():
    """Explicit pair: LLM removed trailing dash and fused word → PART1 falls back to OCR."""
    part1 = make_line(
        "TL1", "Rus-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_subs_content="Russie",
        hyphen_source_explicit=True,
    )
    part2 = make_line(
        "TL2", "sie le tsar.",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        hyphen_subs_content="Russie",
        hyphen_source_explicit=True,
    )
    t1, t2, subs = reconcile_hyphen_pair(part1, part2, "Russie", "sie le tsar.")
    assert t1 == "Rus-", "PART1 must fall back to OCR source when LLM fuses the word"
    assert t2 == "sie le tsar.", "PART2 correction is valid, keep it"
    assert subs == "Russie", "SUBS_CONTENT should be preserved from source"


def test_reconcile_heuristic_conservative():
    """Heuristic pair: subs_content must be None, corrected texts returned as-is."""
    part1 = make_line(
        "TL1", "boule-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_source_explicit=False,
    )
    part2 = make_line(
        "TL2", "vard du roi",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        hyphen_source_explicit=False,
    )
    t1, t2, subs = reconcile_hyphen_pair(
        part1, part2, "boule-", "vard du roi"
    )
    assert t1 == "boule-"
    assert t2 == "vard du roi"
    assert subs is None


def test_reconcile_ambiguous_returns_source():
    """When LLM join doesn't match expected subs_content, fall back to source."""
    part1 = make_line(
        "TL1", "tra-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="travail",
        hyphen_source_explicit=True,
    )
    part2 = make_line(
        "TL2", "vauxxx",   # garbled — "tra" + "vauxxx" != "travail"
        hyphen_role=HyphenRole.PART2,
        hyphen_subs_content="travail",
        hyphen_source_explicit=True,
    )
    t1, t2, subs = reconcile_hyphen_pair(part1, part2, "tra-", "vauxxx")
    # subs is None because join is wrong
    assert subs is None
    # But corrected texts are still returned (boundaries intact)
    assert t1 == "tra-"
    assert t2 == "vauxxx"


def test_reconcile_heuristic_llm_completed_word():
    """Heuristic: LLM removed trailing dash and fused word → PART1 falls back to OCR."""
    part1 = make_line(
        "TL1", "Rus-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_source_explicit=False,
    )
    part2 = make_line(
        "TL2", "sie le tsar.",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        hyphen_source_explicit=False,
    )
    t1, t2, subs = reconcile_hyphen_pair(part1, part2, "Russie", "sie le tsar.")
    assert t1 == "Rus-", "PART1 must fall back to OCR source"
    assert t2 == "sie le tsar.", "PART2 correction is valid, keep it"
    assert subs is None


def test_reconcile_heuristic_llm_completed_word_part2_also_bad():
    """Heuristic: LLM fused word AND PART2 correction is empty → both fall back."""
    part1 = make_line(
        "TL1", "Rus-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_source_explicit=False,
    )
    part2 = make_line(
        "TL2", "sie le tsar.",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        hyphen_source_explicit=False,
    )
    t1, t2, subs = reconcile_hyphen_pair(part1, part2, "Russie", "")
    assert t1 == "Rus-", "PART1 must fall back to OCR source"
    assert t2 == "sie le tsar.", "PART2 empty → fall back to OCR source"
    assert subs is None


def test_reconcile_heuristic_tiret_preserved():
    """Heuristic: LLM kept the trailing dash → corrections accepted as-is."""
    part1 = make_line(
        "TL1", "Rus-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
        hyphen_source_explicit=False,
    )
    part2 = make_line(
        "TL2", "sie le tsar.",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
        hyphen_source_explicit=False,
    )
    t1, t2, subs = reconcile_hyphen_pair(part1, part2, "Rus-", "sie le tsar.")
    assert t1 == "Rus-", "LLM respected the dash, keep correction"
    assert t2 == "sie le tsar."
    assert subs is None


def test_reconcile_no_line_fusion():
    """Result must always be two distinct non-empty strings."""
    part1 = make_line(
        "TL1", "con-",
        hyphen_role=HyphenRole.PART1,
        hyphen_subs_content="construction",
        hyphen_source_explicit=True,
    )
    part2 = make_line(
        "TL2", "struction solide",
        hyphen_role=HyphenRole.PART2,
        hyphen_subs_content="construction",
        hyphen_source_explicit=True,
    )
    t1, t2, subs = reconcile_hyphen_pair(
        part1, part2, "con-", "struction solide"
    )
    # Both lines must remain non-empty and distinct
    assert t1 and t2
    assert t1 != t2
    # No text from part2 leaked into t1
    assert "struction" not in t1
    # No text from part1 leaked into t2
    assert "con-" not in t2


# ---------------------------------------------------------------------------
# should_stay_in_same_chunk
# ---------------------------------------------------------------------------

def test_should_stay_linked_pair():
    part1 = make_line(
        "TL1", "por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL2",
    )
    part2 = make_line(
        "TL2", "te",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
    )
    assert should_stay_in_same_chunk(part1, part2) is True
    # Symmetric
    assert should_stay_in_same_chunk(part2, part1) is True


def test_should_stay_unrelated_lines():
    line_a = make_line("TL1", "Bonjour monde.")
    line_b = make_line("TL2", "Autre ligne.")
    assert should_stay_in_same_chunk(line_a, line_b) is False


def test_should_stay_part1_wrong_pair_id():
    """PART1 pointing to a different line must not match."""
    part1 = make_line(
        "TL1", "por-",
        hyphen_role=HyphenRole.PART1,
        hyphen_pair_line_id="TL99",  # points elsewhere
    )
    part2 = make_line(
        "TL2", "te",
        hyphen_role=HyphenRole.PART2,
        hyphen_pair_line_id="TL1",
    )
    assert should_stay_in_same_chunk(part1, part2) is False
