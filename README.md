---
title: Lidenbrock
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Lidenbrock

**The deliverable is a Python library** — `lidenbrock`, in
[`packages/lidenbrock/`](packages/lidenbrock/): post-OCR text correction of
**ALTO and PAGE XML**, structure-safe, with no server and no vendor wired in.
That is the thing that gets published, versioned and supported.

**The rest of this repository is a demonstration of it, and it is temporary.**
The FastAPI backend and the React frontend exist to show the library working
on a real file, in a browser, without anyone installing Python — a shop
window, not a second product. **They will be removed when the library reaches
its final form.** Nothing in them is packaged, published or under SemVer, and
the library does not import them: the coupling is one-way and stays that way
(`SPECS_LIB_V2.md` §15).

Read that as a promise about the library, not a warning about the demo: the
demo can be deleted without the library losing anything, and that is exactly
the property being maintained.

---

## What the demo does

Upload one or more ALTO or PAGE XML files, choose a provider and model, and get the corrected XML back — in its original format and namespace, with hyphenation pairs preserved intact across line boundaries. Providers: OpenAI, Anthropic, Mistral, Google Gemini.

**What it does:** corrects OCR errors in the text of a line — ALTO `<String CONTENT="..."/>`, PAGE `<TextEquiv><Unicode>` — never its geometry.
**What it does not:** OCR, resegmentation, line merging/splitting, translation, or text modernisation.

**Formats:** ALTO v2/v3/v4 and PAGE 2013/2019/2024 (other PAGE dates parse
tolerantly). Both are first-class: same engine, same guarantees, same
`DocumentManifest`. See
[`packages/lidenbrock/docs/format-support.md`](packages/lidenbrock/docs/format-support.md)
for the version matrix and what each one validates against.

---

## Documentation map

Two lifetimes, and it is worth knowing which one a document has. **Library
docs outlive the demo**; demo docs go with it. Everything under
`docs/history/` is already dead and fenced off.

**The library — kept current, survives the demo's removal:**

| Doc | Scope |
|---|---|
| [`packages/lidenbrock/README.md`](packages/lidenbrock/README.md) | The library's own front page — this is what a PyPI reader sees, and it stands alone |
| `SPECS_LIB_V2.md` | Normative spec for the `lidenbrock` library — what it **must be** |
| [`docs/PLAN.md`](docs/PLAN.md) | **The single live plan** — what remains, in what order, and what `1.0` requires. There is exactly one; do not write a second |
| [`docs/audit/`](docs/audit/) | Findings, with evidence — what has been **observed**. Carries no plan |
| `packages/lidenbrock/docs/` | Library guides: [`quickstart`](packages/lidenbrock/docs/quickstart.md), [`formats`](packages/lidenbrock/docs/formats.md) (how the two backends are built), [`format-support`](packages/lidenbrock/docs/format-support.md) (which versions, and what validates), [`edit-protocol`](packages/lidenbrock/docs/edit-protocol.md), [`versioning`](packages/lidenbrock/docs/versioning.md), and [`reading-a-report`](packages/lidenbrock/docs/reading-a-report.md) — what each number in a run's report does **and does not** mean |
| `packages/lidenbrock/CHANGELOG.md` | The library's released changes (SemVer) |
| [`docs/adr/`](docs/adr/) | Architecture decision records — why a design is what it is. Some record demo decisions (002, 003, 004); those retire with it |

**The demo — accurate today, removed with the app:**

| Doc | Scope |
|---|---|
| `README.md` (this file, below the map) | Running and deploying the demo |
| [`docs/API.md`](docs/API.md) | The demo backend's HTTP API map (the OpenAPI schema is the contract) |
| [`SECURITY.md`](SECURITY.md) | Deployment profiles and threat model — the demo's, not the library's. A library has no CORS policy |

**Both:**

| Doc | Scope |
|---|---|
| `CONTRIBUTING.md`, `CLAUDE.md` | Contributor + assistant guidance for the whole repository |

**Status:** pre-`0.10.0`, no git tag yet. The library is a research-grade beta:
read `docs/PLAN.md` for the known open defects and the criteria a `1.0` has to
meet before it can claim to be one. The **top-level import surface is
provisional until `1.0.0`** but no longer accidental: `S3b` cut it from 95
accumulated symbols to the **68** two computed closures reach, and demoted
symbols stay importable from their own module
([`packages/lidenbrock/docs/versioning.md`](packages/lidenbrock/docs/versioning.md)).

