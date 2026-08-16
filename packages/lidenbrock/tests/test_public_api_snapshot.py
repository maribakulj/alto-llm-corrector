"""Public-API snapshot — the computed closure, held still.

The list below is no longer an inventory of what accreted. It is what `S3b`
cut the surface down to (2026-08-01): **68 symbols, computed rather than
chosen**, and `RM-04` took it to **66** (2026-08-06) by demoting the two
knobs no default run uses. The computation is reproducible — start from
what
``load``/``correct``/``correct_sync`` return and from what
:class:`EditProducer` and :class:`PipelineObserver` name in their
signatures, then follow the type annotations transitively.

Two closures, because the library makes two promises. The README's first
sentence says corrections come "by LLM, rules engine, or **any custom
EditProducer**", so the producer seam is a promise as much as the result
is, and both are closed here: a caller typing the value it was handed, and
an implementer typing the protocol it fills, can import every name they
need from ``lidenbrock``.

What is deliberately NOT here is the third seam. ``format_adapter`` is an
optional injection whose closure drags in ``RewriteResult``,
``RewriteMetrics``, ``AlignedPair``, ``TokenAlignment`` — the rewriter's
internal accounting vocabulary, which `R5`/`R8`/`L8` have been moving all
year. Blessing it under SemVer at 1.0 would promise a stability nothing
supports. It stays at its module path, which `docs/versioning.md` documents
as a supported door.

`RM-04`'s two removals are ``ConfidencePolicy`` and ``RoutingPolicy``.
Both are constructor knobs whose defaults do nothing — ``mode="drop"``
computes no confidence, and a ``RoutingPolicy`` with both bounds ``None``
sends every line to the producer — and both belong to the research
programme the plan's freeze suspends. A top-level export reads as "ready";
these are not. They stay importable from ``core.schemas`` and
``core.quality``, the demotion door ``docs/versioning.md`` documents, so
the four calibration scripts are unaffected
(``tests/test_research_boundary.py`` pins their exact import paths).

What did NOT go, and the distinction is `I4`: ``ImageAsset``,
``ImageRef``, ``ImageTransform`` and ``PageImage`` stay on the surface.
They are not vision code — they are what the pure core CARRIES for a
producer that asks for pixels, and never opens. A custom ``EditProducer``
declaring ``wants_image`` is handed one, so they are inside the producer
seam's closure and leaving them out would break rule (3) below.

The former surface was 95, and the four numbers worth keeping straight are
in `docs/PLAN.md`: the plan's own estimate was 54, which turned out not to
be reproducible — it counted the advanced door's entry points without their
closure, which would have left exactly the holes `S3b` exists to close.

Four pins:

  1. ``lidenbrock.__all__`` is EXACTLY the list below. Adding a symbol is a
     deliberate act (update the snapshot + CHANGELOG) — and during the
     feature freeze, extending the public API is suspended outright.
  2. The surface does not GROW. Stated separately from (1) because it is
     the property that survives the cut, and it should fail with that
     sentence rather than a diff of 66 strings.
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

import lidenbrock

# ---------------------------------------------------------------------------
# 1. The current surface — what `__all__` holds today, not what it should hold
# ---------------------------------------------------------------------------

#: The provisional top-level surface. `S3` reduces this to the computed
#: closure (54); until then it is pinned so that it can only shrink or move
#: deliberately. Do not read this list as a promise to consumers.
#: The top-level surface, as computed by `S3b`. A symbol removed from here
#: is NOT deleted — it stays importable from its own module, which is the
#: other supported door (`docs/versioning.md`).
CURRENT_TOP_LEVEL_SURFACE = sorted(
    [
        "BlockManifest",
        "ChunkGranularity",
        "ChunkPlannerConfig",
        "Coords",
        "CorrectionAborted",
        "CorrectionError",
        "CorrectionPipeline",
        "CorrectionReport",
        "CorrectionRequest",
        "CorrectionResult",
        "LidenbrockError",
        "DecisionReason",
        "DecisionSet",
        "DecisionStage",
        "DocumentManifest",
        "DuplicateIdError",
        "EDIT_PROTOCOL_VERSION",
        "EditOp",
        "EditProducer",
        "EditScript",
        "GuardConfig",
        "HyphenRole",
        "HyphenSplit",
        "ImageAsset",
        "ImageRef",
        "ImageTransform",
        "LineConfidence",
        "LineContext",
        "LineDecision",
        "LineGeometry",
        "LineManifest",
        "LineOutcome",
        "LinePrecondition",
        "LineRef",
        "LineStatus",
        "LineTrace",
        "LoadedDocument",
        "LossPolicy",
        "MatchAnchor",
        "PageImage",
        "PageManifest",
        "PairingPolicy",
        "ParseError",
        "PipelineObserver",
        "ProducerMetadata",
        "ProducerOptions",
        "ProducerProvenance",
        "ProjectionFidelity",
        "ProjectionStage",
        "ProposalFeatures",
        "ProposalStage",
        "ProposalValidationError",
        "RangeAnchor",
        "ReconcileMetrics",
        "ReplaceLine",
        "ReplaceSpan",
        "RetryPolicy",
        "RunProvenance",
        "SidecarEntry",
        "Usage",
        "ValidationError",
        "__version__",
        "correct",
        "correct_sync",
        "load",
        "sanitize_error",
    ]
)


def test_public_api_is_exactly_the_snapshot():
    assert sorted(lidenbrock.__all__) == CURRENT_TOP_LEVEL_SURFACE, (
        "lidenbrock.__all__ drifted from the pinned surface. If deliberate, "
        "update CURRENT_TOP_LEVEL_SURFACE here AND document the change in "
        "CHANGELOG.md. Before 1.0 a removal is allowed (0.9.x may break); "
        "after 1.0 it is a MAJOR bump."
    )


def test_the_surface_does_not_grow():
    """The ratchet, and it outlives the cut. A surface reaches 95 by
    accretion one convenient symbol at a time, which is exactly how it got
    there the first time; nothing may push it upward now that it has been
    computed. A shrink still passes here — pin (1) catches it."""
    assert len(lidenbrock.__all__) <= len(CURRENT_TOP_LEVEL_SURFACE), (
        f"the top-level surface grew to {len(lidenbrock.__all__)} symbols. "
        "It reached 95 by accretion once already and S3b cut it back to a "
        "computed closure — a symbol that is in neither closure does not "
        "belong here. Export it from its own module instead."
    )


def test_every_public_symbol_resolves():
    for name in lidenbrock.__all__:
        obj = getattr(lidenbrock, name)  # raises AttributeError on breakage
        assert obj is not None, name


def test_lazy_map_is_subset_of_public_api():
    from lidenbrock import _LAZY

    unknown = set(_LAZY) - set(lidenbrock.__all__)
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
    assert _param_names(lidenbrock.CorrectionPipeline.run) == expected
    assert _param_names(lidenbrock.CorrectionPipeline.run_sync) == expected
    # §5.1 resorption — credentials must NEVER reappear on the run surface.
    for banned in ("api_key", "model", "provider_name"):
        assert banned not in expected


def test_for_provider_signature_is_pinned():
    params = _param_names(lidenbrock.CorrectionPipeline.for_provider)
    assert params[0] == "provider"
    for required in ("api_key", "model", "provider_name", "observer"):
        assert required in params
    # ADR-011 slice D-fin — persistence left the engine surface for good.
    assert "output_writer" not in params
    assert "output_writer" not in _param_names(lidenbrock.CorrectionPipeline.__init__)


def test_correction_report_json_keys_are_pinned():
    report = lidenbrock.CorrectionReport(run_id="r")
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
        "usage",  # optional, additive (no version bump)
        "sidecar",  # optional, additive (no version bump)
    }, (
        "CorrectionReport JSON shape moved — a key removal/rename requires "
        "bumping CORRECTION_REPORT_VERSION (§9); an addition must stay "
        "optional."
    )
    assert report.report_version == "2.0"
