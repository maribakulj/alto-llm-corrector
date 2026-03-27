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

    hyphen_pairs maps PART1 → PART2 and PART2 → PART1 (both directions).
    We deduplicate via frozenset and check each pair once.
    """
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

        # Either side being empty means illegal fusion/deletion
        if not text_a:
            raise ValueError(
                f"hyphen_integrity_violation: corrected_text for line "
                f"{id_a!r} is empty"
            )
        if not text_b:
            raise ValueError(
                f"hyphen_integrity_violation: corrected_text for line "
                f"{id_b!r} is empty"
            )


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
