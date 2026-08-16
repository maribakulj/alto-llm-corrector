# Contributing

## Repo layout

**One deliverable.** `packages/saknussemm/` is the correction library: the
only packaged Python distribution (hatchling), and the reason this
repository exists. Everything beside it serves it — the plan, the ADRs, the
audits, the fixtures.

The web demonstration and the benchmark left on 2026-08-16 and live in
[`saknussemm-demo`](https://github.com/maribakulj/saknussemm-demo) and
[`cinoc`](https://github.com/maribakulj/cinoc). They import this library.
It imports neither, and a change that would reverse that direction is out
of scope rather than clever.

## Local dev setup

```bash
cd packages/saknussemm
pip install -e '.[test,typecheck]'
```

Both extras are declared in `pyproject.toml` rather than assembled by hand,
so they mean the same thing here and in CI. That is not tidiness: the test
toolchain used to live in a workflow's `pip install` line, and a test needing
PyYAML went green locally and red on all three Python versions.

Without `lxml-stubs` (in `[typecheck]`), `mypy --strict` checks **less** than
CI does — `_Element.attrib` degrades to `Any` and strict mode goes quiet.

## Running things

```bash
cd packages/saknussemm
pytest                                   # coverage gate 85%
pytest tests/test_x0000002.py::test_name -v
mypy --strict src/saknussemm
ruff check src tests && ruff format --check src tests
```

## CI gates (all must pass)

Five jobs, all on the library: lint, types, tests (3.11 / 3.12 / 3.13 with
the coverage gate), the external-corpus invariants, and the build — which
constructs the wheel and sdist and smoke-installs the wheel under every
supported Python, so a packaging regression fails here rather than at
release time.

**Green locally is not green in CI.** CI runs three Python versions; a
gesture that passes here can fail there, and has. That is what the pull
request is for, and why "the CI is green" and not "the suite passes on my
machine" is the condition for merging.

## Documentation rules

Normative docs are the ones listed in the README's documentation map
(README, `SPECS_LIB_V2.md`, `packages/saknussemm/docs/`, `docs/API.md`,
`SECURITY.md`, this file). Everything under `docs/history/` is frozen
design/audit history — never update it to match the code; write the
current truth in a normative doc instead. Audit-trail references
(`Audit-Fxx`, wave numbers) belong in PRs and issues, not in new code
comments.

## License

Apache 2.0 (see `LICENSE`).
