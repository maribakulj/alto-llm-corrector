"""Public-API snapshot — an inventory held still, NOT the 1.0 contract.

This file used to call the list below ``PUBLIC_API_1_0`` and describe it as
"the frozen 1.0 surface". That was false in a way worth naming, because the
name is what a reader trusts: the 95 entries were never ratified as a
contract, they **accreted**. Each was added because something needed it that
day. `docs/PLAN.md` (`S3`) computes what the surface should be — the
transitive closure of what the façade returns, 54 symbols — and the
reduction has not happened yet. A test asserting the accretion is the 1.0
promise contradicted the plan and would have made the cut look like a
regression.

So, plainly: **the surface is provisional.** The 0.9.x series is explicitly
free to break it (`docs/versioning.md`), and it will be cut once the
structural work that decides the final shape (`S2`) has landed.

What this snapshot is for, meanwhile, is the ratchet. The list got to 95 by
accretion; the only thing that stops it reaching 110 while the cut waits is
that no name can join it silently. Four pins:

  1. ``corrigenda.__all__`` is EXACTLY the list below. Adding a symbol is a
     deliberate act (update the snapshot + CHANGELOG) — and during the
     feature freeze, extending the public API is suspended outright, so an
     addition needs a reason that survives review.
  2. The surface does not GROW. Stated separately from (1) because it is the
     property that matters while the reduction is pending, and it should
     fail with that sentence rather than a diff of 95 strings.
  3. Every listed symbol actually resolves — eager or lazy (PEP 562) — and
     every lazy-map key is part of ``__all__``.
  4. The signatures of the top entry points (``run``, ``run_sync``,
     ``for_provider``) and the ``CorrectionReport`` JSON keys are pinned:
     these are what consumer code and persisted artefacts depend on.

If this test fails after an intentional change, update the snapshot in the
same commit that documents the change in CHANGELOG.md.
"""

from __future__ import annotations

import inspect

import corrigenda

# ---------------------------------------------------------------------------
# 1. The current surface — what `__all__` holds today, not what it should hold
# ---------------------------------------------------------------------------

#: The provisional top-level surface. `S3` reduces this to the computed
#: closure (54); until then it is pinned so that it can only shrink or move
#: deliberately. Do not read this list as a promise to consumers.
CURRENT_TOP_LEVEL_SURFACE = sorted(
    [
        # Version
        "__version__",
        # Parsers / rewriters / adapters (lazy — formats)
        "build_document_manifest",
        "parse_alto_file",
        "extract_output_texts",
        "rewrite_alto_file",
        "parse_page_file",
        "rewrite_page_file",
        "AltoFormatAdapter",
        "PageFormatAdapter",
        # Happy path (§2, P3.12 — lazy: formats)
        "load",
        "correct",
        "correct_sync",
        "LoadedDocument",
        # Pipeline
        "CorrectionPipeline",
        "CorrectionResult",
        # Decisions (ADR-011, slice E)
        "DecisionSet",
        "LineDecision",
        "LineRef",
        # Edit protocol (§4)
        "EDIT_PROTOCOL_VERSION",
        "EditScript",
        "EditOp",
        "ReplaceLine",
        "ReplaceSpan",
        "MatchAnchor",
        "RangeAnchor",
        "EditResult",
        "EditRejection",
        "LinePrecondition",
        "apply_edit_script",
        "line_digest",
        "normalize_anchor",
        # Producers (§5)
        "EditProducer",
        "ProducerMetadata",
        "ProducerOptions",
        "require_capabilities",
        "require_page_images",
        "RulesProducer",
        "SubstitutionRule",
        "default_french_ocr_rules",
        "LLMEditProducer",
        # Errors (§8.4) — canonical names since P3.11; the old names are
        # 0.9.x deprecation aliases of the SAME classes.
        "CorrigendaError",
        "CorrectionError",
        "ParseError",
        "DuplicateIdError",  # P0-5 — additive, subclasses ParseError
        "ProposalValidationError",
        "ValidationError",
        "CorrectionAborted",
        # Ports
        "BaseProvider",
        "ModelCatalog",
        "PipelineObserver",
        "StructuredCompletionClient",
        # LLM contract (lazy — producers)
        "OUTPUT_JSON_SCHEMA",
        "SYSTEM_PROMPT",
        "sanitize_error",
        # Schemas (domain)
        "BlockManifest",
        "ChunkGranularity",
        "ChunkPlannerConfig",
        "CorrectionReport",
        "DocumentManifest",
        "GuardConfig",
        "HyphenRole",
        "LineManifest",
        "LineStatus",
        "LineTrace",
        "LineContext",
        "LineProposal",
        "LossPolicy",
        "ModelCapabilities",
        "ModelInfo",
        "PageManifest",
        "PairingPolicy",
        "RetryPolicy",
        "Usage",
        # Report v2 (§9, P3.5)
        "LineOutcome",
        "ProposalStage",
        "ProposalFeatures",
        "DecisionStage",
        "DecisionReason",
        "ProjectionStage",
        # Provenance (§11, P3.9)
        "ProducerProvenance",
        "RunProvenance",
        # token_realign sidecar (ROADMAP V3 Phase 1) — additive
        "SidecarEntry",
        # Confidence block (ROADMAP V3 Phase 1) — additive
        "ConfidencePolicy",
        "ConfidenceScorer",
        "HeuristicScorer",
        "LineConfidence",
        # QE + routing (ROADMAP V3 Phase 3) — additive
        "HeuristicQEScorer",
        "QEScorer",
        "RoutingDecision",
        "RoutingPolicy",
        "route_line",
        # Structured page image (ROADMAP V3 Phase 4) — additive
        "ImageAsset",
        "ImageRef",
        "ImageTransform",
        "PageImage",
    ]
)


