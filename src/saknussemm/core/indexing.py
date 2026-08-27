"""The per-line indexes a run builds before it can correct anything.

Three facts about the document have to exist before the first chunk is
planned: the trace each line starts from, the page-qualified registry that
makes a partner on another page findable, and how many hyphen units the
document holds. They are an INDEX, derived from the manifest alone — not
part of the run — and one pass builds all three. Line identity is
``(page_id, line_id)`` throughout (ADR-001/ADR-007): a bare ``line_id``
legitimately repeats across source files, so every key here is a
:class:`LineRef`.
"""

from __future__ import annotations

from dataclasses import dataclass

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.pairing import forward_ref, pair_ref
from saknussemm.core.schemas import (
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

    Built once, from the run's private manifest copy (ADR-011).
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

    Les deux slots, dans les deux sens : une page peut porter l'un ou
    l'autre bout d'une unité qui enjambe une coupure, et les deux lectures
    passent par :func:`~saknussemm.core.pairing.pair_ref` et
    :func:`~saknussemm.core.pairing.forward_ref` — les seules qui savent
    qu'un pointeur sans ``page_id`` désigne la page de la ligne qui le
    porte. Ce site lisait les quatre champs directement et réexprimait
    cette qualification par un test sur la vacuité du ``page_id``.

    Les partenaires de cette page-ci sont écartés : ses propres lignes sont
    déjà en portée.

    Rend ``None`` quand toutes les unités de la page sont locales, pour que
    l'appelant distingue « rien à emprunter » de « une carte vide qu'il faut
    quand même faire voyager ».
    """
    partners: dict[LineRef, LineManifest] = {}
    for lm in page.lines:
        for ref in (pair_ref(lm), forward_ref(lm)):
            if ref is None or ref.page_id == page.page_id:
                continue
            partner = lines.get(ref)
            if partner is not None:
                partners[ref] = partner
    return partners or None
