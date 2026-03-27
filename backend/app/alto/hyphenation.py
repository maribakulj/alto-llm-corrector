from __future__ import annotations

from typing import Optional

from app.schemas import HyphenRole, LLMLineInput, LineManifest


def enrich_chunk_lines(
    line_manifests: list[LineManifest],
    all_lines_by_id: dict[str, LineManifest],
) -> list[LLMLineInput]:
    """
    Build LLMLineInput list from a chunk's LineManifests.

    For each line:
    - prev_text / next_text come from all_lines_by_id lookups.
    - Hyphenation fields are populated only when hyphen_role != NONE.
    """
    result: list[LLMLineInput] = []

    for lm in line_manifests:
        prev_text: Optional[str] = None
        next_text: Optional[str] = None

        if lm.prev_line_id and lm.prev_line_id in all_lines_by_id:
            prev_text = all_lines_by_id[lm.prev_line_id].ocr_text
        if lm.next_line_id and lm.next_line_id in all_lines_by_id:
            next_text = all_lines_by_id[lm.next_line_id].ocr_text

        if lm.hyphen_role == HyphenRole.NONE:
            result.append(
                LLMLineInput(
                    line_id=lm.line_id,
                    prev_text=prev_text,
                    ocr_text=lm.ocr_text,
                    next_text=next_text,
                )
            )
        else:
            result.append(
                LLMLineInput(
                    line_id=lm.line_id,
                    prev_text=prev_text,
                    ocr_text=lm.ocr_text,
                    next_text=next_text,
                    hyphenation_role=lm.hyphen_role.value,
                    hyphen_candidate=True,
                    hyphen_join_with_next=(
                        True if lm.hyphen_role == HyphenRole.PART1 else None
                    ),
                    hyphen_join_with_prev=(
                        True if lm.hyphen_role == HyphenRole.PART2 else None
                    ),
                    logical_join_candidate=lm.hyphen_subs_content or None,
                )
            )

    return result


def reconcile_hyphen_pair(
    part1: LineManifest,
    part2: LineManifest,
    corrected_part1: str,
    corrected_part2: str,
) -> tuple[str, str, Optional[str]]:
    """
    Validate and reconcile LLM corrections for a hyphenated pair.

    Returns (final_text_part1, final_text_part2, resolved_subs_content).

    Guarantees:
    - The two physical lines remain distinct.
    - No text migrates from one line to the other.
    - On ambiguity, fall back to OCR source texts.
    """
    # --- Heuristic mode: conservative, no SUBS_CONTENT reconstruction ---
    if not part1.hyphen_source_explicit:
        # If PART1 OCR ended with "-" AND the LLM removed the hyphen AND
        # extended the text (i.e. completed the hyphenated word), fall back
        # PART1 to the OCR source.  The "longer than bare OCR" condition
        # distinguishes word-completion ("néces-" → "nécessaires") from a
        # legitimate stray-hyphen cleanup ("néces-" → "néces"), which should
        # be allowed through.
        ocr_bare = part1.ocr_text.rstrip("-")
        if (
            part1.ocr_text.endswith("-")
            and not corrected_part1.endswith("-")
            and len(corrected_part1) > len(ocr_bare)
        ):
            safe_part2 = (
                corrected_part2
                if corrected_part2 and "\n" not in corrected_part2
                else part2.ocr_text
            )
            return part1.ocr_text, safe_part2, None
        return corrected_part1, corrected_part2, None

    # --- Explicit mode ---
    # Guard: if the LLM removed the trailing dash AND completed the word
    # (corrected text is longer than the bare OCR fragment), fall back PART1
    # to OCR source to preserve physical line boundaries.
    ocr_bare = part1.ocr_text.rstrip("-")
    if (
        part1.ocr_text.endswith("-")
        and not corrected_part1.endswith("-")
        and len(corrected_part1) > len(ocr_bare)
    ):
        safe_part2 = (
            corrected_part2
            if corrected_part2 and "\n" not in corrected_part2
            else part2.ocr_text
        )
        return part1.ocr_text, safe_part2, part1.hyphen_subs_content

    # Extract boundary tokens
    tokens1 = corrected_part1.split()
    tokens2 = corrected_part2.split()

    if not tokens1 or not tokens2:
        # Empty corrected text on either side — fall back to source
        return part1.ocr_text, part2.ocr_text, None

    left_fragment = tokens1[-1]   # last token of part1 (possibly ends with "-")
    right_fragment = tokens2[0]   # first token of part2

    # Strip trailing hyphen from left fragment for join
    left_bare = left_fragment.rstrip("-")

    resolved_subs: Optional[str] = None

    if part1.hyphen_subs_content:
        expected = part1.hyphen_subs_content
        joined = left_bare + right_fragment
        # Accept if the join matches the expected logical word (case-insensitive)
        if joined.lower() == expected.lower():
            resolved_subs = expected
        else:
            # Mismatch — uncertain, keep boundaries but no SUBS_CONTENT
            resolved_subs = None
    else:
        # No reference word: just accept the corrected texts as-is,
        # physical boundaries are preserved by returning them unchanged.
        resolved_subs = None

    return corrected_part1, corrected_part2, resolved_subs


def should_stay_in_same_chunk(
    line_a: LineManifest,
    line_b: LineManifest,
) -> bool:
    """
    Return True if line_a and line_b must be in the same LLM chunk
    because they form a hyphenated pair.
    """
    return (
        line_a.hyphen_role == HyphenRole.PART1
        and line_a.hyphen_pair_line_id == line_b.line_id
    ) or (
        line_b.hyphen_role == HyphenRole.PART1
        and line_b.hyphen_pair_line_id == line_a.line_id
    )
