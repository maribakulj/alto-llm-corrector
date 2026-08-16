# lidenbrock

Structure-safe post-OCR correction of heritage transcriptions — **ALTO**
and **PAGE XML** — by LLM, rules engine, or any custom `EditProducer`.
No server, no job store, no vendor wired in: the library computes and
returns values, and everything about *running* a correction service
belongs to whoever calls it. *Lidenbrock*: the printed errata leaf bound
into books — literally what this library produces.

It is developed in the [lidenbrock](https://github.com/maribakulj/lidenbrock)
repository, which also carries a FastAPI + React demonstration of it. That
demo is **not part of this package** — it is not published, and it will be
removed once the library reaches its final form. Nothing here imports it;
the coupling only runs the other way.

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

- `lidenbrock.formats.alto` — ALTO XML parsing and rewriting (v2/v3/v4),
  with the Hyphenation Reconciler.
- `lidenbrock.formats.page` — PAGE XML (PRImA/Transkribus/eScriptorium):
  polygon geometry preserved verbatim (bbox derived for the planner),
  canonical text via `TextEquiv @index` with a `Word`-concat fallback,
  heuristic hyphenation (`- ¬ ⸗ U+00AD`), and a rewriter that never
  touches geometry. Both formats produce the **same `DocumentManifest`**.
- `lidenbrock.core.editing` + `lidenbrock.producers` — the **span edit
  protocol**: `EditScript` / `ReplaceLine` / `ReplaceSpan` with
  `RangeAnchor` and `MatchAnchor`, a deterministic `RulesProducer`, the
  `EditProducer` contract and a vision envelope (**the core** forwards an
  opaque image reference and touches no pixel — decoding and cropping is the
  producer's job, in the `lidenbrock[vision]` extra; the base install pulls
  no image dependency at all). See
  [`docs/edit-protocol.md`](docs/edit-protocol.md).
- `lidenbrock.core` — chunk planning, LLM-response validation,
  per-line acceptance policy, and the pure `CorrectionPipeline` that
  ties them together (`run()` async, `run_sync()` façade).
- `lidenbrock.core.schemas` — Pydantic models for documents, pages, blocks and
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
- `lidenbrock.errors` — one root, `LidenbrockError`, over `ParseError`,
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
- `lidenbrock.core.protocols` — ports (`BaseProvider`,
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

## Minimal working example

```python
import asyncio
from pathlib import Path

from lidenbrock import CorrectionPipeline, PipelineObserver
from lidenbrock.core.protocols import BaseProvider
from lidenbrock.formats.alto.parser import build_document_manifest


class IdentityProvider:
    """Returns each line's OCR text unchanged — useful for smoke tests."""

    async def list_models(self, api_key):
        return []

    async def complete_structured(
        self, api_key, model, system_prompt, user_payload, json_schema, temperature=0.0,
    ):
        # F14 contract: return (parsed_json, usage). Usage is an
        # lidenbrock.core.schemas.Usage (tokens in/out) or None when the
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

The version is read from `src/lidenbrock/__init__.py::__version__` by
hatchling (single source of truth — `pyproject.toml` is `dynamic`).

To cut a new release:

1. Bump `__version__` in `src/lidenbrock/__init__.py`.
2. Add a `## [X.Y.Z]` entry to [CHANGELOG.md](./CHANGELOG.md).
3. Commit + tag: `git tag lidenbrock-vX.Y.Z`.
4. Push the tag.
5. From the GitHub UI, run **Actions → Publish lidenbrock → Run
   workflow**. Pick `testpypi` first to validate, then `pypi`. The
   workflow uses Trusted Publishing (PEP 740 / OIDC) — no API token
   stored in GitHub secrets.

For a local dry-run before pushing:

```bash
scripts/release-lidenbrock.sh             # build + smoke-install only
scripts/release-lidenbrock.sh --testpypi  # build + upload TestPyPI
```

## License

Apache 2.0 (see [LICENSE](./LICENSE)).
