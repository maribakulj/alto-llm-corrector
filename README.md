# Lidenbrock

**Structure-safe post-OCR correction of heritage transcriptions** — ALTO and
PAGE XML. A Python library, and only that: it opens no socket, stores no
credential, and wires in no vendor.

The library and its documentation live in
**[`packages/lidenbrock/`](packages/lidenbrock/)** — start with
[its README](packages/lidenbrock/README.md).

## The promise, in one paragraph

The application decides; the model informs. Lines never merge, text never
migrates between them, and a correction that cannot be projected onto the
source structure is refused rather than approximated. Every alteration the
engine makes to the delivered file is declared and counted — including the
ones the *format* costs, which is why the report carries a fidelity scale
rather than a boolean. What the system cannot establish, it does not decide.

It does **not** do OCR, resegmentation, line merging or splitting,
translation, or text modernisation.

## The three repositories

| | |
|---|---|
| **this one** | the library. The deliverable, versioned and published |
| [`lidenbrock-demo`](https://github.com/maribakulj/lidenbrock-demo) | a web demonstration — upload a file, watch it corrected in a browser |
| [`cinoc`](https://github.com/maribakulj/cinoc) | the benchmark — transcription pipelines compared on ground truth, with 24 metrics and significance tests |

Both of them import this library. **This library imports neither**, and that
is a property being maintained rather than a coincidence: either could be
deleted without the library losing anything.

## Where things are

| | |
|---|---|
| [`packages/lidenbrock/`](packages/lidenbrock/) | the library: source, tests, its own docs, its `CHANGELOG` |
| [`SPECS_LIB_V2.md`](SPECS_LIB_V2.md) | the contract — what the library must be. Normative |
| [`docs/PLAN.md`](docs/PLAN.md) | **the single live plan** — what remains, in what order, and why |
| [`docs/adr/`](docs/adr/) | the decisions that shaped the engine, with their reasons |
| [`docs/audit/`](docs/audit/) | what was measured, with the evidence. No plans live here |
| [`docs/history/`](docs/history/) | frozen. Read it for *why*, never for *where* — and it predates the rename |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | how to work in this repository |

## Status

**Nothing has been published yet**, and no git tag exists. The version in
`__init__.py` is a development milestone, not a release — `docs/PLAN.md`
schedules the first real one and says exactly what it is waiting on.

No number in this repository claims a quality result. That is deliberate:
the plan forbids any quantified claim until a range has been measured over
at least two families of models, and that measurement is not done.
