"""Writing onto a line's trace, when there is one.

One helper, lifted out of the orchestrator (S2) because three modules now
need it and none of them should reach into the pipeline for it.
"""

from __future__ import annotations

from corrigenda.core.identity import LineRef, line_ref
from corrigenda.core.schemas import LineManifest, LineTrace


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
