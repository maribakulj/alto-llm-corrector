# 2026-08-14 — BNL ground truth × `mistral-medium-2604`, five runs (`M2`)

**`M2` — the variance requirement — and the re-run `542c783` was owed.**
The 2026-07-25 campaign quoted a single decimal off two runs; the plan's
standing rule is *≥5 runs per configuration, publish a range, never an
isolated decimal*, and a permanent corollary of the lifted freeze says
**no quantified claim without `M2` + `M3`**. This is `M2`. `M3` (a second
model family) is still open — one provider is all this run had.

The headline is not the range. **The measured CER got worse, from
0.0252–0.0266 to 0.0338–0.0357.** Chasing that down is what the campaign
is actually worth: the cause is `542c783` making 24 more lines visible
as hyphen pairs, and most of the resulting reverts turn out to come from
an incoherence in this harness rather than from anything a real document
would hit. Both halves of that are below, with the counterfactual and
the trace that separate them.

## What produced these numbers

| | |
|---|---|
| corpus | `corpus/37-GT-BNL` — 37 pages, 522 lines, **human transcription** |
| input | **byte-identical to the July campaign** — its `ocr_spa_sidecar.json` was replayed, not re-OCRed |
| producer | `mistral-medium-2604`, `--provider mistral`, dated snapshot, still served |
| guards | `GuardConfig.vision()` (source-similarity floor 0.15) |
| code | `5407b08`, whose `src/` is identical to `main` (the two commits ahead of it touch only `tests/`) |
| cost | 5 × 86 producer calls, ~7 min per run |

Only two things differ from July: the library (`542c783` and everything
after it), and the model's own non-determinism. The input, corpus,
provider, model id and guard profile are the same.

## The range

| config | CER (5 runs) | median | spread | improved | degraded | false pos. |
|---|---|---|---|---|---|---|
| baseline (raw OCR) | 0.1038 | — | — | — | — | — |
| text (`default_french_ocr_rules`) | 0.1038 – 0.1038 | 0.1038 | 0.0 % | 0 | 0 | 0 |
| **vision** | **0.0338 – 0.0357** | 0.0349 | **5.6 %** | 328 – 337 | 9 – 10 | 2 |

Per run: 0.0357, 0.0349, 0.0338, 0.0343, 0.0353. `producer_calls` is 86
every time; `false_positives` is 2 every time.

**5.6 % spread confirms July's 6 %** — measured on five runs instead of
two, so the number is now a property of the setup rather than an
anecdote. Any comparison closer than ~6 % is noise on this corpus.

By language, using the repository's own classifier
(`extract_press19_corpus.language_of`):

| | n | baseline | after (5 runs) |
|---|---|---|---|
| French | 313 | 0.0503 | 0.0174 – 0.0191 |
| German (Fraktur) | 140 | 0.1852 | 0.0539 – 0.0576 |
| undecided | 69 | 0.1683 | 0.0630 – 0.0910 |

The undecided bucket carries most of the instability — a 44 % spread on
69 lines against 10 % on the 313 French ones. An aggregate hides that.

## Why the CER rose — and why the fix is still right

`542c783` taught the ALTO parser the whole word-break repertoire instead
of just `-`. It brought 24 previously-invisible `⸗` (U+2E17, the Fraktur
double oblique hyphen) break lines into pairing. The effect is exact:

- lines that end at their source text rose **141 → 165, i.e. +24**;
- of the 28 lines that revert now and did not in July, 16 carry a break
  sign and 14 have `⸗` in the reference;
- among the 34 `⸗` lines, reverts went **3 → 16**. The rest of the
  difference is partner propagation (ADR-010: a hyphen member whose
  partner fell back keeps its source text too).

The mechanism, traced by replaying July's accepted output as a cassette
through today's engine and reading `result.decisions`: **26 of the 31
reverts are `hyphen_pair_fallback`, and `orphan_hyphen_completed` never
fires at all.** It is not the acceptance guard — that one tests
`lm.ocr_text` — but `reconcile_hyphen_pair`, which requires the
CORRECTION of a PART1 to end on a break mark
(`core/hyphenation.py:335`) and reverts **both** members of the pair
when it does not. Before `542c783` these lines were not pairs, so the
reconciler was never called on them.

**The model erases `⸗` on 36 of 36 occurrences, in every run of both
campaigns** — it never once kept one. That part is solid and
harness-independent.

### …but most of these reverts are an artefact of this harness

Of the 15 PART1 lines reverting through the reconciler, only **4** have
an `ocr_text` that carries the break mark. The other **11** do not, and
that state is one the harness manufactures rather than one a run can
reach.

