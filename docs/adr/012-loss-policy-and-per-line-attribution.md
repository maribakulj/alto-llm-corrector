# ADR-012 — Loss policy: a format loss is a decision, and it is attributed per line

Status: accepted (2026-07)

## Context

Correcting a line can cost markup. The PAGE rewriter cannot keep a line's
`Word` children when the correction changes the word count: the 6.2 P4
slow path drops them and the text moves to line level. The line still
says the right thing; what is gone is the per-word geometry a viewer, a
re-OCR pass or an alignment tool would have used.

Two things were wrong with how that was handled.

**The loss was not a decision.** It happened inside the rewriter, after
the run had already decided the line was CORRECTED, and surfaced — when
it surfaced at all — as a counter on the finished report. A host that
would rather keep its word geometry than gain a corrected word had no
way to say so, and no way to find out afterwards which lines had paid.

**The loss was not attributable.** `format_losses` was one aggregate per
run. "This document lost 34 word boxes" does not tell anyone which 34
lines, so it cannot be reviewed, and a reader cannot distinguish a run
that damaged one heavily-corrected line from one that shaved a word off
thirty-four different lines. R1 found the same shape of defect on the
counters themselves; this is its decision-side twin.

The library's standing philosophy — the app decides, the model informs;
fall back to source on ambiguity — has no expression here at all: the
one predictable, decision-relevant loss in the engine was applied
unconditionally and reported as a number.

## Decision

**1. Word-granularity loss becomes a policy, `LossPolicy`, decided
BEFORE the decisions materialise.** `LineManifest.word_count` carries the
markup's word count from parse time, so the check runs in the pure core
against text, with no format module involved and no output in existence
yet. Three stances:

- **REPORT** (`strict=False`, the default, and the historical behaviour
  made explicit): the correction projects, the loss is counted and
  attributed.
- **STRICT** (`strict=True`): a correction that cannot project without
  losing word granularity is rejected. The line falls back to source
  text with a `format_loss` reason, the source markup keeps its
  geometry, and the rewrite sees an untouched line.
- **TOKEN_REALIGN** (`min_alignment_score` set, not strict): the middle
  ground. A word-count-changing correction projects only when its tokens
  align onto the source words confidently enough; a gated line reverts
  like strict, but its correction is preserved in the run's **sidecar**
  rather than discarded. `strict=True` wins over this gate.

**2. A rejection covers the whole hyphen unit** (ADR-010). Half a unit
reverted and half projected would leave a joined word rewritten on one
line and verbatim on the other; the reverts go through the same unit
closure every other fallback path uses.

**3. Losses are attributed per line, not only counted.** The rewrite
returns `losses_by_line` alongside the aggregate; it rides the line's
trace onto `ProjectionStage.losses` in the §9 report. Summing the values
reproduces `format_losses` — the aggregate is a view of the attribution,
not a separate measurement that could drift from it.

**4. The scope of `strict` is word granularity only.** Stale-annotation
drops — `conf`, alternative `TextEquiv`, offset-anchored `custom` groups
— describe the OLD reading of the line. They are inherent to *any*
correction, so refusing a correction on their account would refuse
correction itself. They stay report-only in every mode.

## Consequences

**`strict` is a no-op on ALTO, and the docstring says so outright** (R7).
`word_count` is populated by the PAGE parser alone: ALTO's per-token
`String` geometry redistributes at any token count, so there is no word
markup to lose and the gate has nothing to measure. A host that sets
`strict=True` on an ALTO document gets the default behaviour, silently —
which is why it is stated rather than left to be inferred.

**A host now has a real choice**, and the report tells it what the choice
cost either way: under REPORT, which lines paid; under STRICT, which
corrections were refused and why; under TOKEN_REALIGN, which are waiting
in the sidecar for review.

**The decision and the artefact cannot disagree.** Because the gate runs
before `derive_decision_set`, a rejected line is FALLBACK in the
DecisionSet *and* untouched in the XML. The earlier arrangement — losing
the markup during the rewrite, after the decision was recorded — is
exactly the shape that made `_verify_projection` raise on the engine's
own output when the PAGE rewriter forced a break character post-decision
(P5).

**`LossPolicy` joins the fingerprinted policies** (§8.2): two runs of the
same document under different stances are different runs, and the
corrected XML's `processingStep` says which one produced it.