**Historical:** everything under [`docs/history/`](docs/history/) is
frozen design & audit trail (original specs, migration and audit logs).
It contradicts the current code in places by design — read it for *why*
a decision was made, never for *where* code lives today.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/) v2+

---

## Local installation

```bash
git clone https://github.com/maribakulj/lidenbrock.git
cd lidenbrock

# Copy the example env file (edit if needed)
cp .env.example .env

# Build and start both services
docker compose up --build
```

The app is then available at **http://localhost:5173**.
The backend API is exposed at **http://localhost:8000**.

To stop:

```bash
docker compose down
```

---

## Deployment on Hugging Face Spaces

1. Create a new Space on [huggingface.co/spaces](https://huggingface.co/spaces) with **Docker** as the SDK.
2. Push this repository to the Space:

```bash
git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
git push space main
```

The root `Dockerfile` is detected automatically. It builds the React frontend and embeds it as static files served by FastAPI on **port 7860** (required by HF Spaces).

No separate nginx is needed — FastAPI serves `/` from `./static/` and the SPA catch-all returns `index.html`.

### ⚠ Job storage is volatile

The container writes uploads and corrected outputs to `/tmp/app-jobs/<job_id>/`. **Anything in `/tmp` is lost when the container restarts** (HF Spaces redeploys on every commit, on idle eviction, and on factory reboot). Practical implications:

- A job in progress when the Space redeploys is killed and the result is lost.
- The `trace.json` and corrected XML are gone after a restart even if the job completed — download them immediately.
- A user revisiting the Space after a restart will get a `404` on `/api/jobs/{id}/download` for any previous job_id.

The frontend shows a yellow warning banner above the upload zone.

**A persistent volume does NOT make jobs persistent.** Job records
(status, capability-token hashes, eviction timestamps) live in process
memory only. If you mount a volume and point `JOB_STORAGE_DIR` at it,
the files survive a restart but the API has no record of them: every
endpoint returns `404` for pre-restart job_ids, the old tokens are
gone, and the results are unreachable. The server therefore deletes
such orphan directories at startup rather than letting them accumulate
as dead weight. Real persistence (a database holding job records that
survive restarts) is a planned feature of that profile, not a
mount-a-volume option.

Single-worker on purpose — see Dockerfile comments. A multi-worker setup would need a shared `JobStore` (Redis, Postgres) since the current one is in-process.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `JOB_STORAGE_DIR` | `/tmp/app-jobs` | Base directory for job files (input + output) |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed CORS origins, or `*` |
| `DEPLOYMENT_PROFILE` | `demo` | `demo` (public Space stance) or `proxy_protected` (behind SSO/proxy; refuses wildcard CORS). `institutional` is the deprecated spelling of `proxy_protected` — it still works and warns. See [SECURITY.md](SECURITY.md) |
| `MAX_ACTIVE_JOBS` | `4` | Concurrent correction pipelines |
| `MAX_CONCURRENT_UPLOADS` | = `MAX_ACTIVE_JOBS` | Concurrent upload slots — reserved by an ASGI middleware before any body byte is read; at capacity the request is refused (503 + `Retry-After`) without receiving the upload |
| `JOB_TIMEOUT_SECONDS` | `1800` | Per-job wall-clock budget (0 disables) |

---

## Hyphenation Reconciler

ALTO files often encode inter-line hyphenation via `SUBS_TYPE="HypPart1/HypPart2"` and `SUBS_CONTENT` attributes, or via a trailing dash heuristic; PAGE carries no equivalent markup, so pairing there is heuristic only. The **Hyphenation Reconciler** (`lidenbrock.core.hyphenation`, in the `packages/lidenbrock` library) treats such pairs as atomic units in both formats:

- Both lines are always sent in the **same LLM chunk** — never split across requests.
- The LLM is instructed to correct each line individually without moving text between them.
- After the LLM response, the reconciler redistributes the corrected fragments back onto the original physical lines and reconstructs the `HYP`/`SUBS_*` attributes.
- On ambiguity or repeated failure the original OCR text is kept as fallback.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2, httpx, lxml, sse-starlette |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| LLM providers | OpenAI, Anthropic, Mistral, Google Gemini |
| Dev stack | docker-compose (backend :8000 + nginx :5173) |
| HF Spaces | Single multi-stage Dockerfile, port 7860 |
| Storage | `/tmp/app-jobs/{job_id}/` — no database |
