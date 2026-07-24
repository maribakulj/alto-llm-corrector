# Ground-truth corpus (P4.1/P4.2)

Reference transcriptions the benchmark (`scripts/benchmark.py`) measures
against. Every case pairs a **source** file (what OCR produced) with a
**reference** file (what the text should read), same format, same line
IDs.

## Provenance rules

- **Real ground truth** requires a *human-reviewed* reference
  transcription (P4.1: 10–20 stratified Gallica pages — ALTO + PAGE,
  book + press, explicit/heuristic/cross-page/chained hyphenation,
  early and modern French). That cost is human and deliberate: never
  commit a machine-generated file as "reference".
- **Synthetic cases** (name prefixed `synthetic-`) bootstrap the
  benchmark before the human corpus lands: the reference is written for
  this corpus, and the source is derived from it by *scripted,
  documented degradations*. They validate the measurement pipeline;
  they do not validate the library against real OCR.

## Current cases

- `synthetic-fr-early-print` — 6 lines of early-modern-flavoured
  French, one heuristic hyphen pair (`trou-` / `blât …`). Degradations
  applied to derive the source from the reference: non-final `s` → `ſ`
  (long s), `fi` → `ﬁ` (ligature) — both fixable by
  `default_french_ocr_rules()` — plus one `m` → `rn` confusion
  (`moindre` → `rnoindre`) that the default rules deliberately cannot
  fix without a lexicon, so the rules producer keeps a measurable
  residual CER and the oracle producer erases it.
- `ocr17-descartes-discours-p14` / `ocr17-lafayette-cleves-p11`
  (**real**, PAGE, ROADMAP V3 Phase 2) — genuine Transkribus OCR of two
  17th-century French prose pages vs the upstream HUMAN-corrected
  reference, from **OCR17+** (Simon Gabay et al., e-ditiones —
  **CC-BY**, attribution kept here and in
  `examples/page/PROVENANCE.md`). Upstream artifact handled by
  `derive_ocr17.py` (committed outputs, offline suite): the raw
  export's line-level `TextEquiv` already carries the corrected
  reading, so the derivation re-exposes the real OCR (`cukiuent`,
  `eft`…) from the `Word` elements at line level — deterministic
  re-exposure of upstream data, nothing machine-generated. The
  references are the upstream human corrections, satisfying the
  provenance rule above.

  Registered in `manifest.json` since corpus_version 0.2.0 — and the
  registration itself was the acceptance test of a real bug these pages
  exposed on their very first oracle run (2026-07-23): the PAGE
  rewriter's P5 pass forced the SOURCE break character (`-`) onto the
  corrected text (`¬`) AFTER the decision had been recorded, so the
  artefact diverged from the decision and `_verify_projection` raised
  `ProjectionError`. P5 now runs decision-side in the pipeline
  (`preserve_break_char`, `core/pairing.py`) — decision == artefact,
  always. Honest baselines measured here: `default_french_ocr_rules()`
  corrects NOTHING on this real OCR (CER 0.069→0.069 / 0.133→0.133,
  zero false positives), and even the ORACLE plateaus at CER 0.057 on
  the hyphen-dense Descartes page (the guards arbitrate its proposals)
  — the guard-calibration ceiling Phase 2 exists to study.

## Vision corpus (ROADMAP V3 Phase 4)

The vision benchmark (`scripts/vision_benchmark.py`) needs something this
directory deliberately does NOT hold: **paired page images**. It therefore
takes a corpus directory as an argument instead of committing scans (a few
hundred MB of PNG has no place in the repo).

Validated against the **BNL ground truth** (Bibliothèque nationale du
Luxembourg, 19th-c. French press): 37 paired `NNNN.xml` (ALTO v4) +
`NNNN.png`, 522 lines. Two properties make it a good fit, both verified
on the data:

- the ALTO declares `MeasurementUnit mm10`, so XML coordinates are NOT
  pixels — exactly what `ImageAsset.transform` exists for. The scans are
  300 DPI, so the mapping is the uniform scale `dpi / 254` ≈ **1.1811**
  (`px = mm10 × dpi / 254`), confirmed by cropping lines and reading them
  back;
- the ALTO `CONTENT` is the human GT (`CC="00"`), i.e. the **reference**,
  not raw OCR — so the INPUT side has to come from somewhere.

### Real OCR instead of scripted degradation

`scripts/ocr_corpus.py` closes that gap: it runs a real OCR engine
(Tesseract) over the corpus's own line images and pairs each reading with
its GT line. The pairing is exact by construction — instead of OCR-ing the
page and aligning two different segmentations, it OCRs **one crop per GT
line**, cut with the library's own `crop_region` from the GT geometry
(`--psm 7`). Every reading belongs to a known `(file, line_id)`.

Two quality tiers, both genuine engine output:

- `--lang fra` — correct engine on French: **CER 0.102**, 121/522 lines
  exact;
- `--lang spa` — a deliberately WRONG language model on French text:
  **CER 0.105**, only 78/522 exact. Still a real engine making real
  decisions with the wrong lexicon, so it degrades the way bad OCR
  degrades (`l'entente` → `Ventente`, `qu'il` → `Qw'il`), not the way a
  substitution table does.

Real OCR fails in ways no substitution table reproduces: merged words
(`On me` → `Oume`), invented characters (`aujourd'hui` → `aujourd'hut`),
apostrophe drift (`’`/`'`), hallucinated leading glyphs. With this
sidecar, **nothing in the measurement is synthetic**: real scans, real OCR
errors, human reference.

### Measured (37 pages / 522 lines, real tesseract/fra input, oracle VLM)

| config | CER | producer calls | escalated |
|---|---|---|---|
| baseline (raw OCR) | 0.1018 | — | — |
| text (`default_french_ocr_rules`) | 0.1018 | 37 | 0 |
| vision (every line) | 0.0021 | 37 | 0 |
| hybrid (QE-routed) | **0.0021** | 58 | 421 |

Three honest readings of that table:

- the **rules producer corrects nothing** on this material (CER
  unchanged, zero false positives) — consistent with the OCR17+ finding
  above. Its table targets early-modern typography (long-s, ligatures);
  19th-c. press OCR fails differently. The rules are a safe no-op here,
  not a fix.
- the hybrid now **matches vision exactly** (0.0021). It did not at first:
  escalation refused hyphen units wholesale, leaving them to the
  ineffective text producer, and that was the hybrid's *entire* residual
  error — predicted from those lines' own raw-OCR CER at 0.0079, measured
  at 0.0083. The fix was to escalate a hyphen unit **as a unit** (both
  members to one producer), which preserves atomicity — the pair still
  reaches one producer in one call and reconciles normally — while
  removing the residual. A measurement that found a real design bug.
- **the hybrid is not cheaper here, and that is expected.** It makes MORE
  calls than all-vision (58 vs 37) because splitting a chunk into
  primary/escalation siblings costs an extra call, while still sending
  421/522 lines to the expensive model. With OCR this poor (only 121/522
  lines are already correct) most lines genuinely need the good model, so
  there is little to save. The hybrid pays off on *mostly clean* OCR,
  where the SKIP tier does the work — that is the configuration the cost
  claim should be measured on, not this one.

Scans are not committed (hundreds of MB); both scripts take a corpus
directory.

## Manifest

`manifest.json`: `corpus_version` (bump on ANY case change — reports
cite it) and `cases[]` with `name`, `format`, `source`, `reference`
(paths relative to this directory), `provenance`.
