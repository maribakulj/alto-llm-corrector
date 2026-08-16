# Historical documents — non-normative

> **The library has been called three things, and this directory uses the
> first.** It was `corrigenda` until 2026-08-16, briefly `lidenbrock` that
> same day, and is `saknussemm` now.
>
> Every document here says `corrigenda`, deliberately. They were written
> when that was the name, and the rule that governs this directory — never
> update it to match the code — is the same rule that forbids rewriting
> them now.
>
> The git history says all three, and permanently: the commits and
> pull-request titles of 2026-08-16 carry `lidenbrock` because that is what
> the library was called for the few hours they were written. Rewriting
> them would break every SHA these documents cite, which is a real cost
> against no benefit — a name in a commit message misleads nobody who knows
> there were two renames, and this paragraph is where they find out.
>
> Nothing outside this directory carries an old name. The code, the
> package, the published artefact and the living documentation say
> `saknussemm` only. If you are reading these files to learn what something
> is called today, that is the one question they cannot answer — and never
> could.

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
