# Versioning & deprecation policy

## Current series: 0.9.x (beta)

The library has never been published to an index, so the 0.9.x series is
free to break the public surface without deprecation aliases — every
break is still a deliberate act (snapshot-test change + CHANGELOG entry).
`1.0.0rc1` freezes the API; `1.0.0` is tagged only after the independent
external review of the public API required by the release plan.

**The top-level surface has been cut, and is provisional until the
freeze.** `corrigenda.__all__` held 95 symbols, accumulated one addition
at a time rather than designed. `S3b` (2026-08-01) reduced it to the
**68** that two computed closures reach — see *What is public* below for
what those closures are and why the format-adapter seam is deliberately
outside them. A demoted symbol was **not removed**: it stays importable
from its own module, so migrating is an import rewrite, not a rewrite.

Provisional still means provisional: 0.9.x may cut further if a closure
turns out to be wrong. What the snapshot test guarantees meanwhile is
that the list cannot *grow* back.

## SemVer, strictly

From `1.0.0`, `corrigenda` follows [Semantic Versioning](https://semver.org):

- **MAJOR** — any breaking change to the public surface: removing or
  renaming a symbol listed in `corrigenda.__all__`, changing an
  entry-point signature (`run`, `run_sync`, `for_provider`,
  `apply_edit_script`, …), a breaking change to the `CorrectionReport`
  JSON shape, or a behavioural change that alters output bytes for
  unchanged inputs outside a documented bug fix.
- **MINOR** — additive: new symbols, new optional parameters/fields, new
  format backends, new producers.
- **PATCH** — bug fixes that do not change the public surface.

The public surface is **pinned by an executable snapshot**
(`tests/test_public_api_snapshot.py`): CI fails on any accidental drift,
so a surface change is always a deliberate, reviewed act paired with a
CHANGELOG entry.

## What is public

Two doors, and the difference between them is the guarantee, not the
mechanism — both resolve to the same objects.

- **`corrigenda.*`** — everything listed in `corrigenda.__all__`. Under
  strict SemVer *from 1.0.0*; provisional until then (see above).

  Since `S3b` (2026-08-01) that list is **computed, not chosen**: 68
  symbols, being the transitive closure of two promises — what
  `load`/`correct`/`correct_sync` return, and what a custom
  `EditProducer` must name to implement the protocol the README's first
  sentence advertises. A name is in `__all__` because one of those two
  closures reaches it, and for no other reason. It was 95 before, reached
  by accretion.
- **The submodule paths** documented in the README (`corrigenda.core.*`,
  `corrigenda.formats.alto` / `corrigenda.formats.page`,
  `corrigenda.producers.*`). Supported and documented — this is the door
  the repository itself uses (864 module-path imports against 65
  top-level ones), and the one a symbol demoted by `S3b` keeps.

  Two things live here on purpose rather than by omission. The **format
  adapter seam** (`FormatAdapter`, `RewriteResult`, `RewriteMetrics`,
  `AlignedPair`, `TokenAlignment`) is the rewriter's own accounting
  vocabulary: injecting an adapter is an optional argument most callers
  never pass, and `R5`/`R8`/`L8` have all moved these types recently.
  Promising their stability under SemVer would be a promise nothing
  supports. The **concrete producers and parsers** (`RulesProducer`,
  `LLMEditProducer`, `build_document_manifest`, `parse_alto_file`, …) are
  implementations, not contracts: the contract they satisfy —
  `EditProducer`, `FormatAdapter` — is what a consumer should type
  against.
- The `CorrectionReport` JSON schema (see below).
- The seven frozen policies' fields and their defaults (§8.2) —
  `ChunkPlannerConfig`, `RetryPolicy`, `GuardConfig`, `PairingPolicy`,
  `LossPolicy`, `ConfidencePolicy`, `RoutingPolicy`. A default change
  alters that policy's `policy_fingerprint()` and is at least MINOR, with
  a CHANGELOG entry. Five of them also feed the composite
  `config_fingerprint()` stamped into corrected XML; the two that cannot
  yet change output bytes (`ConfidencePolicy`, `RoutingPolicy`) stay out
  of it deliberately.

Anything prefixed with `_` (modules, functions, attributes) is private,
whatever module it lives in.

## `report_version` (§9)

The `CorrectionReport` carries its own schema version, decoupled from the
package version:

- **Breaking** JSON change (key removed/renamed, meaning changed) →
  bump `CORRECTION_REPORT_VERSION` **and** MAJOR-bump the package.
- **Additive** optional key → `report_version` unchanged, package MINOR.

Consumers should dispatch on `report_version`, not on the package version.

**Dispatch on the field, not on the constant** (D5). The thing to branch on
is `report.report_version` — read off the artefact you are actually holding,
which is the only thing that tells you how *that* report was written. The
library's own `CORRECTION_REPORT_VERSION` says what THIS install emits, so a
consumer comparing it against a report it just loaded learns nothing about
that report.

That is why the constant is not in `corrigenda.__all__` while
`EDIT_PROTOCOL_VERSION` is: the edit protocol's version is something a
producer must *declare*, the report's is something a reader *finds*. The
asymmetry was previously unexplained and read as an oversight. When a tool
does need the constant — a writer checking what it is about to emit — it is
importable by module path like anything else the top level does not carry:

```python
from corrigenda.core.schemas import CORRECTION_REPORT_VERSION
```

## Byte-parity discipline

Corrected-output bytes are part of the behavioural contract: golden
sha256 hashes over the non-regression corpus gate every change. A commit
that moves a golden hash must name the normative reason in its message —
"the test was updated" is never the explanation.

## Deprecation

Nothing was published before 1.0.0, so 1.0.0 ships **zero** deprecated
aliases. After 1.0.0:

1. A deprecation lands in a MINOR release: the old name keeps working,
   emits `DeprecationWarning`, and the CHANGELOG names the replacement.
2. It is removed no earlier than the **next MAJOR** release, and no
   earlier than 6 months after the deprecating release.
3. `# type: ignore`-free migration: the replacement is always available
   in the same release that deprecates the old name.

## Support window

- Python: 3.11+ (new minors may raise the floor in a MINOR release, with
  one release of notice in the CHANGELOG).
- pydantic 2.x and lxml 6.x are the supported dependency majors; bumping
  either major is a corrigenda MAJOR unless proven byte-compatible.
