# ADR-013 — When two passes revert the same line, the first reason is the true one

Status: accepted (2026-08)

## Context

A line that loses its correction carries one `fallback_reason`, and a
consumer reads it off `LineOutcome` or counts it in
`CorrectionResult.fallback_reasons`. Seven places in `core` write that
field, and they do not agree on what to do when it is already set:

| # | Site | Reason it writes | On an occupied trace |
|---|---|---|---|
| 1 | `acceptance._apply_line_acceptance` | `orphan_hyphen_completed` | assigns |
| 2 | `acceptance._apply_line_acceptance` | `hyphen_partner_fell_back` | assigns |
| 3 | `acceptance._apply_line_acceptance` | the guard's own (`too_different_from_source`, `closer_to_previous_line`, `closer_to_next_line`, `absorbs_next_line`, `absorbs_previous_line`) | assigns |
| 4 | `outcome._fall_back_to_source` | `all_attempts_exhausted: …` | assigns |
| 5 | `outcome._extend_to_units` | `hyphen_unit_fallback` | **defers** |
| 6 | `reconcile._refresh_pair_traces` | `hyphen_pair_{coherent\|fallback\|neutralised}` | **defers** |
| 7 | `acceptance._apply_unit_reverts` | the flagged line's own reason, or the caller's `atomicity_reason` | **defers** |

Four assign, three defer. Nothing states that split; it exists as the
shape of three `if not trace.fallback_reason` guards written at different
times, and it was described in the `RM` wave's opening audit as an
asymmetry to be resolved.

Sites 1–4 never collide in practice: they belong to one chunk's
acceptance path and each line goes through it once. The question is only
about 5–7, which run later, document-wide, and can land on a line another
pass already explained.

The `RM-01` audit note claimed this made
`CorrectionResult.fallback_reasons` count wrong — that a `token_realign`
gate could be reported as an `adjacent_duplicate`. **That claim was
checked and it is false.** What follows is what the check found.

## The invariant that decides it

> **I-1 — a line carrying a `fallback_reason` has already been reverted:
> its final text equals its source text.**

Verified, not assumed: an adversarial producer (duplicating neighbours,
absorbing across seams, dropping break marks, re-segmenting, and
answering far enough from source to be refused) was run over
`examples/X0000002.xml`, `examples/sample.xml`, the four PAGE fixtures
and `tests/corpus_gt/`, under the default loss policy, `token_realign`
and `strict` — 756 decided lines across six configurations, exercising
all eight reason families that appear in the wild. **Zero lines carried a
reason while holding a correction.**

It holds by construction, and the construction is worth naming because
`RM-01` must not break it. Every site that writes a reason has already
put the line back to its source text on the statement before, and
`guards.check_line` returns `text=source_ocr` on every one of its five
rejection branches — a rejected proposal never survives its own
rejection.

I-1 is what makes deferring correct rather than merely conservative. If
the line is already at source when the second pass arrives, that pass's
revert is **idempotent**: it changes no text, no status a reader would
notice, nothing. The pass that actually took the correction away is the
first one. Its reason is therefore not the stale one — it is the only
true one.

Last-writer-wins would name a pass that did nothing.

## Decision

**Keep the split. Deferring on sites 5–7 is correct, and sites 1–4 assign
because they cannot collide.**

Stated as the rule `RM-01` implements when it routes every write through
one entry point:

> **The reason belongs to the pass that first removed the correction.
> A later revert of an already-reverted line changes text and status
> idempotently and leaves the reason alone.**

Two consequences for the single writer:

- `fall_back(line, reason)` **must not** overwrite a non-empty
  `fallback_reason`. Today only three of the seven sites take that care;
  the single writer takes it always, which is a behaviour change on
  sites 1–4 that is invisible **because I-1 makes those sites
  unreachable twice**. `RM-01` must keep the invariant test green as the
  proof of that, not as a formality.
- The revert of text and status stays unconditional. Making it
  conditional too would be a real behaviour change: `_apply_unit_reverts`
  pulls unit members that may not be reverted yet, and that pull is the
  whole of ADR-010's fallback atomicity.

## What we are NOT deciding

**One line still reports one reason.** A line refused by the adjacency
guard and then also caught by the `token_realign` gate reports the first
only. That is information loss — a host cannot learn the line was
doubly suspect — but it is not a wrong count: each fallback is
attributed to the cause that produced it, exactly once, and the totals
in `CorrectionResult.fallback_reasons` sum to the number of fallen
lines.

Exposing the full set would mean a new field (`fallback_reasons:
list[str]` on `LineOutcome`), which is a public-API extension and is
suspended by the freeze in `docs/PLAN.md`. If a host ever asks, that is
the shape — not a change to this rule.

**`finalize._preserve_break_chars` is out of scope here.** It writes
`corrected_text` on an *accepted* line and writes no reason at all, so
the precedence rule does not reach it. Whether it belongs behind the
single writer is a separate question `RM-01` answers on its own terms.

## Consequences

- The precedence rule is a decision with a reason, citable as `ADR-013`,
  instead of a pattern to be re-derived from three `if` statements.
- `RM-01` inherits a target and an invariant rather than an open
  question: one writer, deferring, and I-1 green throughout the
  migration.
- `tests/decision/test_fallback_reason_precedence.py` pins all seven
  sites behaviourally and pins I-1 end-to-end over the corpora. A
  migration that changes which reason a consumer sees fails there first.
- The `RM` audit note that this "counts wrong" is retracted in
  `docs/PLAN.md`. The behaviour is correct; what was missing was the
  invariant that says so.
