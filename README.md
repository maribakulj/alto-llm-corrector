# saknussemm

Structure-safe post-OCR correction of heritage transcriptions — **ALTO**
and **PAGE XML** — by LLM, rules engine, or any custom `EditProducer`.
No server, no job store, no vendor wired in: the library computes and
returns values, and everything about *running* a correction service
belongs to whoever calls it. *Saknussemm*: the printed errata leaf bound
into books — literally what this library produces.

It is developed in the [saknussemm](https://github.com/maribakulj/saknussemm)
repository, which also carries a FastAPI + React demonstration of it. That
demo is **not part of this package** — it is not published, and it will be
removed once the library reaches its final form. Nothing here imports it;
the coupling only runs the other way.

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

## What's not

- No LLM HTTP calls (you supply a `BaseProvider` implementation, or use
  an adapter like XerLLM).
- No filesystem writes, ever — reading source ALTO files is the only
  I/O; outputs travel on `CorrectionResult` (ADR-011).
- No FastAPI, no SSE, no job store. Those belong to the consumer: the
  repository's demo backend implements them for itself, and a future
  extraction of them would be its own distribution, not this one.

## What it costs, and what it does not scale to

Measured on the three pinned Gallica pages — 1215 lines, 1.99 MB of ALTO,
2026-08-17, this machine, no network:

| | identity run | with corrections |
|---|---|---|
| CPU per line | 0.21 ms | 0.38 ms |
| peak memory | ×7.3 the source XML | ×11.9 |
| per line | 11.6 kB | 19.1 kB |

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

**Pages are corrected in reading order, and that is semantic.** Cross-page
hyphen reconciliation assumes the earlier page was decided first, so
reordering or parallelising pages changes the bytes produced. Reordering the
*files* of one call is safe and tested.

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
