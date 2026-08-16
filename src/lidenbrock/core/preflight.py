"""Everything a run refuses BEFORE spending any correction work.

Five checks, and the reason they are one function rather than five scattered
guards is that they share a property: each turns a mid-run surprise into a
start-up error. A vision producer with no images, a producer whose declared
capabilities contradict its wiring, an injected adapter that disagrees with
the format the manifest was parsed as, a duplicate identity, an image key
matching no page — every one of them would otherwise fail late, confusingly,
with correction work already spent.

Lifted out of ``_run_impl``: the 311-line orchestrator opened with 60
lines that decide nothing about how the run proceeds, only whether it may
start at all.
"""

from __future__ import annotations

from lidenbrock.core.context import RunContext
from lidenbrock.core.identity import (
    ensure_unique_identities,
    ensure_unique_page_ids_across_files,
)
from lidenbrock.core.protocols import (
    EditProducer,
    FormatAdapter,
    require_capabilities,
    require_page_images,
)
from lidenbrock.core.schemas import DocumentManifest, PageImage, PageManifest
from lidenbrock.errors import ConfigurationError


def _preflight(
    *,
    producer: EditProducer,
    escalation_producer: EditProducer | None,
    format_adapter: FormatAdapter | None,
    document_manifest: DocumentManifest,
    page_images: dict[str, PageImage] | None,
    ctx: RunContext,
) -> None:
    """Refuse a run that cannot honestly proceed. Mutates ``ctx`` with the
    per-page image envelope it validated."""
    # §5.1 — a vision producer without its images is a start-up error,
    # never a silent image-less call.
    require_page_images(producer, document_manifest.pages, page_images)
    # §5.2 bis — a producer whose declared capabilities
    # contradict its wiring (wants images but vision=False) is a
    # start-up error, not a mid-run surprise.
    require_capabilities(producer)
    # the escalation (vision) producer is the one that needs
    # images: preflight it too, so a run that WILL escalate fails at
    # start-up if its VLM lacks a scan, never mid-run.
    if escalation_producer is not None:
        require_page_images(escalation_producer, document_manifest.pages, page_images)
        require_capabilities(escalation_producer)

    # §3 — the format travels with the document. An injected adapter
    # that contradicts the format the manifest was parsed as would
    # only surface at write time (as a confusing projection failure);
    # refuse it before any correction work is spent. Adapters without
    # a ``format_name`` (custom implementations) are trusted as-is.
    declared = document_manifest.source_format
    adapter_format = getattr(format_adapter, "format_name", None)
    if declared and adapter_format and declared != adapter_format:
        raise ConfigurationError(
            f"the injected format_adapter writes {adapter_format!r} but "
            f"the manifest was parsed as {declared!r} — parse with the "
            "matching lidenbrock parser or inject the matching adapter"
        )

    # ADR-007 — identity-uniqueness invariant, enforced at the pipeline
    # door so hand-built manifests get the same guarantee as
    # parser-built ones: within one source file every page/block/line
    # ID must be unique (correction-to-line association is keyed by
    # bare line_id per file), and page_ids must be unique across the
    # whole document (trace keys, per-page image/dimension lookups).
    pages_by_file: dict[str, list[PageManifest]] = {}
    for page in document_manifest.pages:
        pages_by_file.setdefault(page.source_file, []).append(page)
    for src_name, src_pages in pages_by_file.items():
        ensure_unique_identities(src_pages, src_name)
    ensure_unique_page_ids_across_files(document_manifest.pages)
    # §4.1 — per-page vision envelope lookups. Pure copying: the
    # ImageRef stays an opaque string end to end. A key matching no
    # page is refused: it is almost always a legacy file-name key
    # from the pre-page_images contract, silently dropping it would
    # reproduce the old wrong-image behaviour.
    images = page_images or {}
    known_pages = {page.page_id for page in document_manifest.pages}
    unknown = sorted(set(images) - known_pages)
    if unknown:
        raise ConfigurationError(
            f"page_images keys must be page ids; {unknown} match no "
            "page of this document (file-name keys are no longer "
            "accepted — pass one ImageRef per page_id)"
        )
    ctx.image_ref_by_page_id = dict(images)
    ctx.page_dims = {
        page.page_id: (page.page_width, page.page_height)
        for page in document_manifest.pages
    }
