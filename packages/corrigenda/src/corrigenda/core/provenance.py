"""What a run records about its own inputs and dependencies (§11).

Three small, pure helpers the orchestrator used to carry: which format
adapter serves a document, which dependency versions were installed, and the
digest of every source file. None of them touches run state (S2).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from corrigenda.core.protocols import FormatAdapter
from corrigenda.errors import ConfigurationError


def _adapter_for_format(source_format: str | None) -> FormatAdapter:
    """Resolve the adapter the MANIFEST declares — no implicit default (§3).

    The format travels with the document: the parsers stamp
    ``DocumentManifest.source_format`` and the engine derives the
    matching adapter here. A manifest without a stamped format
    (hand-built) has no derivable adapter, and silently assuming one —
    the historical ALTO default — is exactly how a PAGE document ended
    up rewritten by the ALTO rewriter.

    This function is the ONLY place ``core`` touches a concrete format,
    and the imports are function-local so importing any
    ``corrigenda.core`` module never loads lxml. The import-contract
    test pins both facts: core modules carry no static formats/lxml
    import, and this exact function is the single allowed lazy site.
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


#: The dependencies whose installed version a run records.
_PROVENANCE_DEPENDENCIES = ("lxml", "pydantic")


def _dependency_versions() -> dict[str, str]:
    """Installed versions of the critical dependencies; a package that
    is not installed is simply absent (never an error — a core-only
    consumer legitimately runs without lxml)."""
    import importlib.metadata as _md

    versions: dict[str, str] = {}
    for package in _PROVENANCE_DEPENDENCIES:
        try:
            versions[package] = _md.version(package)
        except _md.PackageNotFoundError:
            continue
    return versions


def _digest_sources(source_files: dict[str, Path]) -> dict[str, str]:
    """``sha256:<hex>`` of every input file's bytes, as GIVEN (P3.9/P3.10).

    Computed once per run and shared by the provenance record and the
    final edit script's preconditions — the two must agree by
    construction, not by coincidence.
    """
    return {
        name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in source_files.items()
    }