`vision_benchmark.py` parses the manifest from the **ground-truth ALTO**
— so hyphenation is detected on the human transcription, which carries
`⸗` — and only then overwrites every `ocr_text` with the Tesseract text,
which carries none (0 of 522 lines end in `⸗`; the GT has 24). All 94
PART1/BOTH lines here are heuristic, none explicit. Heuristic pairing is
derived FROM the trailing mark, so a real parser cannot produce a
heuristic PART1 whose `ocr_text` lacks one. This harness can, because it
rewrites the text after pairing.

So the pipeline is being handed GT-quality hyphenation markup with
OCR-quality text, and `542c783` made that incoherence reachable by
detecting 24 more marks in the GT half of it.

**The honest reading:** the CER movement between the two campaigns is
real and correctly measured, but it is mostly this harness, not a
production behaviour. The production-real slice — source carries the
mark, model erases it, pair reverts — is **4 lines**, not 24.

The measurement-validity defect is the most useful thing this campaign
found, and it applies to the July campaign too: **neither campaign's
number is trustworthy on hyphenated lines.** Fixing it means deriving
pairing from the text actually fed in, not from the reference.

The counterfactual closes the account. Re-score the run with the
reverted lines holding their July corrections instead:

| run | measured | counterfactual |
|---|---|---|
| 1 | 0.0357 | 0.0263 |
| 2 | 0.0349 | 0.0253 |
| 3 | 0.0338 | 0.0243 |
| 4 | 0.0343 | 0.0245 |
| 5 | 0.0353 | 0.0255 |

0.0243 – 0.0263 is July's range. **The entire movement is those ~30
lines and nothing else** — no other behaviour changed between the two
campaigns. Read together with the section above: ~11 of the 15 PART1
reverts behind it come from the harness's incoherent state, so most of
that 0.009 is a measurement defect rather than a cost the library
imposes on a real document.

## What this makes `M4` worth

`M4` is "recover the CER lost to two systematic normalisations". This
campaign does NOT price it at the 0.009 gap above — that gap is mostly
harness. What it does establish:

- the erasure itself is total and perfectly reproducible (36/36
  occurrences, ten runs across two campaigns), and it is a property of
  the model, not of the harness;
- when the source genuinely carries the mark, erasing it costs the whole
  pair: `reconcile_hyphen_pair` reverts both members. Here that is 4
  lines. On a corpus whose OCR reads `⸗` correctly it would be all of
  them.

Pricing `M4` needs a corpus where the input text and the hyphenation
markup come from the same place. That is a prerequisite this campaign
discovered, not a result it delivered.

Both substitutions re-measured here, five runs:

| | lines | occurrences | July |
|---|---|---|---|
| `⸗` U+2E17 erased | 34 / 34, every run | 36 / 36, every run | 34 / 34, 36 / 36 |
| `’` U+2019 → `'` | 50 – 58 / 127 | 64 – 74 / 161 | 54 / 127, 69 / 161 |

`⸗` is total and perfectly reproducible: the model never returns one.
`’` is partial and varies run to run — July's "all 69 occurrences" is the
right count but the wrong quantifier; it is 69 of 161.

Making the producer preserve `⸗` is still the right move — a corrector
that silently swaps a Fraktur break mark for a modern hyphen is altering
the document, which is the one thing this library promises not to do.
But its price on delivered quality is not measured yet, for the reason
above.

## Caveats

- **One model family.** `M3` is not satisfied by this run, so no
  quantified claim leaves this file yet.
- **The harness pairs on the reference, not on the input.** See the
  section above. Any per-line number on a hyphenated line, in this
  campaign or July's, inherits that defect.
- No cross-page hyphenation is exercised — no file ends mid-word and the
  harness parses each file as its own single-page document. `M1` remains
  the only way to measure that path.
- The input is deliberately bad OCR (Tesseract `--lang spa` on
  French/German). A lower bound, not an average.
- The German half is Fraktur against a French-oriented prompt.

## Reproducing

```bash
for i in 1 2 3 4 5; do
  python scripts/vision_benchmark.py --corpus corpus/37-GT-BNL \
    --ocr measurements/2026-07-25-bnl-mistral/ocr_spa_sidecar.json \
    --provider mistral --only text,vision \
    --out report-run$i.json --dump-lines lines-run$i.json
done
```

`MISTRAL_API_KEY` is read from the environment and never accepted as a
flag (`scripts/run_vision.py` says why). `--limit 5` smoke-tests the
wiring for about a minute before spending on the campaign.

## Files

- `report-run{1..5}.json` — the five run reports.
- `lines-run{1..5}.json` — every `(file, line_id, ocr, out, ref)` tuple,
  which is where the fallback account and both substitution counts come
  from. No re-run was needed for any finding on this page.
- The OCR sidecar is **not** duplicated here: it is the July campaign's,
  replayed unchanged, and that is the point.
