# Architecture Decision Records

One short document per load-bearing decision: context, decision,
consequences. The rule (also in CONTRIBUTING.md): **code comments state
the invariant; ADRs, PRs and issues hold the genealogy.** When you feel
the urge to write `Audit-Fxx` or a bug history in a comment, write the
invariant in the comment and the story here.

Format: `NNN-short-slug.md`, statuses `accepted | superseded by NNN`.

| # | Decision |
|---|---|
| [001](001-line-identity-page-id-line-id.md) | Line identity is `(page_id, line_id)` everywhere |
| [002](002-sse-loss-degrades-to-polling.md) | A lost SSE stream degrades to status polling, never fails the job |
<!-- 004 left with the demo on 2026-08-16: deployment profiles are the
     web application's decision, not the library's. It lives in
     saknussemm-demo/docs/. The number is not reused — a gap is honest,
     a renumbering would break every citation ever written. -->
| [003](003-tokens-never-in-urls.md) | Capability tokens are header-only; URLs carry scoped signed credentials |
| [005](005-pipeline-one-run-per-instance.md) | `CorrectionPipeline`: one run per instance, manifest is consumed — superseded by ADR-011 slice E |
| [006](006-pipeline-emits-events-never-logs.md) | The pipeline emits events; it never logs |
| [007](007-duplicate-identities-are-refused.md) | Duplicate identities are refused, never disambiguated |
| [008](008-error-taxonomy-and-degradation.md) | Error taxonomy: one classified root; bugs fail, bad input degrades |
| [009](009-lineref-qualified-identity.md) | `LineRef`: document-wide line lookups carry a qualified identity |
| [010](010-atomic-hyphen-groups.md) | Hyphen groups: one derivation of "these lines travel together" |
| [011](011-immutable-source-decisionset.md) | Immutable source, `DecisionSet`, side-effect-free engine — supersedes ADR-005 |
| [012](012-loss-policy-and-per-line-attribution.md) | Loss policy: a format loss is a decision, and it is attributed per line |
| [013](013-fallback-reason-precedence.md) | When two passes revert the same line, the first reason is the true one |
