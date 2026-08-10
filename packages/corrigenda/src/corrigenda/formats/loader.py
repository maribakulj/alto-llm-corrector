"""Namespace-driven format detection and the generic manifest builder (§3).

The document says what it is: each file's root namespace selects the
ALTO or PAGE parser — nobody passes a format flag. One format per
document (a mixed ALTO+PAGE batch has no single rewriter).

Any host ingesting user files should build its manifest through this
module rather than importing a format-specific parser: the ALTO parser
applied to a valid PAGE file finds no ALTO pages and yields an EMPTY
manifest (0 pages, 0 lines) instead of an error — a silent mis-read,
not a refusal. ``corrigenda.load()`` (the facade) is this module plus
basename bookkeeping; hosts that carry their own (path, source_name)
pairs and a :class:`PairingPolicy` call :func:`build_document_manifest`
directly.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from corrigenda.core.protocols import FormatAdapter
from corrigenda.core.schemas import (
    DEFAULT_PAIRING_POLICY,
    DocumentManifest,
    PairingPolicy,
)
from corrigenda.errors import ConfigurationError, ParseError
from corrigenda.formats._xml import (
    classified_parse_errors,
    detect_namespace,
    make_safe_parser,
)

_ALTO_MARKER = "loc.gov/standards/alto"
_PAGE_MARKER = "primaresearch.org/PAGE"


def sniff_format(path: Path) -> str:
    """``"alto"`` / ``"page"`` from the file's root namespace."""
    with classified_parse_errors(path.name):
        root = etree.parse(str(path), make_safe_parser()).getroot()
    ns = detect_namespace(root)
    if _ALTO_MARKER in ns:
        return "alto"
    if _PAGE_MARKER in ns:
        return "page"
    raise ParseError(
        f"{path.name!r}: root namespace {ns!r} is neither ALTO nor PAGE — "
        "corrigenda only speaks those two; parse other formats through "
        "their own adapter."
    )


def build_document_manifest(
    files: list[tuple[Path, str]],
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> DocumentManifest:
    """Build a manifest from ``(xml_path, source_name)`` pairs, any format.

    Same signature as the per-format builders it dispatches to
    (``formats.alto.parser`` / ``formats.page.parser``), so it is a
    drop-in replacement wherever one of them was hard-wired. The format
    is sniffed per file from the root namespace; a mixed batch raises
    :class:`ParseError` (one document, one format — ADR: a document has
    exactly one rewriter).
    """
    if not files:
        raise ParseError("build_document_manifest() needs at least one file")

    formats = {name: sniff_format(path) for path, name in files}
    distinct = set(formats.values())
    if len(distinct) > 1:
        detail = ", ".join(f"{name}: {fmt}" for name, fmt in formats.items())
        raise ParseError(
            f"one document, one format — got a mix ({detail}). "
            "Load ALTO and PAGE files as separate documents."
        )

    if distinct == {"page"}:
        from corrigenda.formats.page.parser import (
            build_document_manifest as build,
        )
    else:
        from corrigenda.formats.alto.parser import (
            build_document_manifest as build,
        )
    return build(files, pairing_policy=pairing_policy)


def adapter_for_format(source_format: str | None) -> FormatAdapter:
    """Resolve the adapter the MANIFEST declares — no implicit default (§3).

    The format travels with the document: the parsers stamp
    ``DocumentManifest.source_format`` and the engine derives the matching
    adapter from it. A manifest without a stamped format (hand-built) has
    no derivable adapter, and silently assuming one — the historical ALTO
    default — is exactly how a PAGE document ended up rewritten by the
    ALTO rewriter.

    Lives here since `RM-07`, next to :func:`build_document_manifest`,
    because the two answer the same question: which module speaks this
    format. It sat in ``core/provenance.py`` before, where it was the one
    place the pure core enumerated ALTO and PAGE by name — lazily, so no
    import rule was broken, but the knowledge was there and a third format
    would have had to be added to a core module to be usable.

    The imports stay function-local: this module is reached from ``core``
    lazily too (``core/rendering.py``, the single remaining lazy site),
    and eager adapter imports would pull both rewriters for a run that
    writes one format.
    """
    if source_format == "alto":
        from corrigenda.formats.alto.adapter import AltoFormatAdapter

        return AltoFormatAdapter()
    if source_format == "page":
        from corrigenda.formats.page.adapter import PageFormatAdapter

        return PageFormatAdapter()
    raise ConfigurationError(
        f"the manifest declares no derivable format "
        f"(source_format={source_format!r}); load the document through a "
        "corrigenda format parser, or inject format_adapter explicitly "
        "on the pipeline"
    )


__all__ = ["adapter_for_format", "build_document_manifest", "sniff_format"]
