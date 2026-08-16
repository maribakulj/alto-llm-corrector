# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lidenbrock is a post-OCR text-correction **library** (`packages/lidenbrock/`, ALTO and PAGE XML). It does NOT do OCR, resegmentation, line merging/splitting, translation, or text modernization.

**This repository is the library, and nothing else.** Two sibling repositories consume it, and both import it — never the reverse:

| repository | what it is |
|---|---|
| [`lidenbrock-demo`](https://github.com/maribakulj/lidenbrock-demo) | the FastAPI + React web demonstration. Left this repository on 2026-08-16 |
| [`cinoc`](https://github.com/maribakulj/cinoc) | the benchmark: pipelines compared on ground truth, 24 metrics, significance tests |

A consumer's need that seems to require this library to name or special-case it is either a missing injection point — fix it generically, here — or out of scope (`SPECS_LIB_V2.md` §12, §15).

Normative docs: `README.md`, `SPECS_LIB_V2.md` (the contract — what the library must be), `docs/PLAN.md` (**the single live plan** — what remains and in what order), `packages/lidenbrock/docs/`, `CONTRIBUTING.md`. Findings live in `docs/audit/` and carry no plan. Everything under `docs/history/` is frozen history — never trust it for current module locations, and never update it to match code. It also predates the rename and says `corrigenda` throughout; that is deliberate, and its README says why.

There is exactly ONE plan. Three competing, unratified ones were consolidated into `docs/PLAN.md` on 2026-07-25 and the originals moved to `docs/history/`; do not write a second, and do not revive the old ones.

Two standing rules from that plan, in force until it says otherwise:

- **Feature freeze.** No new producer, format, routing policy, cost optimisation, confidence writing, or public-API extension until the `L*` (line integrity) and `R*` (loss accounting) items are closed. Fixes, *reducing* refactors, corpora, measurement, tests and truth-in-documentation are always allowed.
- **One derivation, one family of directed primitives.** Hyphen-partner resolution has exactly two encodings and must keep exactly two: the directed primitives in `core/pairing.py` (the only reader of the pointer fields) and the unit derivation in `core/units.py` (`derive_hyphen_groups`). An earlier unification landed as an addition and left five parallel resolvers; that is down to zero duplicates (`docs/PLAN.md`, row `S1`), but the unit is **not yet authoritative** — pointer fields are still the storage of record. A fix that needs a third encoding, or a new projection of the derivation, is the signal to finish `S1` first, not to add one.

## Tech Stack

- **Python 3.11+, Pydantic v2, lxml, httpx.** No server dependency, no framework: the library opens no socket, stores no credential and writes no file unless asked.
- One optional extra: `[vision]` (Pillow, lazy-imported — CI installs it, so its tests actually run). `[typecheck]` and `[test]` are toolchains, declared in `pyproject` so they mean the same thing locally and in CI. `[qe]` left for the bench on 2026-08-16: it needed a 545 MB model no CI could fetch, so nothing ever ran it.

## Common Commands

```bash
cd packages/lidenbrock
pip install -e '.[test,typecheck]'   # the two toolchains, declared once in
                                     # pyproject so they mean the same thing
                                     # here and in CI. Without lxml-stubs,
                                     # mypy checks LESS than CI does.
pytest                               # coverage gate 85%
mypy --strict src/lidenbrock
ruff check src tests && ruff format --check src tests

pytest tests/test_x0000002.py::test_name -v   # a single test
```

## Architecture

### Core Pipeline (in `packages/lidenbrock/src/lidenbrock/`)

The correction flow is: **Parse → Chunk → Enrich → LLM Call → Validate → Reconcile → Rewrite**

1. `formats/alto/parser.py` (and `formats/page/`) — Parses ALTO XML (v2/v3/v4) / PAGE XML into the common `DocumentManifest`/`PageManifest` structures; detects inter-line hyphenation (explicit via SUBS_TYPE/HYP and heuristic via trailing dash, vetted by `core/pairing.py`)
2. `core/planner.py` — Splits lines into LLM-sized chunks using adaptive granularity: PAGE → BLOCK → WINDOW → LINE. Hyphen pairs are atomic and must never be split across chunks
3. `core/hyphenation.py` — **Hyphenation Reconciler**. Enriches chunks with hyphenation metadata before the LLM call, then reconciles corrected text back onto physical line pairs after the response. Core invariant: the app decides, the LLM informs — lines are never merged or moved
4. `core/validator.py` — Validates LLM JSON responses (line count, IDs, no newlines). Extra check: hyphen pairs must not have been merged by the LLM
5. `core/pipeline.py` — `CorrectionPipeline`, the **façade**: construction, the config fingerprint, and the six steps of a run (preflight → index → drive pages → finalise → render → report). Since `S2` it orchestrates and reimplements nothing — 568 lines, ratchet-guarded by `tests/test_orchestrator_budget.py`. **`run()` never mutates its input (private deep copy, ADR-011); instances are reentrant — read outcomes off `result.decisions`**
6. `core/driver.py` — `PageDriver`, the inner loop: plan a page's chunks, route them, run each, descend a granularity when retrying at this one is hopeless. Immutable config, no run state
7. `core/attempt.py` — one chunk asked of a producer until it answers or the budget runs out: request, call, validation, and what a retry costs (3 attempts, temperature ramp)
8. `core/outcome.py` — the three ways a chunk ends and what each does to its lines: success, fallback, absorbed error. Guards live in `core/guards.py`, the edit protocol in `core/editing.py`
9. `formats/alto/rewriter.py` — Rewrites ALTO XML with corrected text, reconstructing HYP/SUBS_* elements for hyphen pairs. Never modifies TextLine geometry attributes (ID, HPOS, VPOS, WIDTH, HEIGHT)

Line identity is always **(page_id, line_id)** — line_id alone repeats across files, so keying anything on it is a bug waiting for a two-file document (`ADR-001`). Every consumer inherits the rule; none may relax it.

## Critical Design Rules

- **Hyphen pairs are atomic**: PART1+PART2 lines must always stay in the same LLM chunk. The chunk planner, validator, and reconciler all enforce this.
- **Lines never merge**: No text migrates between lines. The rewriter preserves physical line boundaries.
- **Line identity is (page_id, line_id)** everywhere — never key anything on line_id alone.
- **Conservative heuristic mode**: When hyphenation is detected heuristically (no SUBS_TYPE in source), no SUBS_CONTENT is invented.
- **Fallback to source**: On ambiguity or repeated LLM failure, always fall back to original OCR text rather than guessing.
- **ALTO geometry**: The rewriter redistributes token widths proportionally within a TextLine but never changes the TextLine's own coordinates.
- **Tests**: every fix ships with the test that fails before it. Audit-trail references (`Audit-Fxx`, waves) stay in PRs/issues, not in new code comments.
