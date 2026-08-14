# 2026-08-14 — BNL ground truth × `mistral-medium-2604`, five runs (`M2`)

**`M2` — the variance requirement — and the re-run `542c783` was owed.**
The 2026-07-25 campaign quoted a single decimal off two runs; the plan's
standing rule is *≥5 runs per configuration, publish a range, never an
isolated decimal*, and a permanent corollary of the lifted freeze says
**no quantified claim without `M2` + `M3`**. This is `M2`. `M3` (a second
model family) is still open — one provider is all this run had.

The headline is not the range. **The measured CER got worse, from
0.0252–0.0266 to 0.0338–0.0357, and the cause is a correctness fix
working as designed.** That account is below, with the counterfactual
that closes it.

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

The mechanism is one guard doing its job. **The model erases `⸗` on
36 of 36 occurrences, in every run of both campaigns** — it never once
kept one. In July those lines were not paired, so the erasure was
accepted and shipped: the model returned `entgegen-`, substituting a
plain hyphen for the break mark, and nothing objected. Now they are
paired, `orphan_hyphen_completed` fires — a PART1 whose source ends on a
break mark and whose correction does not — and the line reverts to raw
OCR. Raw Fraktur OCR is very bad (`nad) bie Dinberniffe` for
`nach die Hindernisse`), so reverting is expensive in CER.

So the library became **more conservative and structurally more correct,
at a measurable cost on this corpus.** The July number was partly bought
with silent break-mark destruction.

The counterfactual closes the account. Re-score the run with the
reverted lines holding their July corrections instead:

| run | measured | counterfactual |
|---|---|---|
| 1 | 0.0357 | 0.0263 |
| 2 | 0.0349 | 0.0253 |
| 3 | 0.0338 | 0.0243 |
| 4 | 0.0343 | 0.0245 |
| 5 | 0.0353 | 0.0255 |

0.0243 – 0.0263 is July's range. **The entire regression is those ~30
lines and nothing else** — no other behaviour moved between the two
campaigns.

## What this makes `M4` worth

`M4` is "recover the CER lost to two systematic normalisations". It now
has a price on this corpus: **~0.009 CER absolute, ~27 % relative**, and
it is the whole gap between the two campaigns.

Both substitutions re-measured here, five runs:

| | lines | occurrences | July |
|---|---|---|---|
| `⸗` U+2E17 erased | 34 / 34, every run | 36 / 36, every run | 34 / 34, 36 / 36 |
| `’` U+2019 → `'` | 50 – 58 / 127 | 64 – 74 / 161 | 54 / 127, 69 / 161 |

`⸗` is total and perfectly reproducible: the model never returns one.
`’` is partial and varies run to run — July's "all 69 occurrences" is the
right count but the wrong quantifier; it is 69 of 161.

Making the producer preserve `⸗` is worth more than the CER: it is 24
lines that currently cannot be corrected at all, because the guard
correctly refuses every correction that drops the mark.

## Caveats

- **One model family.** `M3` is not satisfied by this run, so no
  quantified claim leaves this file yet.
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
