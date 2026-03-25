"""Jobs API router."""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path
from typing import AsyncGenerator, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.alto.parser import build_document_manifest
from app.jobs.orchestrator import run_job
from app.jobs.store import job_store
from app.schemas import (
    CreateJobResponse,
    HyphenRole,
    JobStatus,
    JobStatusResponse,
    Provider,
)
from app.storage import (
    get_output_files,
    images_dir,
    init_job_dirs,
    link_alto_to_images,
    output_dir,
    save_uploaded_files,
)

router = APIRouter()

_ALLOWED_UPLOAD_EXTENSIONS = {".xml", ".alto", ".zip"}


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------

@router.post("", response_model=CreateJobResponse)
async def create_job(
    files: List[UploadFile] = File(...),
    provider: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
) -> CreateJobResponse:
    """Upload ALTO files and start a correction job."""
    # Validate upload extensions
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {f.filename!r}. "
                       f"Allowed: {sorted(_ALLOWED_UPLOAD_EXTENSIONS)}",
            )

    # Validate provider
    try:
        provider_enum = Provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider!r}")

    # Read all file bytes
    file_tuples: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        file_tuples.append((f.filename or "upload.xml", content))

    # Create job and dirs
    job_id = job_store.create_job(provider_enum, model)
    init_job_dirs(job_id)

    # Save and extract files (also extracts images from ZIPs)
    saved, image_files = save_uploaded_files(job_id, file_tuples)

    if not saved:
        raise HTTPException(
            status_code=400,
            detail="No ALTO/XML files found after extraction.",
        )

    # Build document manifest
    file_pairs = [(path, name) for name, path in saved.items()]
    try:
        doc_manifest = build_document_manifest(file_pairs)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse files: {exc}")

    if doc_manifest.total_lines == 0:
        raise HTTPException(
            status_code=400,
            detail="No text lines found in the uploaded ALTO files.",
        )

    pages_info = [(p.page_id, p.source_file) for p in doc_manifest.pages]
    images_map = link_alto_to_images(pages_info, saved, image_files)
    job_store.update_job(job_id, document_manifest=doc_manifest, images=images_map)

    # Resolve provider instance
    from app.providers import get_provider as _get_provider
    provider_instance = _get_provider(provider_enum)

    out_dir = output_dir(job_id)

    # Launch correction in background
    asyncio.create_task(
        run_job(
            job_id=job_id,
            document_manifest=doc_manifest,
            provider_name=provider,
            api_key=api_key,
            model=model,
            output_dir=out_dir,
            source_files={name: path for name, path in saved.items()},
            provider=provider_instance,
        )
    )

    return CreateJobResponse(job_id=job_id)


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}
# ---------------------------------------------------------------------------

@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    """Poll the status of a correction job."""
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        total_lines=job.total_lines,
        lines_modified=job.lines_modified,
        chunks_total=job.chunks_total,
        retries=job.retries,
        fallbacks=job.fallbacks,
        duration_seconds=job.duration_seconds,
        error=job.error,
    )


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/events
# ---------------------------------------------------------------------------

@router.get("/{job_id}/events")
async def job_events(job_id: str) -> EventSourceResponse:
    """SSE stream of correction job events."""
    if job_store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")

    async def generator() -> AsyncGenerator[dict, None]:
        async for sse_event in job_store.stream_events(job_id):
            yield {
                "event": sse_event.event,
                "data": json.dumps(sse_event.data),
            }

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/download
# ---------------------------------------------------------------------------

@router.get("/{job_id}/download")
async def download_job(job_id: str) -> Response:
    """Download corrected XML file(s)."""
    if job_store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")

    out_files = get_output_files(job_id)
    if not out_files:
        raise HTTPException(
            status_code=404,
            detail="Output not ready yet. Wait for job to complete.",
        )

    if len(out_files) == 1:
        xml_path = out_files[0]
        return Response(
            content=xml_path.read_bytes(),
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{xml_path.name}"'
            },
        )

    # Multiple files → ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in out_files:
            zf.write(p, arcname=p.name)
    buf.seek(0)

    zip_name = f"job_{job_id}_corrected.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/diff
