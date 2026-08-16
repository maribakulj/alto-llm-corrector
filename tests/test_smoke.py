"""Smoke tests for the saknussemm package.

These tests don't try to be exhaustive — the heavy lifting is still
done by the backend test suite that exercises the modules through the
re-export shim. The goal here is to catch the most obvious extraction
mistakes: missing files, broken imports, exported symbols that vanished.

When the saknussemm package gets its own consumer (eScriptorium bridge,
benchmark runner, etc.), this file will grow into a full test surface.
"""

from __future__ import annotations


def test_top_level_import():
    import saknussemm

    assert isinstance(saknussemm.__version__, str)
    # X.Y.Z semver shape — the exact value is the release's business, but a
    # malformed version string breaks packaging (hatchling reads this).
    parts = saknussemm.__version__.split(".")
    assert len(parts) >= 3 and parts[0].isdigit(), saknussemm.__version__


def test_subpackages_importable():
    import saknussemm.core.hyphenation
    import saknussemm.formats.alto.parser
    import saknussemm.formats.alto.rewriter
    import saknussemm.core.planner
    import saknussemm.core.pipeline
    import saknussemm.core.guards
    import saknussemm.core.validator
    import saknussemm.core.protocols
    import saknussemm.integrations.llm
    import saknussemm.core.schemas

    # Touch attributes that consumers will reach for, so a missing
    # rename in the extraction trips here rather than at first call.
    assert saknussemm.core.pipeline.CorrectionPipeline
    assert saknussemm.core.protocols.BaseProvider
    assert saknussemm.core.protocols.PipelineObserver
    assert saknussemm.core.protocols.FormatAdapter
    assert saknussemm.integrations.llm.OUTPUT_JSON_SCHEMA
    assert saknussemm.integrations.llm.SYSTEM_PROMPT
    assert saknussemm.core.schemas.LineManifest
    assert saknussemm.core.schemas.DocumentManifest


def test_top_level_public_api_is_importable():
    """The README and ARCHITECTURE.md promise a single import surface.
    If a future refactor drops one of these re-exports, this test trips.

    The list MUST stay in sync with ``saknussemm.__all__`` (less
    ``__version__`` which is checked separately in
    ``test_top_level_import``). The shared smoke script
    ``packages/saknussemm/_smoke_imports.py`` iterates ``__all__``
    directly to enforce the same contract from CI/release tooling.
    """
    from saknussemm import (
        BlockManifest,
        ChunkGranularity,
        ChunkPlannerConfig,
        CorrectionPipeline,
        CorrectionResult,
        DocumentManifest,
        HyphenRole,
        LineManifest,
        LineStatus,
        LineTrace,
        LineContext,
        PageManifest,
        PipelineObserver,
        sanitize_error,
    )
    from saknussemm.core.protocols import BaseProvider
    from saknussemm.core.schemas import LineProposal, ModelInfo
    from saknussemm.formats.alto.parser import build_document_manifest, parse_alto_file
    from saknussemm.formats.alto.rewriter import extract_output_texts, rewrite_alto_file
    from saknussemm.integrations.llm import OUTPUT_JSON_SCHEMA, SYSTEM_PROMPT

    # Just touch each one so flake/mypy can't optimise the import away.
    assert all(
        x is not None
        for x in (
            BaseProvider,
            PipelineObserver,
            CorrectionPipeline,
            CorrectionResult,
            build_document_manifest,
            parse_alto_file,
            rewrite_alto_file,
            extract_output_texts,
            OUTPUT_JSON_SCHEMA,
            SYSTEM_PROMPT,
            sanitize_error,
            DocumentManifest,
            PageManifest,
            BlockManifest,
            LineManifest,
            HyphenRole,
            LineStatus,
            ChunkGranularity,
            ChunkPlannerConfig,
            ModelInfo,
            LineTrace,
            LineContext,
            LineProposal,
        )
    )


