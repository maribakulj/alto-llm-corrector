"""lidenbrock — structure-safe post-OCR correction of heritage transcriptions.

Sub-packages (§3 tree):

- :mod:`lidenbrock.core` — pure algorithms: schemas, guards, hyphenation
  reconciliation, chunk planning, response validation, the orchestrating
  :class:`CorrectionPipeline`, and every port (zero I/O, zero lxml —
  enforced by the import-contract test).
- :mod:`lidenbrock.formats` — concrete transcription formats. Today
  :mod:`lidenbrock.formats.alto` (hardened parser + 4-path rewriter);
  PAGE XML plugs in the same seam.
- :mod:`lidenbrock.producers` — edition-producer surfaces (the LLM
  system prompt + JSON output schema today).

Top-level re-exports give a single import surface. Format- and
producer-bound symbols are exposed LAZILY (PEP 562) so that importing
:mod:`lidenbrock` from a core-only consumer never loads lxml.
"""

from typing import TYPE_CHECKING, Any

from lidenbrock.core.decisions import (
    DecisionSet,
    LineDecision,
)
from lidenbrock.core.identity import LineRef
from lidenbrock.core.editing import (
    EDIT_PROTOCOL_VERSION,
    EditOp,
    EditScript,
    LinePrecondition,
    MatchAnchor,
    RangeAnchor,
    ReplaceLine,
    ReplaceSpan,
)
from lidenbrock.core.pipeline import (
    CorrectionPipeline,
    CorrectionResult,
    sanitize_error,
)
from lidenbrock.core.protocols import (
    EditProducer,
    PipelineObserver,
    ProducerMetadata,
    ProducerOptions,
)
from lidenbrock.core.fidelity import ProjectionFidelity
from lidenbrock.core.hyphenation import ReconcileMetrics
from lidenbrock.core.schemas import (
    BlockManifest,
    ChunkGranularity,
    ChunkPlannerConfig,
    Coords,
    CorrectionReport,
    CorrectionRequest,
    DecisionReason,
    DecisionStage,
    DocumentManifest,
    GuardConfig,
    HyphenRole,
    HyphenSplit,
    ImageAsset,
    ImageRef,
    ImageTransform,
    LineConfidence,
    LineContext,
    LineGeometry,
    LineManifest,
    LineOutcome,
    LineStatus,
    LineTrace,
    LossPolicy,
    PageImage,
    PageManifest,
    PairingPolicy,
    ProducerProvenance,
    ProjectionStage,
    ProposalFeatures,
    ProposalStage,
    RetryPolicy,
    RunProvenance,
    SidecarEntry,
    Usage,
)
from lidenbrock.errors import (
    CorrectionAborted,
    CorrectionError,
    LidenbrockError,
    DuplicateIdError,
    ParseError,
    ProposalValidationError,
    ValidationError,
)

if TYPE_CHECKING:  # typed view of the lazy symbols below
    from lidenbrock.facade import LoadedDocument as LoadedDocument
    from lidenbrock.facade import correct as correct
    from lidenbrock.facade import correct_sync as correct_sync
    from lidenbrock.facade import load as load

__version__ = "0.9.0"

# MAINTAINER NOTE — adding/removing a PUBLIC symbol touches THREE lists here,
# by design (the friction is a feature: a public API change should be
# deliberate, and ``tests/test_public_api_snapshot.py`` fails until all three
# agree):
#   1. either an eager ``from lidenbrock.core... import`` above (pure-core
#      symbols, no lxml) OR the ``_LAZY`` map below (format/producer symbols
#      that must stay lazy so ``import lidenbrock`` never loads lxml);
#   2. the ``TYPE_CHECKING`` block above, if the symbol is lazy (so mypy/IDEs
#      still see it);
#   3. ``__all__`` at the bottom.
#
#: Lazily resolved top-level names -> their home module (PEP 562). These
#: pull in lxml (formats) or producer surfaces, so they materialise only
#: on first attribute access — `import lidenbrock` alone stays pure.
_LAZY: dict[str, str] = {
    "LoadedDocument": "lidenbrock.facade",
    "correct": "lidenbrock.facade",
    "correct_sync": "lidenbrock.facade",
    "load": "lidenbrock.facade",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module 'lidenbrock' has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module_name), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


__all__ = [
    # ---------------------------------------------------------------
    # The façade (§2) — lazy, because `load` reaches a format.
    # ---------------------------------------------------------------
    "load",
    "correct",
    "correct_sync",
    "LoadedDocument",
    "__version__",
    # ---------------------------------------------------------------
    # What the façade RETURNS, transitively (V5). Computed, not chosen:
    # start from `load`/`correct`/`correct_sync`'s return annotations and
    # follow the types. A caller typing the value it was handed must be
    # able to import every name in it.
    # ---------------------------------------------------------------
    "CorrectionResult",
    "CorrectionReport",
    "DecisionSet",
    "LineDecision",
    "LineRef",
    "DocumentManifest",
    "PageManifest",
    "BlockManifest",
    "LineManifest",
    "Coords",
    "LineStatus",
    "HyphenRole",
    "HyphenSplit",
    "LineTrace",
    "Usage",
    "ReconcileMetrics",
    # Report v2 (§9) — the staged per-line outcome
    "LineOutcome",
    "ProposalStage",
    "ProposalFeatures",
    "DecisionStage",
    "DecisionReason",
    "ProjectionStage",
    "ProjectionFidelity",
    "LineConfidence",
    "SidecarEntry",
    # Provenance (§11)
    "ProducerProvenance",
    "RunProvenance",
    # The edit script the run applied (§4)
    "EditScript",
    "EditOp",
    "ReplaceLine",
    "ReplaceSpan",
    "MatchAnchor",
    "RangeAnchor",
    "LinePrecondition",
    "EDIT_PROTOCOL_VERSION",
    # ---------------------------------------------------------------
    # The producer seam. The README's first sentence promises "any
    # custom EditProducer", so what implementing one requires is
    # first-class here — protocol, payload, options, identity — and
    # closed the same way: everything the protocol's signatures name.
    # ---------------------------------------------------------------
    "EditProducer",
    "CorrectionRequest",
    "ProducerOptions",
    "ProducerMetadata",
    "LineContext",
    "LineGeometry",
    "ChunkGranularity",
    "ImageAsset",
    "ImageRef",
    "ImageTransform",
    "PageImage",
    # The engine you hand a producer to, and what it reports through.
    "CorrectionPipeline",
    "PipelineObserver",
    # ---------------------------------------------------------------
    # Injectable policies (§8.2). Frozen fields, fingerprinted.
    #
    # The five that shape EVERY run. `RM-04` demoted the two that shape
    # none by default — `ConfidencePolicy` (mode="drop") and
    # `RoutingPolicy` (both bounds None) belong to the research
    # programme the plan's freeze suspends, and a top-level export
    # advertises as ready something no default run executes. Both stay
    # importable from their own module (`core.schemas`, `core.quality`),
    # which is the demotion door `docs/versioning.md` documents.
    # ---------------------------------------------------------------
    "ChunkPlannerConfig",
    "RetryPolicy",
    "GuardConfig",
    "PairingPolicy",
    "LossPolicy",
    # ---------------------------------------------------------------
    # Errors (§8.4)
    # ---------------------------------------------------------------
    "LidenbrockError",
    "CorrectionError",
    "ParseError",
    "DuplicateIdError",
    "ProposalValidationError",
    "ValidationError",
    "CorrectionAborted",
    # ---------------------------------------------------------------
    # Kept deliberately: a security utility is made easy to find.
    # ---------------------------------------------------------------
    "sanitize_error",
]
