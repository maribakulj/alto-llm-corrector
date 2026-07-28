# Versioning & deprecation policy

## Current series: 0.9.x (beta)

The library has never been published to an index, so the 0.9.x series is
free to break the public surface without deprecation aliases — every
break is still a deliberate act (snapshot-test change + CHANGELOG entry).
`1.0.0rc1` freezes the API; `1.0.0` is tagged only after the independent
external review of the public API required by the release plan.

**The top-level surface is provisional and will shrink before that
freeze.** `corrigenda.__all__` holds 95 symbols today, accumulated one
addition at a time rather than designed; `docs/PLAN.md` (`S3`) computed
what it should be — the transitive closure of what the façade returns,
54 — and schedules the cut for the end of the current cleanup, once the
structural work that decides the final shape has landed. A demoted
symbol is **not removed**: it stays importable from its own module (see
*What is public* below), so a migration is an import rewrite, not a
rewrite. Meanwhile the snapshot test refuses any *growth* of the list.
Treat `__all__` as an inventory until `S3` closes; the entry points
pinned by that same test are the part you can rely on today.

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
- **The submodule paths** documented in the README (`corrigenda.core.*`,
  `corrigenda.formats.alto` / `corrigenda.formats.page`,
  `corrigenda.producers.*`). Supported and documented — this is the door
  the repository itself uses (695 module-path imports against 64
  top-level ones), and the one a symbol demoted by `S3` keeps.
- The `CorrectionReport` JSON schema (see below).
- The four frozen policies' fields and their defaults (§8.2) — a default
  change alters `policy_fingerprint()` and is at least MINOR, with a
  CHANGELOG entry.

Anything prefixed with `_` (modules, functions, attributes) is private,
whatever module it lives in.

## `report_version` (§9)

The `CorrectionReport` carries its own schema version, decoupled from the
package version:

- **Breaking** JSON change (key removed/renamed, meaning changed) →
  bump `CORRECTION_REPORT_VERSION` **and** MAJOR-bump the package.
- **Additive** optional key → `report_version` unchanged, package MINOR.

Consumers should dispatch on `report_version`, not on the package version.

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