# ---------------------------------------------------------------------------

@router.get("/{job_id}/diff")
async def get_job_diff(job_id: str) -> dict:
    """Return per-line OCR vs corrected diff data for a completed job."""
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (status: {job.status.value})",
        )
    if job.document_manifest is None:
        raise HTTPException(status_code=404, detail="No document manifest available.")

    pages_out = []
    total_lines = 0
    modified_lines = 0
    hyphen_pairs = 0

    for page in job.document_manifest.pages:
        lines_out = []
        for lm in page.lines:
            corrected = lm.corrected_text if lm.corrected_text is not None else lm.ocr_text
            modified = corrected != lm.ocr_text
            lines_out.append({
                "line_id": lm.line_id,
                "ocr_text": lm.ocr_text,
                "corrected_text": corrected,
                "modified": modified,
                "hyphen_role": lm.hyphen_role.value,
                "hyphen_subs_content": lm.hyphen_subs_content,
            })
            total_lines += 1
            if modified:
                modified_lines += 1
            if lm.hyphen_role == HyphenRole.PART1:
                hyphen_pairs += 1

        pages_out.append({
            "page_id": page.page_id,
            "page_index": page.page_index,
            "lines": lines_out,
        })

    return {
        "job_id": job_id,
        "pages": pages_out,
        "stats": {
            "total_lines": total_lines,
            "modified_lines": modified_lines,
            "hyphen_pairs": hyphen_pairs,
        },
    }


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/layout
# ---------------------------------------------------------------------------

@router.get("/{job_id}/layout")
async def get_job_layout(job_id: str) -> dict:
    """Return structural layout data (blocks + lines with ALTO coordinates)."""
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (status: {job.status.value})",
        )
    if job.document_manifest is None:
        raise HTTPException(status_code=404, detail="No document manifest available.")

    pages_out = []
    for page in job.document_manifest.pages:
        line_by_id = {lm.line_id: lm for lm in page.lines}

        blocks_out = []
        for block in page.blocks:
            lines_out = []
            for line_id in block.line_ids:
                lm = line_by_id.get(line_id)
                if lm is None:
                    continue
                corrected = lm.corrected_text if lm.corrected_text is not None else lm.ocr_text
                lines_out.append({
                    "line_id": lm.line_id,
                    "hpos": lm.coords.hpos,
                    "vpos": lm.coords.vpos,
                    "width": lm.coords.width,
                    "height": lm.coords.height,
                    "ocr_text": lm.ocr_text,
                    "corrected_text": corrected,
                    "modified": corrected != lm.ocr_text,
                    "hyphen_role": lm.hyphen_role.value,
                })
            blocks_out.append({
                "block_id": block.block_id,
                "hpos": block.coords.hpos,
                "vpos": block.coords.vpos,
                "width": block.coords.width,
                "height": block.coords.height,
                "lines": lines_out,
            })

        image_filename = job.images.get(page.page_id)
        image_url = f"/api/jobs/{job_id}/images/{image_filename}" if image_filename else None
        pages_out.append({
            "page_id": page.page_id,
            "page_index": page.page_index,
            "page_width": page.page_width,
            "page_height": page.page_height,
            "image_url": image_url,
            "blocks": blocks_out,
        })

    return {"job_id": job_id, "pages": pages_out}


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/images/{image_name}
# ---------------------------------------------------------------------------

_IMAGE_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


@router.get("/{job_id}/images/{image_name}")
async def get_job_image(job_id: str, image_name: str) -> Response:
    """Serve a source scan image for a job."""
    if job_store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")

    # Sanitise: only allow plain filenames (no path traversal)
    if "/" in image_name or "\\" in image_name or image_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid image name.")

    img_path = images_dir(job_id) / image_name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {image_name!r}")

    mime = _IMAGE_MIME.get(img_path.suffix.lower(), "application/octet-stream")
    return Response(content=img_path.read_bytes(), media_type=mime)
