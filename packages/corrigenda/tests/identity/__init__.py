"""Tests for the one rule the whole library is keyed on.

**Line identity is ``(page_id, line_id)``** — in the library, in the demo's
read models, in the frontend. `line_id` alone repeats across files, and
every consequence of forgetting that is silent: the wrong correction lands
on the wrong line, two lines collapse into one trace, a cross-page lookup
overwrites instead of missing.

Third directory organised by invariant rather than by the wave that found
the case (`RM-05b`, after `tests/decision/` and `tests/hyphenation/`).
Three questions, and two ADRs behind them:

  ``test_duplicate_ids``      a file whose ids are not unique is REFUSED
                              at the door, in both parsers and again in
                              ``run()`` (ADR-007)
  ``test_identity_refusal``   the cases the refusal nearly missed — a line
                              with no id at all, a duplicate hiding in a
                              margin or a nested region, and the repeat
                              that is LEGITIMATE because ids are
                              page-scoped
  ``test_line_ref``           one frozen key type, so a cross-page keying
                              mistake is a type error and not a runtime
                              overwrite (ADR-009)

Deliberately NOT gathered here, and the line is worth stating: reading
order and recursive traversal (``test_structure_traversal``) are about
which elements the parser VISITS, not about what names them. They share
fixtures with this directory, not an invariant.

No boundedness guard like `tests/hyphenation`'s, and for a measured
reason: `core.identity` is imported by a large part of the suite because
`line_ref` is how anything keys a line, so "imports the module" would name
half the tests instead of bounding anything.
"""
