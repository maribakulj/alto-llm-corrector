"""Hand-built post-page-loop state, for the finalisation passes.

The document-wide passes in ``core/finalize.py`` run on a manifest whose
lines have already been through the producer: ``corrected_text`` set,
``status`` terminal-ish, a trace per line. Building that state directly —
rather than running a pipeline to reach it — is what lets a test permute
the passes and compare, which is the whole point of `RM-05a`.
"""

from __future__ import annotations

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.schemas import (
    BlockManifest,
    Coords,
    DocumentManifest,
    LineManifest,
    LineStatus,
    LineTrace,
    PageManifest,
)


def line(
    index: int,
    ocr: str,
    corrected: str | None = None,
    *,
    page_id: str = "p1",
    status: LineStatus = LineStatus.CORRECTED,
) -> LineManifest:
    """One line as the page loop leaves it."""
    return LineManifest(
        line_id=f"L{index}",
        page_id=page_id,
        block_id="b1",
        line_order_global=index,
        line_order_in_block=index,
        coords=Coords(hpos=0, vpos=index * 10, width=100, height=10),
        ocr_text=ocr,
        corrected_text=ocr if corrected is None else corrected,
        status=status,
    )


def document(
    lines: list[LineManifest], *, source_file: str = "f.xml"
) -> tuple[DocumentManifest, dict[LineRef, LineManifest], dict[LineRef, LineTrace]]:
    """``(manifest, all_lines, traces)`` — the three things every
    document-wide pass in ``core/finalize.py`` is handed."""
    page = PageManifest(
        page_id=lines[0].page_id,
        source_file=source_file,
        page_index=0,
        page_width=1000,
        page_height=1000,
        blocks=[
            BlockManifest(
                block_id="b1",
                page_id=lines[0].page_id,
                block_order=0,
                coords=Coords(hpos=0, vpos=0, width=1000, height=1000),
                line_ids=[lm.line_id for lm in lines],
            )
        ],
        lines=lines,
    )
    manifest = DocumentManifest(
        source_files=[source_file], pages=[page], source_format="alto"
    )
    all_lines = {line_ref(lm): lm for lm in lines}
    traces = {
        line_ref(lm): LineTrace(
            line_id=lm.line_id, page_id=lm.page_id, source_ocr_text=lm.ocr_text
        )
        for lm in lines
    }
    return manifest, all_lines, traces


def snapshot(
    manifest: DocumentManifest, traces: dict[LineRef, LineTrace]
) -> dict[str, tuple[str | None, str, str | None]]:
    """What a consumer would see: ``line_id -> (text, status, reason)``."""
    return {
        lm.line_id: (
            lm.corrected_text,
            lm.status.value,
            traces[line_ref(lm)].fallback_reason,
        )
        for page in manifest.pages
        for lm in page.lines
    }
