# Reading a run's report honestly

A `CorrectionReport` carries several numbers. Each answers a narrow question,
and the danger is not that any of them lies — it is that a reader takes one
for a broader claim than it makes. This page says, for each, what it means and
what it does **not**.

Written for the institutional case: someone deciding whether a corrected file
can be ingested, who needs to know what the run could not see.

## The one that misleads most: `fallback_lines == 0`

**Means:** no proposal was refused by the guards.

**Does not mean:** nothing was altered. It is close to the opposite — every
line the producer touched was *accepted*. A run where the model rewrote half
the document and the guards found nothing objectionable reports `0`.

To ask "what changed?", read the per-line outcomes: `decision.final_text`
against the source, or `projection.rewriter_path` (`untouched` is the only
value that means the line's markup was not rewritten at all).

## `format_losses is None`

**Means:** no markup was dropped — no element or attribute left the tree.

**Does not mean:** nothing was lost. A character the format cannot carry — a
no-break space, U+202F, a tab flattened to an ordinary space — is a loss of
TEXT, and it is counted on the fidelity scale instead. A run can report
`format_losses: None` and `projection_fidelity: {"normalized": 2}` at the same
time, and those two lines really did lose something a typographer would see.

Both fields have to be read. They are deliberately not mirrored into one
counter: two accounting sites for one event drift apart, which is a defect
this library has already had once.

## `projection_fidelity`

Per-line grades, counted over the run, best to worst:

| level | what it says |
|---|---|
| `exact` | the artefact says the decision, character for character |
| `source_spelling` | same words and same break, but the file spells a character its own way (a `<HYP>` holding U+00AD read back as `-`). **Nothing is lost** — the file is *more* specific than the decision |
| `token_equivalent` | same words, and every significant whitespace survived; only runs collapsed or edges were trimmed. This is what the format costs |
| `normalized` | a significant whitespace character was **replaced**. The line reads the same to a machine that splits on whitespace, and no longer reads the same to a typographer |

**Does not mean:** that the text is *right*. This scale compares the delivered
file against what the run DECIDED. A wrong decision faithfully written is
`exact`.

## `unpaired_breaks`

**Means:** N lines end mid-word with no partner this run could see — the
pairing policy refused the candidate, the partner is on a page this run does
not have, or the pointer dangles.

**Does not mean** the count is a defect count. A page whose last line ends in
a hyphen legitimately contributes 1. What it does mean is that those lines were
corrected **alone**, so their pair-drift guards never ran: they carry less
scrutiny than a paired line, not more error.

## `hyphen_splits`

**Means:** the planner **severed** a hyphen link to keep a chain inside one
request. Both sides keep their OCR text verbatim.

**Does not mean** a failure. It means a delivered line whose text still ends
mid-word and which now declares no break at all. Nothing else on the report
says this: it is not a fallback, not an unpaired break, and not a format loss.

Rare — it requires an over-cap chain *and* a chunk that failed its retries,
since the granularity descent is the only path that reaches LINE planning.

## `confidence_invalidated`

**Means:** N **lines** lost their OCR confidence: the source engine's `WC`/`CC`
(ALTO) or `@conf` (PAGE) were removed because a correction made them untrue.

**Does not mean** N attributes. The unit is the line, deliberately — per
occurrence it reaches four digits on a single page and tracks how wordy a line
is rather than anything you would act on.

## `word_order_suspected` (per line)

**Means:** the token alignment could not vouch for the word order it was
handed.

**Does not mean** a loss, and it is not counted as one. Nothing left the
markup; the correction is written exactly as decided, because lines never merge
and words never move. It is a flag for a human, never acted on.

## What no number on this report tells you

- **Whether the corrections are right.** Every guard in this library is
  structural: it refuses text that migrated between lines, words that grew past
  a threshold, a break mark that vanished. None of them knows French, or
  history, or your edition's conventions. A plausible, fluent, wrong reading
  passes every one.
- **Whether the guards are calibrated.** They are not, and the code says so —
  `GuardConfig`'s thresholds are safe defaults, not measured ones. They have
  been exercised on two corpora and one model family.
- **Whether the source OCR was any good.** `ocr_confidence` is preserved per
  line where the source carried it, and it is the *engine's* opinion of its own
  work.

## The short version

`0 fallback` means **no proposal was refused**. It does not mean nothing
changed, and it does not mean what changed was right. To audit a run you need
`projection_fidelity` and `format_losses` together, plus `unpaired_breaks` and
`hyphen_splits` for the lines that were corrected with less than the full set
of guards behind them.
