"""Writing onto a line's trace, when there is one.

Lifted out of the orchestrator because several modules now need this
and none of them should reach into the pipeline for it.
"""

from __future__ import annotations

from lidenbrock.core.identity import LineRef, line_ref
from lidenbrock.core.schemas import LineManifest, LineTrace


def _set_trace(
    traces: dict[LineRef, LineTrace] | None,
    lm: LineManifest,
    **fields: object,
) -> None:
    """Assign trace fields on the LineTrace keyed by ``lm``, if tracked.

    Centralises the ``if traces is not None: t = traces.get(...);
    if t is not None: ...`` pattern that was repeated five times in
    ``_run_chunk`` and its helpers. A trace dict that isn't tracking
    a given line silently no-ops.
    """
    if traces is None:
        return
    trace = traces.get(line_ref(lm))
    if trace is None:
        return
    for name, value in fields.items():
        setattr(trace, name, value)


def _finalize_chunk_traces(
    *,
    chunk_lines: list[LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """Project a chunk's post-acceptance state onto the traces (when the
    host opted in by passing a non-None ``traces`` dict).

    Duplicate detection is not chunk business anymore: the single
    document-wide adjacency pass runs after the page loop, so the
    state projected here is provisional until that pass ran.
    """
    for lm in chunk_lines:
        _set_trace(
            traces,
            lm,
            projected_text=(
                lm.corrected_text if lm.corrected_text is not None else lm.ocr_text
            ),
            validation_status=lm.status.value,
        )
