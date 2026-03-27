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


def _part1_text_migrated(ocr_text: str, corrected_text: str) -> bool:
    """
    Return True if corrected PART1 text looks like the LLM extended the
    hyphenated word or pulled text from the next line.
    """
    ocr_bare = ocr_text.rstrip("-").rstrip()
    corrected_bare = corrected_text.rstrip("-").rstrip(".")

    ocr_words = ocr_bare.split()
    corrected_words = corrected_bare.split()

    # Word count increased significantly → text was pulled from next line
    if len(corrected_words) > len(ocr_words) + 1:
        return True

    # Same or similar word count, but last word got much longer
    # (word completion, e.g. "néces" → "nécessaires")
    if ocr_words and corrected_words:
        ocr_last = ocr_words[-1].rstrip("-")
        corrected_last = corrected_words[-1].rstrip("-")
        if len(corrected_last) > len(ocr_last) + 3:
            return True

    # Overall character length grew substantially
    if len(corrected_bare) > len(ocr_bare) * 1.4 + 8:
        return True

    return False


def _part2_text_migrated(ocr_text: str, corrected_text: str) -> bool:
    """
    Return True if corrected PART2 text is drastically different from
    original, indicating cascade propagation from a shifted PART1.
    """
    ocr_words = ocr_text.split()
    corrected_words = corrected_text.split()

    # Dramatic shrinkage → content was absorbed by previous line
    if ocr_words and len(corrected_words) < len(ocr_words) * 0.4:
        return True

    # Dramatic growth → text pulled from next line
    if len(corrected_words) > len(ocr_words) + max(3, int(len(ocr_words) * 0.4)):
        return True

    return False


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
    # --- Shared guard: detect word extension / text migration on PART1 ---
    # The LLM may complete the hyphenated word on PART1 (e.g. "néces-" →
    # "nécessaires-") or pull text from PART2 onto PART1.  We detect this
    # by comparing word counts and character lengths.
    _fell_back = False
    if _part1_text_migrated(part1.ocr_text, corrected_part1):
        safe_part2 = (
            corrected_part2
            if corrected_part2 and "\n" not in corrected_part2
            else part2.ocr_text
        )
        subs = part1.hyphen_subs_content if part1.hyphen_source_explicit else None
        corrected_part1 = part1.ocr_text
        corrected_part2 = safe_part2
        _fell_back = True
        # Early return: boundaries are restored, preserve SUBS_CONTENT
        return corrected_part1, corrected_part2, subs

    # Also guard PART2: if corrected PART2 is drastically different from
    # original (cascade propagation), fall it back to OCR source.
    if _part2_text_migrated(part2.ocr_text, corrected_part2):
        corrected_part2 = part2.ocr_text

    # --- Heuristic mode: conservative, no SUBS_CONTENT reconstruction ---
    if not part1.hyphen_source_explicit:
        return corrected_part1, corrected_part2, None

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