def test_public_api_is_exactly_the_snapshot():
    assert sorted(corrigenda.__all__) == CURRENT_TOP_LEVEL_SURFACE, (
        "corrigenda.__all__ drifted from the pinned surface. If deliberate, "
        "update CURRENT_TOP_LEVEL_SURFACE here AND document the change in "
        "CHANGELOG.md. Before 1.0 a removal is allowed (0.9.x may break); "
        "after 1.0 it is a MAJOR bump."
    )


def test_the_surface_does_not_grow_while_the_reduction_is_pending():
    """The ratchet. `S3` cuts this list to 54; nothing may push it upward in
    the meantime, and the feature freeze suspends public-API extension
    anyway. A shrink is the point and passes here — pin (1) catches it."""
    assert len(corrigenda.__all__) <= len(CURRENT_TOP_LEVEL_SURFACE), (
        f"the top-level surface grew to {len(corrigenda.__all__)} symbols. "
        "It reached 95 by accretion once already, which is what S3 exists to "
        "undo — adding to it now makes that cut larger. Export from the "
        "symbol's own module instead, or close S3 first."
    )


def test_every_public_symbol_resolves():
    for name in corrigenda.__all__:
        obj = getattr(corrigenda, name)  # raises AttributeError on breakage
        assert obj is not None, name


def test_lazy_map_is_subset_of_public_api():
    from corrigenda import _LAZY

    unknown = set(_LAZY) - set(corrigenda.__all__)
    assert not unknown, f"lazy symbols not in __all__: {sorted(unknown)}"


# ---------------------------------------------------------------------------
# 3. Entry-point signatures + report keys
# ---------------------------------------------------------------------------


def _param_names(func) -> list[str]:
    return [p for p in inspect.signature(func).parameters if p != "self"]


def test_run_and_run_sync_signatures_are_pinned():
    expected = [
        "document_manifest",
        "source_files",
        "run_id",
        "should_abort",
        "page_images",
    ]
    assert _param_names(corrigenda.CorrectionPipeline.run) == expected
    assert _param_names(corrigenda.CorrectionPipeline.run_sync) == expected
    # §5.1 resorption — credentials must NEVER reappear on the run surface.
    for banned in ("api_key", "model", "provider_name"):
        assert banned not in expected


def test_for_provider_signature_is_pinned():
    params = _param_names(corrigenda.CorrectionPipeline.for_provider)
    assert params[0] == "provider"
    for required in ("api_key", "model", "provider_name", "observer"):
        assert required in params
    # ADR-011 slice D-fin — persistence left the engine surface for good.
    assert "output_writer" not in params
    assert "output_writer" not in _param_names(corrigenda.CorrectionPipeline.__init__)


def test_correction_report_json_keys_are_pinned():
    report = corrigenda.CorrectionReport(run_id="r")
    keys = set(report.model_dump().keys())
    assert keys == {
        "report_version",
        "run_id",
        "total_lines",
        "lines",
        "format_losses",
        # Optional and additive: absent from a run that wrote no file, and
        # a v2.0 consumer that ignores unknown keys is unaffected — so it
        # does NOT bump CORRECTION_REPORT_VERSION.
        "projection_fidelity",
        # Same contract: optional, absent when every break found its
        # partner, so no CORRECTION_REPORT_VERSION bump.
        "unpaired_breaks",
        # R6 — the units the planner CUT. Same contract again: optional,
        # absent when no chain was severed, no version bump.
        "hyphen_splits",
        "provenance",  # P3.9 — optional, additive (no version bump)
        "usage",  # ROADMAP V3 Phase 0 — optional, additive (no version bump)
        "sidecar",  # ROADMAP V3 Phase 1 — optional, additive (no version bump)
    }, (
        "CorrectionReport JSON shape moved — a key removal/rename requires "
        "bumping CORRECTION_REPORT_VERSION (§9); an addition must stay "
        "optional."
    )
    assert report.report_version == "2.0"
