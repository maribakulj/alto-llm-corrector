"""Every type the engine passes around, in four families.

This was one 1 538-line module with 44 importers, which is why it is a
package and not four modules: **everything is re-exported here**, so
``from saknussemm.core.schemas import X`` keeps working for every X it
ever named, and the split cost no importer a line.

  :mod:`~saknussemm.core.schemas.manifest`   the parsed document
  :mod:`~saknussemm.core.schemas.policies`   what a consumer injects (§8.2)
  :mod:`~saknussemm.core.schemas.producer`   the producer payloads (§5.1)
  :mod:`~saknussemm.core.schemas.report`     what the run says it did (§9)

The four are strictly layered — ``manifest`` ← ``policies``/``producer`` ←
``report`` — and nothing in them imports the engine. New types join the
family they belong to; the re-export here is not optional, it is what the
importers depend on.

``__all__`` is the surface as it was before the split, to the name.
"""

from __future__ import annotations

from saknussemm.core.fidelity import ProjectionFidelity as ProjectionFidelity

from saknussemm.core.schemas.manifest import (
    BlockManifest as BlockManifest,
    ChunkGranularity as ChunkGranularity,
    Coords as Coords,
    DocumentManifest as DocumentManifest,
    HyphenRole as HyphenRole,
    LineManifest as LineManifest,
    LineStatus as LineStatus,
    PageManifest as PageManifest,
    PipelineEventType as PipelineEventType,
)

from saknussemm.core.schemas.policies import (
    ChunkPlan as ChunkPlan,
    ChunkPlannerConfig as ChunkPlannerConfig,
    ChunkRequest as ChunkRequest,
    ConfidencePolicy as ConfidencePolicy,
    DEFAULT_CONFIDENCE_POLICY as DEFAULT_CONFIDENCE_POLICY,
    DEFAULT_GUARD_CONFIG as DEFAULT_GUARD_CONFIG,
    DEFAULT_LOSS_POLICY as DEFAULT_LOSS_POLICY,
    DEFAULT_PAIRING_POLICY as DEFAULT_PAIRING_POLICY,
    DEFAULT_RETRY_POLICY as DEFAULT_RETRY_POLICY,
    FrozenPolicy as FrozenPolicy,
    GuardConfig as GuardConfig,
    HyphenSplit as HyphenSplit,
    LossPolicy as LossPolicy,
    PairingPolicy as PairingPolicy,
    RetryPolicy as RetryPolicy,
)

from saknussemm.core.schemas.producer import (
    CorrectionRequest as CorrectionRequest,
    ImageAsset as ImageAsset,
    ImageRef as ImageRef,
    ImageTransform as ImageTransform,
    LineContext as LineContext,
    LineGeometry as LineGeometry,
    LineProposal as LineProposal,
    ModelCapabilities as ModelCapabilities,
    ModelInfo as ModelInfo,
    PageImage as PageImage,
    ProposalBatch as ProposalBatch,
    Usage as Usage,
)

from saknussemm.core.schemas.report import (
    CORRECTION_REPORT_VERSION as CORRECTION_REPORT_VERSION,
    CorrectionReport as CorrectionReport,
    DecisionReason as DecisionReason,
    DecisionStage as DecisionStage,
    LineConfidence as LineConfidence,
    LineOutcome as LineOutcome,
    LineTrace as LineTrace,
    ProducerProvenance as ProducerProvenance,
    ProjectionStage as ProjectionStage,
    ProposalFeatures as ProposalFeatures,
    ProposalStage as ProposalStage,
    RunProvenance as RunProvenance,
    SidecarEntry as SidecarEntry,
)

# --- public surface ---
__all__ = [
    "LineStatus",
    "ChunkGranularity",
    "HyphenRole",
    "PipelineEventType",
    "Coords",
    "LineManifest",
    "BlockManifest",
    "PageManifest",
    "DocumentManifest",
    "ChunkPlannerConfig",
    "FrozenPolicy",
    "GuardConfig",
    "ConfidencePolicy",
    "LineConfidence",
    "LossPolicy",
    "PairingPolicy",
    "RetryPolicy",
    "ChunkRequest",
    "ChunkPlan",
    "ImageRef",
    "LineGeometry",
    "LineContext",
    "CorrectionRequest",
    "LineProposal",
    "ProposalBatch",
    "ModelInfo",
    "Usage",
    "LineTrace",
    "LineOutcome",
    "ProposalStage",
    "ProposalFeatures",
    "DecisionStage",
    "DecisionReason",
    "ProjectionFidelity",
    "ProjectionStage",
    "ProducerProvenance",
    "RunProvenance",
    "SidecarEntry",
    "CorrectionReport",
]
