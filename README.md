# saknussemm

Structure-safe post-OCR correction of heritage transcriptions — **ALTO**
and **PAGE XML** — by LLM, rules engine, or any custom `EditProducer`.
No server, no job store, no vendor wired in: the library computes and
returns values, and everything about *running* a correction service
belongs to whoever calls it. *Saknussemm*: the printed errata leaf bound
into books — literally what this library produces.

This repository is the library, and nothing else. The web demonstration
left it on 2026-08-16 for [`saknussemm-demo`](https://github.com/maribakulj/saknussemm-demo),
and the benchmark for [`cinoc`](https://github.com/maribakulj/cinoc).
Both import this library; nothing here imports either.

## The three repositories

| | |
|---|---|
| **this one** | the library. The deliverable, versioned and published |
| [`saknussemm-demo`](https://github.com/maribakulj/saknussemm-demo) | a web demonstration — upload a file, watch it corrected in a browser |
| [`cinoc`](https://github.com/maribakulj/cinoc) | the benchmark — transcription pipelines compared on ground truth, with 24 metrics and significance tests |

Both of them import this library. **This library imports neither**, and that
is a property being maintained rather than a coincidence: either could be
deleted without the library losing anything.

## Status

**0.9.0 — beta.** The public surface is pinned by an executable
snapshot test, but the API is **not frozen yet**: the 0.9.x series may
break it deliberately (each break is a reviewed snapshot change with a
CHANGELOG entry). Strict SemVer starts at `1.0.0`, which requires an
independent external API review first; see
[docs/versioning.md](docs/versioning.md). Docs:
[quickstart](docs/quickstart.md) ·
[la vie d'une ligne](docs/la-vie-d-une-ligne.md) ·
[edit protocol](docs/edit-protocol.md) ·
[formats](docs/formats.md) — and a runnable, test-guarded
[examples/quickstart.py](examples/quickstart.py).

## What's in the box

- `saknussemm.formats.alto` — ALTO XML parsing and rewriting (v2/v3/v4),
  with the Hyphenation Reconciler.
- `saknussemm.formats.page` — PAGE XML (PRImA/Transkribus/eScriptorium):
  polygon geometry preserved verbatim (bbox derived for the planner),
  canonical text via `TextEquiv @index` with a `Word`-concat fallback,
  heuristic hyphenation (`- ¬ ⸗ U+00AD`), and a rewriter that never
  touches geometry. Both formats produce the **same `DocumentManifest`**.
- `saknussemm.core.editing` + `saknussemm.producers` — the **span edit
  protocol**: `EditScript` / `ReplaceLine` / `ReplaceSpan` with
  `RangeAnchor` and `MatchAnchor`, a deterministic `RulesProducer`, the
  `EditProducer` contract and a vision envelope (**the core** forwards an
  opaque image reference and touches no pixel — decoding and cropping is the
  producer's job, in the `saknussemm[vision]` extra; the base install pulls
  no image dependency at all). See
  [`docs/edit-protocol.md`](docs/edit-protocol.md).
- `saknussemm.core.page_alignment` + `saknussemm.producers.page_llm` — the
  **realigned mode**: one call per page instead of one contract per line,
  and the alignment that recovers which returned line is which. Eight times
  cheaper, and its whole risk is in one module — see "Two modes" below.
- `saknussemm.core` — chunk planning, LLM-response validation,
  per-line acceptance policy, and the pure `CorrectionPipeline` that
  ties them together (`run()` async, `run_sync()` façade).
- `saknussemm.core.schemas` — Pydantic models for documents, pages, blocks and
  lines, plus the seven **frozen, injectable policies**: `RetryPolicy`
  (attempt cap / temperature ramp / per-chunk budget — `.default()` is
  byte-compatible with the historical behaviour, `.deterministic()` pins
  every temperature to 0), `GuardConfig` (every anti-migration threshold),
  `ChunkPlannerConfig`, `PairingPolicy` (hyphen-pairing seam),
  `LossPolicy` (what a run does when a correction cannot project without
  losing word granularity — ADR-012), `ConfidencePolicy` and
  `RoutingPolicy`. Each exposes `policy_fingerprint()`; the pipeline combines them into
  `config_fingerprint()`, stamped into the corrected XML's
  `processingStep` for provenance.
- `saknussemm.errors` — one root, `SaknussemmError`, over `ParseError`,
  `ValidationError` (both also `ValueError`) and `CorrectionAborted`
  (raised by the cooperative `should_abort` cancellation probe).
  `CorrectionError` is the same class under its older name.
- `CorrectionResult` — the run's whole deliverable (ADR-011): the
  corrected XML per source file (`result.corrected_files`), the
  immutable per-line `DecisionSet` (`result.decisions`), a public,
  versioned `CorrectionReport` (v2: one staged `LineOutcome` per line —
  source → proposal → decision → projection, with structured fallback
  reasons), the applied `EditScript` and the run's statistics. The
  engine never persists anything and never mutates its input — the
  same document can be run again or concurrently; `result.write(dir)`
  is the one-call persistence helper, or feed the bytes to your own
  transaction.
- `saknussemm.core.protocols` — ports (`BaseProvider`,
  `PipelineObserver`, `FormatAdapter`) that consumers implement to plug
  the core into their own infrastructure.
- PEP 561 `py.typed` marker — the package type-checks under
  `mypy --strict` and so can your integration.

Job-level concepts (`JobManifest`, `JobStatus`, the `Provider` vendor
enum) are deliberately **not** here — the core does not enumerate LLM
vendors or track a server job's lifecycle; they live in the consumer.

## Two modes, and the one thing that separates them

The library can be asked for the same correction in two ways. They differ in
**who holds line identity**, and everything else follows from that.

| | `line_keyed` — keyed mode | `page_aligned` — realigned mode |
|---|---|---|
| identity held by | the JSON contract, per line | the alignment, after the fact |
| producer | `producers.llm_edit.LLMEditProducer` | `producers.page_llm.PageLLMEditProducer` |
| calls (24 592 lines) | ~2 000 | **28** |
| input tokens | 5.49 M | **0.39 M** |
| cost | $1.11 | **$0.14** |
| a model that merges two lines | refused by the validator (an id is missing) | refused by the alignment (neither line is vouched for) |
| what an unresolvable line does | fails the chunk, then retries | keeps its OCR text |

Both run on the same engine. The guards, the hyphenation reconciler, the
projection invariant and the loss accounting are shared and unchanged, which
is what makes the two comparable on the same corpus rather than two products.

**Where the eight-fold saving comes from.** Not cleverness: the keyed
envelope carries `prev_text` and `next_text` with every line, so each line's
text is sent three times, and the JSON around it weighs **7.9× the text it
transports**. The realigned mode sends the page once, as bare strings.

**What it costs, stated plainly.** The answer comes back with no line ids, so
which returned line answers which source line has to be *recovered*. Get that
wrong and the file says something the scan does not, on a line nobody
flagged — worse than never correcting. The recovery lives in
`core/page_alignment.py`, and its refusals were measured before it was
written: on eight real Gallica pages, **0** lines paired with the wrong line,
17 of 1 035 left unmatched on the worst page (always in pairs, never a silent
substitution), 0.05 s per page.

The merge case in particular is not a heuristic. A correction moves a line's
token count by −1, 0 or +1 — **100% of 8 859 measured pairs** — while a
merged line carries 1.64× to 1.86× its source's tokens. The two populations
do not overlap, so a merged line matches neither of the lines that made it,
and both keep their OCR.

**Which to use — and today the answer is keyed mode.** The realigned mode was
run against a real provider on 2026-08-19, four Gallica pages, 3 135 lines.
The alignment held perfectly: **zero** lines came back unmatched. The model
did not. The share of lines it proposes to change swings between **2.3% and
56%** page to page, against a steady 48–72% in keyed mode — and on one page
it returned **963 of 986 lines untouched**.

The saving is real and measured on the same page: 2 calls against 147,
`$0.0051` against `$0.0189`, 77 s against 234 s. But eight times cheaper is
worth nothing if the run corrects a fifth as much, and how much it corrects
is not currently predictable.

Page SIZE is the factor. At **518 lines the realigned mode matches the keyed
one** — 195 corrections against 196. At 986 it delivers **9 against 278**.

Bounding the request does not currently help, and the reason is worth knowing.
Caps of 400 and 250 lines on a 986-line page both emit **217 chunks** — the
cap is not what splits anything. Once it is crossed the planner descends to
BLOCK granularity, and the page has 217 blocks; below a block's size the cap
stops mattering. That recovers the corrections and destroys the economy.
Slicing a page into N equal parts is not something the planner can express
today.

So: **keyed mode for work you depend on.** The realigned mode is complete, its
risky half is proven and its hyphenation is fixed; what it waits on is either a
splitting mode the planner does not have, or a model that holds attention over
a thousand lines at once.

## What it does not claim to have checked

The guards compare characters. They have no notion of meaning, and no
threshold gives them one: on twelve counter-examples put through the real
acceptance guard, all twelve were accepted at both threshold settings — a
removed negation at similarity 0.8955, a changed date at 0.9388, a
truncated amount at 0.9643, a neighbouring line copied verbatim at 0.8852.
Tightening the bound far enough to catch those rejects the ordinary OCR
fixes the library exists to make.

So a run does not report those lines as `corrected`. It delivers the
correction and says it cannot vouch for it:

```python
result.review_lines      # 11
result.review_reasons    # {"proper_noun_changed": 8, "negation_changed": 3,
                         #  "digits_changed": 2}

d = result.decisions.by_ref[LineRef(page_id="P1", line_id="TL7")]
d.status                 # LineStatus.REVIEW_REQUIRED
d.final_text             # the CORRECTION — a referral takes nothing away
d.review_reasons         # ("digits_changed: 1789 → 1780",)
```

Three properties worth stating plainly:

- **the correction ships.** A referred line carries the same bytes a
  `corrected` one would, and the same op in the `EditScript`. Referral is a
  statement about the check, not about the correction — on the real run this
  was measured against, most of the flagged changes were good ones.
- **turning it off changes no output.** `ReviewPolicy.silent()` restores the
  previous status distribution and delivers identical files. The library
  verifies that by comparing the bytes of two runs, not by promising it.
- **it is not a defect rate.** It is the size of what the guards were
  already unable to check and were not saying.

Some rules the design called for are **not** implemented, because the engine
has no input for them — a lexicon it does not carry, a routing mode that asks
two producers the same line, a confidence score that is admittedly not
calibrated. `docs/la-vie-d-une-ligne.md` §3 bis lists all six codes and the
three absences with their reasons.

## What's not

- No LLM HTTP calls (you supply a `BaseProvider` implementation, or use
  an adapter like XerLLM).
- No filesystem writes, ever — reading source ALTO files is the only
  I/O; outputs travel on `CorrectionResult` (ADR-011).
- No FastAPI, no SSE, no job store. Those belong to the consumer:
  `saknussemm-demo` implements them for itself, in its own repository and
  its own distribution.

## What it costs, and what it does not scale to

Measured on the three pinned Gallica pages — 1215 lines, 1.99 MB of ALTO,
2026-08-17, this machine, no network:

| | identity run | with corrections |
|---|---|---|
| CPU per line | 0.21 ms | 0.38 ms |
| peak memory | ×7.3 the source XML | ×11.9 |
| per line | 11.6 kB | 19.1 kB |

Referral costs **+8 %** of wall clock in the worst case measured — the same
three pages with a rule that changes every line, 0.895 → 0.964 ms per line,
235 lines referred. It is one extra character-level diff per CHANGED line, so
a run that corrects little pays nothing. `ReviewPolicy.silent()` removes it.

**The unit of work is one document, and the corpus belongs to you.** The
whole run lives in memory until it returns: the manifest, every line's
trace, the decisions and the corrected bytes. So 100 000 lines is roughly
40 s of CPU and 1.9 GB — nothing streams, and nothing is bounded on your
behalf. Run documents one at a time and keep the batching upstream.

**The scale parameter is lines per PAGE, not per document.** Time is linear
in lines while pages stay ordinary (30–1200 lines, which is what real OCR
produces). On a single page of several thousand lines *combined with a
producer that fails often*, the fallback path degrades quadratically —
measured, and on the list to fix rather than to live with.

**A file whose artefact does not carry its decisions is withheld, and the
run continues.** The last thing the library does before handing anything back
is re-read the XML it just built and compare it, word for word, against what
it decided to write. A file that disagrees is corruption of the deliverable,
so it is not handed back — **absent** from `corrected_files`, never present in
a lesser version. A lookup by name raises `KeyError`; it never returns bytes
nobody vouched for.

It used to take the whole run down with it: a 300-page volume lost for one
line, and the report lost too — every trace, every fidelity level, every
decision — leaving one exception message about one line. The other 299 files
were faithful, and refusing to hand them over never made them better.

```python
result = await pipeline.run(...)          # returns; does not raise for this
result.undeliverable_files                # {'f17.xml': "line TL0441: decided … artefact …"}
result.corrected_files['f17.xml']         # KeyError
result.write(out)                         # ConfigurationError: INCOMPLETE set
result.write(out, allow_partial=True)     # the 299, on purpose
```

That last line is where the loudness lives. Withholding alone would trade a
loud failure for a quiet one — a caller looping over `corrected_files` would
persist 299 of 300 pages and report success — so `write`, the one door that
puts bytes on disk, refuses an incomplete set until the caller says in
reviewed code that it accepts one.

The argument for keeping the old total refusal was that a word broken across
two files could be delivered half-corrected. Measured over the two real
Gallica issues — 12 files, 8 787 lines, 1 583 hyphen units — **zero** cross a
file boundary, on a detector checked against a fabricated positive. The
mechanism exists; it is not worth losing everything else for.

**A correction on a broken word costs the correction of two lines.** A word
split across a line break is decided as a unit: the reconciler validates both
fragments against `SUBS_CONTENT`, and when the join does not match it reverts
**both** sides to the source. That is deliberate — a mixed pair would rewrite
the joined word on one line and keep it verbatim on the other, which is the
one thing the hyphen machinery exists to prevent — but it means one bad
fragment discards a good correction next to it.

It is not a rounding error. On the 24 592-line Gallica run of 2026-08-18 it
was the **second cause of refusal**, 2 271 lines, behind exhausted attempts
and ahead of every guard. And it concentrates where correction is most
wanted:

| pages | median word confidence | lines lost to the pairing rule |
|---|---|---|
| degraded (n=5) | 0.50 – 0.94 | **12 – 28%** |
| clean (n=19) | 0.99 – 1.00 | 7 – 11% |

Read it off the result, no message parsing:

```python
result.fallback_reasons.get("hyphen_pair_fallback", 0)   # in LINES
```

The unit is lines, and a fallen pair contributes two of them — halving it to
count pairs understates what the run gave up. Both halves of that sentence
are guarded by `tests/test_the_cost_of_a_broken_word_is_countable.py`.

**Pages are corrected in reading order, and that is semantic.** Cross-page
hyphen reconciliation assumes the earlier page was decided first, so
reordering or parallelising pages changes the bytes produced.

**Consecutive files are consecutive pages, so the order of the files matters
too.** One file per page is how a digital library exports a volume, and the
library treats the list you pass as that volume: a word broken at the foot of
one file continues onto the head of the next, explicitly or from a trailing
dash. Reorder the list and you change which pages are adjacent, which changes
which words are joined, which changes the bytes.

The corollary is the trap: **handing unrelated documents to one call makes
them one document.** Nothing refuses it. Measured over five unrelated real
ALTO files, four hyphen links formed across file boundaries — one joining a
BnF page to a Gallica page — and two good corrections were discarded as
`hyphen_pair_fallback` because the pair could not be reconciled. Pass one
document per call, where a document is the set of files that belong to the
same scan, in reading order.

An earlier version of this section said reordering the files was "safe and
tested". It was tested, on two one-line documents with no break mark, which is
the only shape where it holds.

**One `run()` at a time per producer.** The engine keeps no per-run state and
two concurrent runs on one instance produce identical results — but that is a
property of the engine, not of what you inject. A producer, scorer or
observer holding per-run state will be corrupted silently, and nothing
detects it. Events carry no run id either, so a shared observer cannot tell
two runs apart: use one observer per run, or one run at a time.

**Retry backoff is serialised wall-clock.** The default ramp sleeps up to a
few seconds per failing chunk, and those sleeps add up across a document. A
host that manages its own retry should set the backoff bases to zero.

## Installing

```bash
pip install saknussemm            # Pydantic and lxml, nothing else
pip install 'saknussemm[vision]'  # adds Pillow, for the crop-and-ask producer
```

Python 3.11 or later. The base install deliberately carries no image library:
the core is blind to pixels, and a test reads `[project].dependencies` to keep
it that way.

**Nothing has been published yet.** There are no git tags and the package is
not on any index, so the commands above will not work today — see *Status*
below. Until the first release:

```bash
pip install git+https://github.com/maribakulj/saknussemm
```

## Minimal working example

```python
import asyncio
from pathlib import Path

from saknussemm import CorrectionPipeline, PipelineObserver
from saknussemm.core.protocols import BaseProvider
from saknussemm.formats.alto.parser import build_document_manifest


class IdentityProvider:
    """Returns each line's OCR text unchanged — useful for smoke tests."""

    async def list_models(self, api_key):
        return []

    async def complete_structured(
        self, api_key, model, system_prompt, user_payload, json_schema, temperature=0.0,
    ):
        # F14 contract: return (parsed_json, usage). Usage is an
        # saknussemm.core.schemas.Usage (tokens in/out) or None when the
        # provider cannot report consumption.
        return {
            "lines": [
                {"line_id": line["line_id"], "corrected_text": line["ocr_text"]}
                for line in user_payload["lines"]
            ],
        }, None


class PrintObserver:
    def on_event(self, event_type, payload):
        print(f"{event_type}: {payload}")


async def main():
    src = Path("page.xml")
    doc = build_document_manifest([(src, src.name)])

    # §5.1 — the pipeline is built around an EditProducer; credentials live
    # inside the producer, never on run(). for_provider() wraps a raw LLM
    # BaseProvider for you. (A deterministic RulesProducer, or any custom
    # EditProducer, goes through CorrectionPipeline(producer=...) directly.)
    pipeline = CorrectionPipeline.for_provider(
        IdentityProvider(),
        api_key="",
        model="mock",
        provider_name="local",
        observer=PrintObserver(),
    )
    result = await pipeline.run(
        document_manifest=doc,
        source_files={src.name: src},
        run_id="local-run",  # optional — auto-generated when omitted
    )
    # The engine never writes; the result carries the artefacts.
    result.write(Path("./out"))  # corrected XML + report.json
    print(f"reconciled {result.total_reconciled} hyphen pairs across {result.total_chunks} chunks")
    print(f"tokens: {result.usage.total_tokens}; report lines: {result.report.total_lines}")


asyncio.run(main())
```

No event loop of your own? `pipeline.run_sync(...)` takes the same
arguments and wraps `asyncio.run` for you. Every run is effectively a
dry run until *you* persist (`result.write(dir)` or your own sink); pass
`should_abort=callable` for cooperative cancellation (raises
`CorrectionAborted` between pages/chunks — no result, nothing to
persist).

## Releasing

The version is read from `src/saknussemm/__init__.py::__version__` by
hatchling (single source of truth — `pyproject.toml` is `dynamic`).

To cut a new release:

1. Bump `__version__` in `src/saknussemm/__init__.py`.
2. Add a `## [X.Y.Z]` entry to [CHANGELOG.md](./CHANGELOG.md).
3. Commit + tag: `git tag saknussemm-vX.Y.Z`.
4. Push the tag.
5. From the GitHub UI, run **Actions → Publish saknussemm → Run
   workflow**. Pick `testpypi` first to validate, then `pypi`. The
   workflow uses Trusted Publishing (PEP 740 / OIDC) — no API token
   stored in GitHub secrets.

For a local dry-run before pushing:

```bash
scripts/release-saknussemm.sh             # build + smoke-install only
scripts/release-saknussemm.sh --testpypi  # build + upload TestPyPI
```

## License

Apache 2.0 (see [LICENSE](./LICENSE)).
