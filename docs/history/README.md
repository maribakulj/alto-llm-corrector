# Historical documents — non-normative

> **The library was called `corrigenda` until 2026-08-16; it is now
> `lidenbrock`.** Every document in this directory uses the old name, and
> deliberately keeps it. They were written when that was the name, and the
> rule that governs this directory — never update it to match the code —
> is the same rule that forbids rewriting them now. So is the git history
> around them: the commits, the pull-request titles and the SHAs these
> documents cite all carry the old name, permanently.
>
> Nothing outside this directory does. The code, the package, the
> published artefact and the living documentation carry `lidenbrock` only.
> If you are reading these files to find out what something is called
> today, that is the one question they cannot answer — and never could.

Everything in this directory is **design and audit history**, kept for
provenance. These documents are frozen: they contradict each other and
the current code in places (module locations, response shapes,
directory names), and that is expected — read them for *why* a decision
was made, never for *where* code lives or *what* the API returns today.

Current, normative sources:

| Doc | Scope |
|---|---|
| `/README.md` | The app: run, deploy, environment, storage semantics |
| `/SPECS_LIB_V2.md` | Normative spec of the `corrigenda` library |
| `/packages/corrigenda/docs/` | Library guides (quickstart, formats, edit protocol, versioning) |
| `/docs/API.md` | Backend HTTP API (with the OpenAPI schema as source of truth) |
| `/SECURITY.md` | Deployment profiles, threat model, reporting |
| `/CONTRIBUTING.md` | Dev setup, CI gates |

## Déplacés ici le 2026-07-25 (consolidation des plans)

Le dépôt portait six documents de pilotage, dont trois clos qui avaient encore
l'air vivants et trois vivants qui se recouvraient avec trois numérotations
différentes. Ils ont été remplacés par **un seul plan**, `docs/PLAN.md`.

| Document | Pourquoi il est ici |
|---|---|
| `AUDIT-2026-07-13.md` | 37 findings, **tous corrigés** — relevé clos |
| `PLAN-CORRECTIONS.md` | suivi de ces 37 correctifs, **exécuté intégralement** |
| `PLAN-REMEDIATION-2026-07-15.md` | vagues 1-4 **livrées** ; seul reliquat V4.5 (revue humaine externe), repris en `P3` du plan unique |
| `PLAN-1.0-2026-07-15.md` | remplacé par `docs/PLAN.md` |
| `ROADMAP_LIB_V3.md` | remplacé par `docs/PLAN.md` |

Ces cinq documents restent utiles pour le **pourquoi** d'une décision. Ne jamais
s'en servir pour l'état courant, et ne pas les ressusciter comme plans.
