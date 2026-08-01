"""What a run returns, and what a caller may do with it (ADR-011).

The engine never writes: it computes values and hands them back. This module
holds that value. Lifted out of the orchestrator (S2) because a result object
is not execution control — it is the shape of an answer, and a reader looking
for "what do I get back?" should not have to scroll past the retry loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from corrigenda.core.decisions import DecisionSet
from corrigenda.core.identity import LineRef
from corrigenda.core.editing import EditScript
from corrigenda.core.hyphenation import ReconcileMetrics
from corrigenda.core.schemas import CorrectionReport, LineTrace, Usage


@dataclass
class CorrectionResult:
    """Outcome of a full pipeline run.

    The input manifest is never mutated (ADR-011 slice E): what the run
    decided is read off ``decisions`` (and ``corrected_files`` for the
    artefacts). `traces` is the line-by-line text trace through every
    stage.
    """

    total_chunks: int
    total_reconciled: int
    retry_count: int
    #: Number of chunks whose producer attempts were exhausted (an
    #: orchestration counter — one rejected 20-line chunk counts once).
    fallback_chunks: int
    #: Number of LINES whose terminal status is ``FALLBACK`` — they kept
    #: their OCR source text, whether a whole chunk fell back, a guard
    #: rejected the correction, or a duplicate revert undid it. Manifest
    #: statuses are the authority; "completed with fallbacks" means
    #: exactly ``fallback_lines > 0``.
    fallback_lines: int
    #: Aggregated ``fallback_reason`` prefixes → line counts for the
    #: fallen lines (e.g. ``{"all_attempts_exhausted": 20}``), so a
    #: consumer can say WHY without parsing messages.
    fallback_reasons: dict[str, int]
    traces: dict[LineRef, LineTrace]
    reconcile_metrics: ReconcileMetrics
    #: F14 — aggregate token consumption across every producer call in the
    #: run (zero when no provider reported usage).
    usage: Usage
    #: §9 — public, versioned correction report (same line traces, promoted
    #: to a documented artefact). Present on every run, including dry runs.
    report: CorrectionReport
    #: §4 — the normalized EditScript the run applied, accumulated across
    #: chunks. In v1 the LLM path emits ``replace_line`` ops (byte-identical
    #: to the direct correction); a rules/​span producer surfaces its
    #: ``replace_span`` ops here too.
    edit_script: EditScript
    #: ADR-011 — the run's immutable :class:`DecisionSet`: one terminal
    #: decision per line in document reading order. Since slice E the
    #: input manifest is never mutated, so THIS is where a caller reads
    #: what the run decided (``decisions.by_ref[LineRef(...)]``).
    decisions: DecisionSet
    #: ADR-011 — the corrected artefacts themselves, keyed by source file
    #: name, computed on EVERY run: the result IS the output; persisting
    #: it is the caller's choice (:meth:`write`, or a host-owned
    #: transaction like the demo backend's staging writer).
    corrected_files: dict[str, bytes] = field(default_factory=dict)
    #: lines the QE router judged already clean and SKIPPED
    #: (confirmed as-is, no producer call). 0 when routing is off. The
    #: economics signal: each skip is one LLM call not spent.
    lines_skipped: int = 0
    #: non-hyphen lines the QE router sent to ESCALATE and that
    #: were routed to the ``escalation_producer`` (a VLM) instead of the
    #: primary producer. 0 when no escalation producer is set. Each one is
    #: a line the hybrid judged worth the heavier (vision) call.
    escalated_lines: int = 0
    #: total ``producer.produce`` invocations (retries included):
    #: the run's real call cost. Falls when routing drops whole chunks —
    #: routing-on vs routing-off on one document is the cheaper-hybrid proof.
    producer_calls: int = 0

    def write(self, directory: str | Path) -> list[Path]:
        """Persist the run's artefacts into ``directory`` (created if
        needed): each corrected XML under its source file's name, plus
        the §9 report as ``report.json``. Returns the written paths.

        ADR-011 — a caller-side convenience, not engine behaviour: the
        engine only computes values. Hosts that own a file transaction
        (commit/discard staging) keep their injected writer instead.
        """
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for source_name, xml_bytes in self.corrected_files.items():
            # Strip any directory part: the key names a source FILE and
            # must not steer the write outside ``directory``.
            path = target / Path(source_name).name
            path.write_bytes(xml_bytes)
            written.append(path)
        report_path = target / "report.json"
        report_path.write_text(self.report.model_dump_json(indent=2), encoding="utf-8")
        written.append(report_path)
        # refused-but-preserved corrections as their own small
        # artefact for review tooling (they are ALSO inside report.json;
        # this is the convenience view, written only when non-empty).
        if self.report.sidecar:
            sidecar_path = target / "sidecar.json"
            sidecar_path.write_text(
                json.dumps(
                    [entry.model_dump(mode="json") for entry in self.report.sidecar],
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            written.append(sidecar_path)
        return written
