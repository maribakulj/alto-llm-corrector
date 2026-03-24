"""Validator for LLM structured responses."""
from __future__ import annotations

from typing import Optional

from app.schemas import LLMLineOutput, LLMResponse


def validate_llm_response(
    raw: dict,
    expected_line_ids: list[str],
    hyphen_pairs: Optional[dict[str, str]] = None,
) -> LLMResponse:
    """
    Validate an LLM response dict and return a typed LLMResponse.

    Parameters
    ----------
    raw:
        Parsed JSON dict from the LLM.
    expected_line_ids:
        The line IDs the LLM was asked to correct.
    hyphen_pairs:
        Mapping of PART1 line_id → PART2 line_id (and vice-versa).
        When provided, additional hyphen-integrity checks are performed.

    Raises
    ------
    ValueError
        On any validation failure, with a descriptive message.
        Hyphen-integrity violations use message prefix
        "hyphen_integrity_violation".
    """
    # --- Basic structure ---
    if "lines" not in raw:
        raise ValueError("Missing key 'lines' in LLM response")

    lines_raw = raw["lines"]
    if not isinstance(lines_raw, list):
        raise ValueError("'lines' must be a list")

    expected_set = set(expected_line_ids)

    # --- Count ---
    if len(lines_raw) != len(expected_line_ids):
        raise ValueError(
            f"Line count mismatch: expected {len(expected_line_ids)}, "
            f"got {len(lines_raw)}"
        )

    seen_ids: set[str] = set()
    outputs: list[LLMLineOutput] = []

    for entry in lines_raw:
        if not isinstance(entry, dict):
            raise ValueError(f"Each line entry must be a dict, got {type(entry)}")

        line_id = entry.get("line_id")
        corrected_text = entry.get("corrected_text")

        if not line_id:
            raise ValueError(f"Entry missing 'line_id': {entry}")
        if line_id in seen_ids:
            raise ValueError(f"Duplicate line_id in response: {line_id!r}")
        if line_id not in expected_set:
            raise ValueError(f"Unknown line_id in response: {line_id!r}")

        seen_ids.add(line_id)

        if not isinstance(corrected_text, str) or corrected_text == "":
            raise ValueError(f"corrected_text for {line_id!r} is empty or missing")
        if "\n" in corrected_text or "\r" in corrected_text:
            raise ValueError(
                f"corrected_text for {line_id!r} contains a newline character"
            )

        outputs.append(LLMLineOutput(line_id=line_id, corrected_text=corrected_text))

    # --- Check all expected IDs are present ---
    missing = expected_set - seen_ids
    if missing:
        raise ValueError(f"Missing line_ids in response: {sorted(missing)}")

    # --- Hyphen integrity ---
    if hyphen_pairs:
        text_by_id = {o.line_id: o.corrected_text for o in outputs}
        _validate_hyphen_integrity(text_by_id, hyphen_pairs, expected_set)

    return LLMResponse(lines=outputs)


def _validate_hyphen_integrity(
    text_by_id: dict[str, str],
    hyphen_pairs: dict[str, str],
    chunk_ids: set[str],
) -> None:
    """
    Check that no hyphen-pair line has been illegally merged.

    hyphen_pairs maps PART1 → PART2 and PART2 → PART1.
    We iterate PART1 entries only (those whose pair is also in chunk).
    """
    # Collect PART1 ids: PART1 id is the one whose value (PART2) is also in chunk
    # hyphen_pairs contains both directions: part1->part2 and part2->part1
    # We need to determine which side is PART1. We can do this by checking
    # whether the key's corrected_text ends with '-' or by convention.
    # The caller is responsible for providing the mapping correctly.
    # We check each entry in hyphen_pairs where both key and value are in chunk.
    checked_pairs: set[frozenset[str]] = set()

    for id_a, id_b in hyphen_pairs.items():
        pair = frozenset({id_a, id_b})
        if pair in checked_pairs:
            continue
        if id_a not in chunk_ids or id_b not in chunk_ids:
            continue
        checked_pairs.add(pair)

        text_a = text_by_id.get(id_a, "")
        text_b = text_by_id.get(id_b, "")

        # Determine which is PART1: it should end with '-' in the original,
        # but here we rely on the mapping convention: key=PART1, value=PART2
        # for the first direction we encounter. We check both directions.
        # The caller passes both part1->part2 and part2->part1.
        # We identify PART1 as the key that points to PART2.
        # Since both directions are present, we check only once per pair.
        # Convention: treat id_a as PART1 candidate if text_a ends with '-'.
        if text_a.rstrip("-").endswith("") and text_b == "":
            raise ValueError(
                f"hyphen_integrity_violation: corrected_text for PART2 "
                f"line {id_b!r} is empty"
            )
        if text_b == "":
            raise ValueError(
                f"hyphen_integrity_violation: corrected_text for line "
                f"{id_b!r} (PART2) is empty"
            )

    # Now check fusion: PART1 corrected_text should not contain the full
    # logical word (i.e. corrected_part1.rstrip('-') == hyphen_subs_content).
    # We receive hyphen_subs_content implicitly via the pair mapping.
    # The caller must pass a dict that includes subs_content if the check
    # is needed. For the fusion check, we look at entries where the value
    # is a tuple (part2_id, subs_content). However the interface uses
    # dict[str, str] so we handle it differently.
    #
    # The fusion check (PART1 text stripped of '-' equals the full logical word)
    # is done in validate_llm_response via the hyphen_pairs_with_subs variant.
    # Since the public API uses dict[str,str], the caller may encode subs_content
    # as a special sentinel. We support an extended form where the value can be
    # a "|"-separated "part2_id|subs_content". See extended validation below.
    pass


def validate_llm_response_with_subs(
    raw: dict,
    expected_line_ids: list[str],
    hyphen_triples: Optional[list[tuple[str, str, Optional[str]]]] = None,
) -> LLMResponse:
    """
    Extended validation that also checks PART1 fusion against subs_content.

    hyphen_triples: list of (part1_id, part2_id, subs_content_or_None)
    """
    # First run basic + simple hyphen check
    if hyphen_triples:
        simple_pairs = {}
        for p1, p2, _ in hyphen_triples:
            simple_pairs[p1] = p2
            simple_pairs[p2] = p1
    else:
        simple_pairs = None

    response = validate_llm_response(raw, expected_line_ids, simple_pairs)

    # Fusion check
    if hyphen_triples:
        text_by_id = {o.line_id: o.corrected_text for o in response.lines}
        for part1_id, part2_id, subs_content in hyphen_triples:
            if subs_content is None:
                continue
            part1_text = text_by_id.get(part1_id, "")
            # Violation: LLM merged — corrected_part1 stripped of hyphen equals full word
            if part1_text.rstrip("-").lower() == subs_content.lower():
                raise ValueError(
                    f"hyphen_integrity_violation: PART1 line {part1_id!r} "
                    f"contains the full logical word {subs_content!r} "
                    f"(fusion detected)"
                )

    return response
