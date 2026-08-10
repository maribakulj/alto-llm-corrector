"""What one page's correction can SEE (`RM-03`).

Three indices travelled the whole chunk path by hand — ``line_by_id``
(this page's lines by bare id), ``cross_page_partners`` (the hyphen
members this page needs from other pages, page-qualified) and ``traces``
(the run's per-line audit records). They appeared together in nine
signatures from :meth:`PageDriver.process_page` down to
``outcome._extend_to_units``, and were counted 24, 38 and 35 times across
the source.

That is not three arguments, it is one thing spelled three times. The
orchestrator split turned what used to be ``self.line_by_id``
into a parameter, which was right in intent and produced
``_descend_granularity`` at twelve arguments. `RM-02` made that visible
by measuring arity next to length; this is the item that acts on it.

**Read-only by construction, and the limit of that claim is worth
stating.** The dataclass is frozen, so a field cannot be rebound, and it
exposes no method that writes anything. The dicts it holds are the run's
LIVE indices, not copies — ``traces`` is written by
:mod:`corrigenda.core.decide` and the manifests in ``line_by_id`` are the
working state a run mutates. Handing them around in one object does not
make them immutable and this module does not pretend otherwise. What it
does is stop the three from being separable: a caller cannot now be given
``line_by_id`` without ``traces``, or be handed a workspace from another
page.

**It is not a bag.** `ADR-011` spent a slice removing per-run mutable
state from the engine, and a workspace that grew a counter, a metric or a
cache would put it straight back. The rule is narrow and mechanical:
this holds INDICES a page's work reads, nothing a run accumulates. Run
state is :class:`~corrigenda.core.context.RunContext` and stays there —
``tests/test_page_workspace_is_not_a_bag.py`` fails if this class grows a
field that is neither of the three, so the next person to reach for it
has to make that argument out loud.
"""

from __future__ import annotations

from dataclasses import dataclass

from corrigenda.core.identity import LineRef
from corrigenda.core.schemas import LineManifest, LineTrace


@dataclass(frozen=True)
class PageWorkspace:
    """The indices one page's correction reads, travelling together."""

    #: This page's lines, by bare ``line_id``. Page-scoped: bare ids are
    #: unique within a file, never document-wide (ADR-007), which is why
    #: the next field is keyed differently.
    line_by_id: dict[str, LineManifest]

    #: Hyphen members this page needs from OTHER pages, page-qualified
    #: (ADR-009). ``None`` when the page has no cross-page unit — the
    #: distinction between "none needed" and "an empty map" is what the
    #: lookup helpers read, so it is preserved rather than normalised.
    cross_page_partners: dict[LineRef, LineManifest] | None

    #: The run's per-line audit records, document-wide. ``None`` when the
    #: host opted out of tracing; every writer already no-ops on that.
    traces: dict[LineRef, LineTrace] | None


__all__ = ["PageWorkspace"]
