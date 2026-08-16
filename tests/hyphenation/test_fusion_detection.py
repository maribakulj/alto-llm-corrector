"""The producer must not have merged the two lines into one.

The validator refuses a response where PART1 comes back carrying the whole
logical word: that is the producer having performed the merge the library
forbids. It is checked over the chunk's TARGET set only — a pair sitting
entirely in the context region belongs to an adjacent chunk, and failing
this chunk for it would spend a retry on someone else's lines.
"""

from __future__ import annotations

import pytest

from saknussemm.core.validator import (
    HyphenIntegrityError,
    _validate_hyphen_integrity,
)


def test_fusion_check_skips_context_only_pair():
    # A full hyphen pair sits entirely in the chunk's CONTEXT region (neither
    # member is a target). Even if the LLM fuses PART1 (its last word ==
    # subs_content), the target chunk must NOT be failed.
    hyphen_pairs = {"ctxP1": "ctxP2", "ctxP2": "ctxP1"}
    text_by_id = {
        "ctxP1": "necessaires",  # fused: contains the full logical word
        "ctxP2": "du roi",
        "tgt": "corrected target",
    }
    ocr_texts = {"ctxP1": "neces-", "ctxP2": "saires", "tgt": "target"}
    hyphen_subs = {"ctxP1": "necessaires"}
    chunk_ids = {"tgt"}  # only the target line is in scope

    # Must NOT raise — the context-only fusion is not this chunk's concern.
    _validate_hyphen_integrity(
        text_by_id,
        hyphen_pairs,
        chunk_ids,
        ocr_texts,
        hyphen_subs,
    )


def test_fusion_check_still_fires_for_a_target_pair():
    hyphen_pairs = {"P1": "P2", "P2": "P1"}
    text_by_id = {"P1": "necessaires", "P2": "du roi"}
    ocr_texts = {"P1": "neces-", "P2": "saires"}
    hyphen_subs = {"P1": "necessaires"}
    chunk_ids = {"P1", "P2"}
    with pytest.raises(HyphenIntegrityError):
        _validate_hyphen_integrity(
            text_by_id, hyphen_pairs, chunk_ids, ocr_texts, hyphen_subs
        )
