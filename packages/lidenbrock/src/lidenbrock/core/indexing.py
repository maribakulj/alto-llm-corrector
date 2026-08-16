"""The per-line indexes a run builds before it can correct anything.

Three facts about the document have to exist before the first chunk is
planned: the trace each line starts from, the page-qualified registry that
makes a partner on another page findable, and how many hyphen units the
document holds. The orchestrator built all three with three separate
traversals of every page of every file, interleaved with the event it emits
about them — which is why the traversals kept being read as part of the run
and not as what they are: an index, derived from the manifest alone.

One pass now, and one value to carry. Line identity is
``(page_id, line_id)`` throughout (ADR-001/ADR-007): a bare ``line_id``
legitimately repeats across source files, so every key here is a
:class:`LineRef`.
"""

from __future__ import annotations

from dataclasses import dataclass

from lidenbrock.core.identity import LineRef, line_ref
from lidenbrock.core.schemas import (
    DocumentManifest,
    HyphenRole,
    LineManifest,
    LineTrace,
    PageManifest,
)

#: The roles that OPEN a hyphen unit — counting these counts units, not
#: member lines (``BOTH`` is a chain's middle: it opens one and closes
#: the previous, so counting openings never double-counts a chain).
_OPENS_A_UNIT = (HyphenRole.PART1, HyphenRole.BOTH)


@dataclass(frozen=True)
class DocumentIndex:
    """What a run knows about its document before any correction work.

    Built once, from the run's private manifest copy (ADR-011 slice E).
    ``traces`` is handed to every later stage and accumulates as the run
    goes; ``lines`` and ``hyphen_pairs`` are read-only views of the
    document as parsed.
    """

    #: The starting trace per line — source OCR text and hyphen role, the
    #: baseline every later stage records against.
    traces: dict[LineRef, LineTrace]
    #: Every line of every page, page-qualified. The lookup a cross-page
    #: hyphen partner needs, and the registry the document-wide passes
    #: apply their unit-atomic reverts through.
    lines: dict[LineRef, LineManifest]
    #: Hyphen units in the document, announced to observers up front.
    hyphen_pairs: int


def _index_document(document_manifest: DocumentManifest) -> DocumentIndex:
    """Index every line of the document once."""
    traces: dict[LineRef, LineTrace] = {}
    lines: dict[LineRef, LineManifest] = {}
    hyphen_pairs = 0
    for page in document_manifest.pages:
        for lm in page.lines:
            ref = line_ref(lm)
            lines[ref] = lm
            traces[ref] = LineTrace(
                line_id=lm.line_id,
                page_id=lm.page_id,
                source_ocr_text=lm.ocr_text,
                hyphen_role=lm.hyphen_role.value,
            )
            if lm.hyphen_role in _OPENS_A_UNIT:
                hyphen_pairs += 1
    return DocumentIndex(traces=traces, lines=lines, hyphen_pairs=hyphen_pairs)


def _cross_page_partners(
    page: PageManifest,
    lines: dict[LineRef, LineManifest],
) -> dict[LineRef, LineManifest] | None:
    """The partners this page's hyphen units need from OTHER pages.

    Both directions are collected — the backward link (``hyphen_pair_*``,
    a PART2 pointing at the PART1 that opened its unit) and the forward
    one (``hyphen_forward_pair_*``) — because a page can hold either end
    of a unit that straddles a page break. Partners on this same page are
    skipped: the page's own lines are already in scope.

    Returns ``None`` when the page's units are all local, so the caller
    can tell "nothing to bring in" from "an empty mapping I must still
    thread through".
    """
    partners: dict[LineRef, LineManifest] = {}
    for lm in page.lines:
        for partner_id, partner_page in (
            (lm.hyphen_pair_line_id, lm.hyphen_pair_page_id),
            (lm.hyphen_forward_pair_id, lm.hyphen_forward_pair_page_id),
        ):
            if not partner_id or not partner_page:
                continue
            if partner_page == page.page_id:
                continue
            ref = LineRef(page_id=partner_page, line_id=partner_id)
            partner = lines.get(ref)
            if partner is not None:
                partners[ref] = partner
    return partners or None