def test_all_matches_top_level_attrs():
    """Roadmap L5 (P8) — ``saknussemm.__all__`` must reflect what's
    actually accessible on the package object. A symbol listed in
    ``__all__`` but missing from the module would silently break
    ``from saknussemm import *`` downstream.
    """
    import saknussemm

    for name in saknussemm.__all__:
        assert hasattr(saknussemm, name), (
            f"{name!r} is listed in saknussemm.__all__ but not present "
            f"on the saknussemm module — broken __init__.py re-export"
        )


def test_changelog_added_symbols_are_importable():
    """Roadmap L5 (B5) — every symbol the CHANGELOG promises in its
    ``### Added`` section must be importable from the documented path.

    The CHANGELOG groups symbols under sub-module headings like
    ``saknussemm.formats.alto`` / ``saknussemm.core``; this test pins the
    promise so a future rename or move breaks the test before it
    breaks a PyPI consumer. The map below is the canonical list — when
    you change the CHANGELOG, sync this map (one line per move).

    NB this test does NOT assert that every listed symbol is a
    top-level re-export. The roadmap explicitly clarifies in the
    CHANGELOG that some symbols are sub-module only; that's checked
    by ``test_top_level_public_api_is_importable`` for the top-level
    set, and HERE for the broader sub-module set.
    """
    import importlib

    # (module path, [symbols expected on that module]).
    # Source of truth: packages/saknussemm/CHANGELOG.md ### Added section.
    expected: list[tuple[str, list[str]]] = [
        # saknussemm.formats.alto
        (
            "saknussemm.formats.alto.parser",
            ["parse_alto_file", "build_document_manifest"],
        ),
        (
            "saknussemm.formats.alto.rewriter",
            ["rewrite_alto_file", "extract_output_texts", "RewriterMetrics"],
        ),
        (
            "saknussemm.core.hyphenation",
            [
                "enrich_chunk_lines",
                "reconcile_hyphen_pair",
                "ReconcileMetrics",
                "classify_reconcile_outcome",
            ],
        ),
        # saknussemm.core
        (
            "saknussemm.core.pipeline",
            ["CorrectionPipeline", "CorrectionResult", "sanitize_error"],
        ),
        ("saknussemm.core.planner", ["plan_page", "downgrade_granularity"]),
        ("saknussemm.core.validator", ["validate_llm_response"]),
        (
            "saknussemm.core.guards",
            ["check_line", "check_adjacent_duplicates", "AcceptanceResult"],
        ),
        # saknussemm.core.protocols
        (
            "saknussemm.core.protocols",
            [
                "BaseProvider",
                "PipelineObserver",
                # P0-1 provider taxonomy (Unreleased ### Added)
                "ProviderTransientError",
                "ProviderPermanentError",
                # P3.7-4 producer identity (Unreleased ### Added)
                "ProducerMetadata",
            ],
        ),
        ("saknussemm.integrations.llm", ["OUTPUT_JSON_SCHEMA", "SYSTEM_PROMPT"]),
        # saknussemm.errors — P0-5 (Unreleased ### Added)
        ("saknussemm.errors", ["DuplicateIdError"]),
    ]

    missing: list[str] = []
    for module_path, symbols in expected:
        mod = importlib.import_module(module_path)
        for name in symbols:
            if not hasattr(mod, name):
                missing.append(f"{module_path}.{name}")

    assert not missing, (
        "CHANGELOG.md promises these symbols but they are not importable "
        f"from their documented path: {missing}. Either fix the import "
        f"path, fix the CHANGELOG, or update the expected map in this test."
    )


def test_correction_pipeline_construction_does_not_touch_infrastructure():
    """A bare ``CorrectionPipeline`` should instantiate from mock ports —
    no filesystem, no HTTP, no global state."""
    from saknussemm.core.pipeline import CorrectionPipeline

    class _NoopProvider:
        async def list_models(self, api_key):  # pragma: no cover
            return []

        async def complete_structured(self, **_kwargs):  # pragma: no cover
            return {"lines": []}, None

    class _NoopObserver:
        def on_event(self, event_type, payload):
            pass

    pipeline = CorrectionPipeline.for_provider(
        _NoopProvider(),
        api_key="k",
        model="m",
        observer=_NoopObserver(),
    )
    assert pipeline.producer is not None
    assert pipeline.observer is not None
