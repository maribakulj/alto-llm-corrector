# 2026-07-25 — BNL ground truth × `mistral-medium-2604` (vision)

**The first quality measurement in this project produced by a real model
against a human reference.** Every CER quoted in the repo before this run
came from an oracle producer — one handed the ground truth, which returns
it and ignores the pixels — so it measured the plumbing's floor, never a
model. Kept here because the run costs money and ten minutes, and because
several findings below were obtained by re-reading `lines.json`, not by
re-running anything.

## What produced these numbers

| | |
|---|---|
| corpus | `corpus/37-GT-BNL` — 37 pages, 522 lines, **human transcription** |
| input | real Tesseract, `--lang spa` on French/German text (deliberately wrong lexicon), via `scripts/ocr_corpus.py` |
| producer | **real VLM**, `mistral-medium-2604`, `--provider mistral` |
| guards | `GuardConfig.vision()` (source-similarity floor 0.15) |
| cost | 86 producer calls, ~5 min |

The corpus is **bilingual**: 26 pages / 373 lines French, 11 pages /
149 lines German in Fraktur. An aggregate CER averages two regimes that
differ threefold at the baseline, which is why `report.json` carries
`per_file`.

## Results

| config | CER | improved | degraded | unchanged | false positives |
|---|---|---|---|---|---|
| baseline (raw OCR) | 0.1038 | — | — | — | — |
| text (`default_french_ocr_rules`) | 0.1038 | 0 | 0 | 522 | 0 |
| **vision (real model)** | **0.0266** | 360 | 10 | 152 | 2 |

Per language: French 0.0624 → 0.0255 (−59.1%), German Fraktur
0.1842 → 0.0294 (−84.1%). The German half started three times worse and
the model recovered most of it, despite a French-oriented prompt.

**Run-to-run variance is real**: two identical runs gave 0.0252 and
0.0266, ~6% apart. Quote a range, never a single decimal.

For scale, the oracle scores 0.0021 on this corpus. The factor-12 gap
between it and a real model is what the oracle measurement could not show.

## What re-reading `lines.json` found

- The model erased the Fraktur double oblique hyphen **U+2E17 on 34 of the
  34 lines** carrying one, and replaced the typographic apostrophe
  **U+2019 on all 69 occurrences** with U+0027. Together these two
  systematic substitutions are **16.5% of all residual error** (576 → 481
  edit distance). Neither is visible to any guard: one character in forty
  does not move a similarity ratio.
- The 10 degraded lines cluster: 3 expanded leader dots in a table
  (`id.......` → `id. . . . . .`), 2 Fraktur (one illegible token deleted
  outright, one German paraphrase), 1 case normalisation
  (`GRECQUE,` → `Grecque,`).
- A digit-change detector flagged 56 lines. Almost all were **correct**
  fixes — the OCR had turned letters into digits (`3an` → `Jan`). That
  could only be determined against the ground truth. **In production there
  is none, and nothing in the text distinguishes a repaired digit from a
  falsified one.**

## Caveats

- No cross-page hyphenation is exercised: no file ends mid-word, and the
  harness parses each file as its own single-page document. The pipeline's
  cross-page path is **not measured by this run** (see the xfail in
  `packages/lidenbrock/tests/test_cross_page_hyphen_decision.py`).
- One model, one provider, one guard profile, two runs.
- The input is deliberately bad OCR — a hard case, closer to a lower
  bound than to an average.
- Produced BEFORE the ALTO word-break repertoire fix (`542c783`), which
  brought 24 previously-undetected `⸗` break lines into pairing. Re-run to
  see its effect.

## Reproducing

```bash
python scripts/ocr_corpus.py --corpus corpus/37-GT-BNL --lang spa --out ocr.json
python scripts/vision_benchmark.py --corpus corpus/37-GT-BNL --ocr ocr.json \
    --provider mistral --only text,vision --out report.json --dump-lines lines.json
```

Omit `--provider` for the offline oracle floor. `--limit N` smoke-tests the
wiring before spending.

## Files

- `report.json` — the run report (`producer` block names the real model,
  `per_file` breaks the CER down).
- `lines.json` — every `(file, line_id, ocr, output, reference)` tuple.
- `ocr_spa_sidecar.json` — the Tesseract input, so the run is reproducible
  without re-OCRing.
