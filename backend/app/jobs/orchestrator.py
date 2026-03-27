"""Main correction orchestrator."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

from app.alto.hyphenation import enrich_chunk_lines, reconcile_hyphen_pair
from app.alto.rewriter import rewrite_alto_file
from app.jobs.chunk_planner import downgrade_granularity, plan_page
from app.jobs.store import job_store
from app.jobs.validator import validate_llm_response
from app.providers.base import OUTPUT_JSON_SCHEMA, SYSTEM_PROMPT, BaseProvider
from app.schemas import (
    ChunkGranularity,
    ChunkPlannerConfig,
    ChunkRequest,
    DocumentManifest,
    HyphenRole,
    JobStatus,
    LineManifest,
    LineStatus,
    LLMUserPayload,
    PageManifest,
)

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = ChunkPlannerConfig()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_hyphen_pairs(
    lines: list[LineManifest],
) -> dict[str, str]:
    """Return PART1→PART2 and PART2→PART1 mapping for lines in the chunk."""
    pairs: dict[str, str] = {}
    for lm in lines:
        if lm.hyphen_role == HyphenRole.PART1 and lm.hyphen_pair_line_id:
            pairs[lm.line_id] = lm.hyphen_pair_line_id
            pairs[lm.hyphen_pair_line_id] = lm.line_id
    return pairs


def _line_drift_too_large(ocr_text: str, corrected_text: str) -> bool:
    """
    Return True if corrected text deviates too far from the OCR source,
    indicating the LLM shifted content between lines.
    """
    ocr_words = ocr_text.split()
    corrected_words = corrected_text.split()
    ocr_wc = len(ocr_words)
    corrected_wc = len(corrected_words)

    # Word-count tolerance: allow generous margin for OCR fixes
    tolerance = max(3, int(ocr_wc * 0.4))
    if abs(corrected_wc - ocr_wc) > tolerance:
        return True

    # Character-length ratio check
    ocr_len = len(ocr_text)
    corrected_len = len(corrected_text)
    if ocr_len > 0:
        ratio = corrected_len / ocr_len
        if ratio > 2.0 or ratio < 0.25:
            return True

    return False


def _count_hyphen_pairs_in_chunk(lines: list[LineManifest]) -> int:
    return sum(
        1 for lm in lines
        if lm.hyphen_role == HyphenRole.PART1 and lm.hyphen_pair_line_id
    )


# ---------------------------------------------------------------------------
# Chunk execution
# ---------------------------------------------------------------------------

async def _run_chunk(
    job_id: str,
    chunk: ChunkRequest,
    line_by_id: dict[str, LineManifest],
    provider: BaseProvider,
    api_key: str,
    model: str,
    provider_name: str,
) -> int:
    """
    Process one chunk through the LLM pipeline.

    Returns the number of hyphen pairs reconciled in this chunk.
    """
    chunk_lines = [line_by_id[lid] for lid in chunk.line_ids if lid in line_by_id]
    if not chunk_lines:
        return 0

    hyphen_pairs = _build_hyphen_pairs(chunk_lines)
    all_lines_by_id = line_by_id

    job_store.emit(job_id, "chunk_started", {
        "chunk_id": chunk.chunk_id,
        "granularity": chunk.granularity.value,
        "line_count": len(chunk_lines),
    })

    # --- Retry loop ---
    max_attempts = 3
    hyphen_violation = False

    for attempt in range(1, max_attempts + 1):
        temperature = 0.0 if (attempt > 1 or hyphen_violation) else 0.0

        enriched = enrich_chunk_lines(chunk_lines, all_lines_by_id)
        payload = LLMUserPayload(
            granularity=chunk.granularity,
            document_id=chunk.document_id,
            page_id=chunk.page_id,
            block_id=chunk.block_id,
            lines=enriched,
        )
        user_dict = payload.model_dump(exclude_none=True)

        try:
            raw = await provider.complete_structured(
                api_key=api_key,
                model=model,
                system_prompt=SYSTEM_PROMPT,
                user_payload=user_dict,
                json_schema=OUTPUT_JSON_SCHEMA,
                temperature=temperature,
            )

            response = validate_llm_response(
                raw,
                [lm.line_id for lm in chunk_lines],
                hyphen_pairs if hyphen_pairs else None,
            )
            hyphen_violation = False

        except ValueError as exc:
            msg = str(exc)
            is_hyphen_violation = "hyphen_integrity_violation" in msg

            if is_hyphen_violation and not hyphen_violation:
                # First hyphen violation: retry immediately with temperature=0
                hyphen_violation = True
                job_store.emit(job_id, "retry", {
                    "chunk_id": chunk.chunk_id,
                    "attempt": attempt,
                    "reason": "hyphen_integrity_violation",
                })
                job_store.update_job(job_id,
                    retries=getattr(job_store.get_job(job_id), "retries", 0) + 1)
                continue

            # General failure
            if attempt < max_attempts:
                await asyncio.sleep(attempt)
                job_store.emit(job_id, "retry", {
                    "chunk_id": chunk.chunk_id,
                    "attempt": attempt,
                    "reason": msg[:120],
                })
                job_store.update_job(job_id,
                    retries=getattr(job_store.get_job(job_id), "retries", 0) + 1)
                continue

            # All attempts exhausted → fallback
            logger.warning("Chunk %s: all attempts failed, falling back to OCR source", chunk.chunk_id)
            job_store.emit(job_id, "warning", {
                "chunk_id": chunk.chunk_id,
                "message": f"Fallback to OCR source: {msg[:120]}",
            })
            for lm in chunk_lines:
                lm.corrected_text = lm.ocr_text
                lm.status = LineStatus.FALLBACK
            job_store.update_job(job_id,
                fallbacks=getattr(job_store.get_job(job_id), "fallbacks", 0) + 1)
            return 0

        # --- Success: apply corrections ---
        text_by_id: dict[str, str] = {o.line_id: o.corrected_text for o in response.lines}

        # Reconcile hyphen pairs
        reconciled_count = 0
        processed_part2: set[str] = set()

        for lm in chunk_lines:
            if lm.hyphen_role == HyphenRole.PART1 and lm.hyphen_pair_line_id:
                part2_id = lm.hyphen_pair_line_id
                if part2_id in processed_part2:
                    continue
                part2 = line_by_id.get(part2_id)
                if part2 is None:
                    continue

                corrected_p1 = text_by_id.get(lm.line_id, lm.ocr_text)
                corrected_p2 = text_by_id.get(part2_id, part2.ocr_text)

                final_p1, final_p2, subs = reconcile_hyphen_pair(
                    lm, part2, corrected_p1, corrected_p2
                )

                lm.corrected_text = final_p1
                lm.status = LineStatus.CORRECTED
                lm.hyphen_subs_content = subs or lm.hyphen_subs_content

                part2.corrected_text = final_p2
                part2.status = LineStatus.CORRECTED
                part2.hyphen_subs_content = subs or part2.hyphen_subs_content

                processed_part2.add(part2_id)
                reconciled_count += 1

        # Apply remaining lines (with drift guard)
        for lm in chunk_lines:
            if lm.corrected_text is None:
                corrected = text_by_id.get(lm.line_id)
                if corrected is not None:
                    if _line_drift_too_large(lm.ocr_text, corrected):
                        lm.corrected_text = lm.ocr_text
                        lm.status = LineStatus.FALLBACK
                    else:
                        lm.corrected_text = corrected
                        lm.status = LineStatus.CORRECTED

        job_store.emit(job_id, "chunk_completed", {
            "chunk_id": chunk.chunk_id,
            "hyphen_pairs_reconciled": reconciled_count,
        })
        return reconciled_count

    # Should not reach here
    return 0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_job(
    job_id: str,
    document_manifest: DocumentManifest,
    provider_name: str,
    api_key: str,
    model: str,
    output_dir: Path,
    source_files: dict[str, Path],
    provider: Optional[BaseProvider] = None,
) -> None:
    """
    Run the full correction pipeline for a job.

    source_files: mapping of source_name → xml_path on disk.
    provider: injected provider (for testing); if None, resolved from registry.
    """
    if provider is None:
        from app.providers import get_provider
        from app.schemas import Provider
        provider = get_provider(Provider(provider_name))

    start_time = time.monotonic()

    try:
        job_store.update_job(job_id, status=JobStatus.STARTED)
        job_store.emit(job_id, "started", {"job_id": job_id})

        # Count total hyphen pairs in document
        total_hyphen_pairs = sum(
            sum(1 for lm in page.lines if lm.hyphen_role == HyphenRole.PART1)
            for page in document_manifest.pages
        )

        job_store.emit(job_id, "document_parsed", {
            "total_pages": document_manifest.total_pages,
            "total_lines": document_manifest.total_lines,
            "hyphen_pairs": total_hyphen_pairs,
        })

        job_store.update_job(
            job_id,
            status=JobStatus.RUNNING,
            document_manifest=document_manifest,
            total_lines=document_manifest.total_lines,
        )

        total_chunks = 0
        total_reconciled = 0
        config = _DEFAULT_CONFIG

        for page in document_manifest.pages:
            # Build a page-local line lookup to prevent ID collisions across pages.
            # Multiple ALTO files often reuse the same TextLine IDs (e.g. "l0001").
            # A global dict would let page N's lines overwrite page M's, causing
            # corrections to be applied to the wrong LineManifest objects.
            # prev_line_id / next_line_id are always within-page (set by parser),
            # so a page-local dict is fully sufficient for context enrichment too.
            line_by_id: dict[str, LineManifest] = {lm.line_id: lm for lm in page.lines}
            page_hyphen_pairs = sum(
                1 for lm in page.lines if lm.hyphen_role == HyphenRole.PART1
            )
            job_store.emit(job_id, "page_started", {
                "page_id": page.page_id,
                "page_index": page.page_index,
                "line_count": len(page.lines),
                "hyphen_pair_count": page_hyphen_pairs,
            })

            # Plan with granularity downgrade fallback
            granularity: Optional[ChunkGranularity] = None
            plan = plan_page(page, document_manifest.document_id, config, granularity)

            job_store.emit(job_id, "chunk_planned", {
                "page_id": page.page_id,
                "chunk_count": len(plan.chunks),
                "granularity": plan.granularity.value,
            })

            page_reconciled = 0
            chunk_failures = 0

            for chunk in plan.chunks:
                total_chunks += 1
                try:
                    n = await _run_chunk(
                        job_id, chunk, line_by_id,
                        provider, api_key, model, provider_name,
                    )
                    page_reconciled += n
                except Exception as exc:
                    logger.exception("Chunk %s raised unexpectedly", chunk.chunk_id)
                    chunk_failures += 1
                    job_store.emit(job_id, "warning", {
                        "chunk_id": chunk.chunk_id,
                        "message": str(exc)[:200],
                    })

            total_reconciled += page_reconciled
            page.status = JobStatus.COMPLETED

            page_corrections = sum(
                1 for lm in page.lines
                if lm.corrected_text is not None and lm.corrected_text != lm.ocr_text
            )
            job_store.emit(job_id, "page_completed", {
                "page_id": page.page_id,
                "page_index": page.page_index,
                "corrections": page_corrections,
                "hyphen_pairs_reconciled": page_reconciled,
            })

        # Rewrite output files
        for source_name, xml_path in source_files.items():
            pages_for_file = [
                p for p in document_manifest.pages
                if p.source_file == source_name
            ]
            if not pages_for_file:
                continue

            xml_bytes = rewrite_alto_file(xml_path, pages_for_file, provider_name, model)
            stem = xml_path.stem
            out_path = output_dir / f"{stem}_corrected.xml"
            out_path.write_bytes(xml_bytes)

        lines_modified = sum(
            1 for page in document_manifest.pages
            for lm in page.lines
            if lm.corrected_text is not None and lm.corrected_text != lm.ocr_text
        )
        elapsed = round(time.monotonic() - start_time, 2)

        job_store.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            chunks_total=total_chunks,
            lines_modified=lines_modified,
            duration_seconds=elapsed,
        )

        job_store.emit(job_id, "completed", {
            "job_id": job_id,
            "total_lines": document_manifest.total_lines,
            "lines_modified": lines_modified,
            "hyphen_pairs_total": total_reconciled,
            "chunks_total": total_chunks,
            "duration_seconds": elapsed,
        })

    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error=str(exc)[:500],
            duration_seconds=time.monotonic() - start_time,
        )
        job_store.emit(job_id, "failed", {
            "job_id": job_id,
            "error": str(exc)[:500],
        })
