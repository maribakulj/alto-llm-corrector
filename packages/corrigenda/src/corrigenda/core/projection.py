"""The projection invariant: the artefact must SAY what the run decided.

Lifted out of the orchestrator (S2) because it is a pure comparison between
two texts and a DecisionSet — it needs no pipeline, no producer and no
observer, and reading it next to the retry loop hid that.
"""

from __future__ import annotations

from corrigenda.core.decisions import DecisionSet
from corrigenda.core.fidelity import ProjectionFidelity, classify_projection_fidelity
from collections.abc import Mapping

from corrigenda.core.identity import LineRef, line_ref
from corrigenda.core.schemas import LineTrace, PageManifest
from corrigenda.errors import ProjectionError


def _fidelity_counts(traces: Mapping[LineRef, LineTrace]) -> dict[str, int]:
    """Count the run's lines by the fidelity their projection reached.

    Keyed by the enum's string value so the report stays plain JSON.
    Lines whose file was never rewritten carry no level and are absent
    from the total — an empty dict means "nothing was written", never
    "everything was exact".
    """
    counts: dict[str, int] = {}
    for trace in traces.values():
        if trace.projection_fidelity is not None:
            key = trace.projection_fidelity.value
            counts[key] = counts.get(key, 0) + 1
    return counts


def _verify_projection(
    source_name: str,
    pages: list[PageManifest],
    output_texts: dict[str, str],
    decisions: DecisionSet,
    verbatim_texts: dict[str, str] | None = None,
) -> dict[str, ProjectionFidelity]:
    """The rewritten file must SAY what the run decided, line for line.

    Compares the rewrite's per-line texts against each line's terminal
    decision (ADR-011 — read from the immutable :class:`DecisionSet`,
    not the mutable manifests). A missing line, or one whose WORDS
    diverge, is corruption of the deliverable — the run fails here,
    before the writer can persist the artefact.

    A line whose words match but whose whitespace does not is NOT a
    failure: ``<SP>`` carries no content, so some of this is what the
    format costs. It is also not nothing — a no-break space flattened
    into an ordinary one changes what the line says to a typographer.
    Until now the comparison ran in whitespace normal form and could not
    tell those two apart, so both vanished. Returns the fidelity level
    reached per line id (see
    :class:`~corrigenda.core.fidelity.ProjectionFidelity`) so the caller
    can put it on the record instead.

    ``verbatim_texts`` (L8) is the same lines read with the format's own
    character substitutions off. A format that substitutes nothing passes
    ``None``; where it differs from ``output_texts`` the file spells a
    character its own way and the line grades ``source_spelling`` instead of
    ``exact`` — not a loss, but not "character for character" either, and
    the comparison against ``output_texts`` alone is structurally unable to
    notice, since both sides went through the same substitution.
    """
    levels: dict[str, ProjectionFidelity] = {}
    for page in pages:
        for lm in page.lines:
            decided = decisions.by_ref[line_ref(lm)].final_text
            extracted = output_texts.get(lm.line_id)
            if extracted is None:
                raise ProjectionError(
                    f"line {lm.line_id!r} (page {lm.page_id!r}) of "
                    f"{source_name!r} is missing from the rewritten XML"
                )
            level = classify_projection_fidelity(
                decided,
                extracted,
                (verbatim_texts or {}).get(lm.line_id),
            )
            if level is None:
                raise ProjectionError(
                    f"rewritten XML for {source_name!r} diverges from the "
                    f"run's decision on line {lm.line_id!r} (page "
                    f"{lm.page_id!r}): decided {decided!r} but the artefact "
                    f"contains {extracted!r}"
                )
            levels[lm.line_id] = level
    return levels
