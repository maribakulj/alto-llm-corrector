"""Ce qu'une page devient une fois découpée pour un producteur.

Une requête de chunk, le plan qui les porte, et le lien de césure que le
planificateur a dû sectionner pour tenir dans ses bornes. Trois modèles de
données, aucune politique.

Ils vivaient dans ``policies.py``, qui déclarait dans son propre nom ne
porter que des politiques injectables et gelées. Un `ChunkRequest` n'est pas
une politique : il est ce qu'une politique — `ChunkPlannerConfig` — produit.
Quatre des onze classes de ce fichier n'étaient pas ce que son nom
annonçait ; les trois qui restent ici et `RefusedEdit`, parti vers
``report.py``, sont ces quatre-là.

Aucun site d'import ne change : ``core/schemas/__init__.py`` réexporte tout.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saknussemm.core.schemas.manifest import ChunkGranularity


class ChunkRequest(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    page_id: str
    block_id: str | None = None
    granularity: ChunkGranularity
    line_ids: list[str]
    # Target lines the pipeline actually corrects/accepts. Any line in
    # ``line_ids`` but NOT in ``target_line_ids`` is *context only*: it is
    # still sent to the producer so a target near it keeps full surrounding
    # context, but its output is discarded here (it is a target of an
    # adjacent chunk). ``None`` means every line is a target (PAGE / BLOCK /
    # LINE granularity, and the historical default for windows).
    target_line_ids: list[str] | None = None

    def targets(self) -> list[str]:
        """The line_ids this chunk owns (all of them when unrestricted)."""
        return self.line_ids if self.target_line_ids is None else self.target_line_ids

    attempt: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _targets_subset_of_lines(self) -> "ChunkRequest":
        """A target outside the chunk's lines would be silently
        ignored at correction time (it has no enriched input) while still
        counting as "owned" — a line lost without a trace."""
        if self.target_line_ids is not None:
            extra = set(self.target_line_ids) - set(self.line_ids)
            if extra:
                raise ValueError(
                    f"target_line_ids not contained in line_ids: {sorted(extra)!r}"
                )
        return self


class HyphenSplit(BaseModel):
    """Record of a severed forward hyphen link (ADR-010 unit SPLIT).

    Emitted by :func:`saknussemm.core.units.split_forward_link` when the
    LINE planner cuts a chain longer than ``max_lines_per_request``, and
    carried on the :class:`ChunkPlan` so the cut is a recorded unit
    operation rather than a silent pointer side effect. Line ids are
    bare on purpose: the chain walk is page-scoped, so a split never
    crosses a page, and ``page_id`` qualifies both (ADR-009).
    """

    model_config = ConfigDict(frozen=True)

    page_id: str
    tail_line_id: str
    head_line_id: str


class ChunkPlan(BaseModel):
    page_id: str
    chunks: list[ChunkRequest]
    granularity: ChunkGranularity
    #: ADR-010 — the forward links the LINE planner severed so that no
    #: still-linked pair spans two chunks (over-cap chains). Empty at
    #: every other granularity.
    hyphen_splits: list[HyphenSplit] = Field(default_factory=list)


__all__ = ["ChunkPlan", "ChunkRequest", "HyphenSplit"]
