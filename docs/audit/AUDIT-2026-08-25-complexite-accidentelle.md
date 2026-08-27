# Audit du 2026-08-25 — complexité accidentelle

Relevé, pas un plan. Ce que la mesure a trouvé, et sur quelles preuves. Ce
qu'on en fait est dans `docs/PLAN.md`, vague `RS`.

Périmètre : le dépôt entier à `4b59394`, lu en intégralité côté `core/`,
échantillonné côté `formats/`. Aucune exécution de test pendant la lecture ;
les chiffres ci-dessous viennent d'analyses AST et de comptages.

## Les six mesures

| mesure | valeur au 2026-08-25 |
|---|---|
| lignes de code effectif (`src/`) | 9 207 (+ 5 351 docstring, + 2 351 commentaire) |
| ratio prose/code | **0,84** |
| modules dans `core/` | 42, dont 9 sous 130 lignes physiques |
| paramètres de `CorrectionPipeline.__init__` | 14 |
| modules lisant les champs pointeurs hors `pairing`/`units` | **3** |
| lignes de tests | 38 522 sur 197 fichiers, 1 302 fonctions |

## Ce qui est solide, et qu'il faut dire d'abord

- **Presque aucun mock** : 17 lignes de `monkeypatch`, 2 de `unittest.mock`
  sur 38 522. Les tests pilotent le vrai pipeline avec des producteurs
  déterministes.
- **La frontière `core` ↔ `formats` est réelle**, vérifiée en sous-processus
  par `tests/test_import_contract.py`.
- **`docs/promises.md`** documente ses propres trous, y compris une promesse
  déclarée fausse. La pratique de sensibilité par mutation y est appliquée
  promesse par promesse.
- **Aucune surarchitecture classique** : pas de factory, de registry, de
  manager ni d'injection cérémonielle. Les deux `Protocol` centraux
  (`EditProducer`, `FormatAdapter`) ont plusieurs implémentations réelles.

## Constat 1 — l'invariant « une seule dérivation » est faux (critique)

`CLAUDE.md` : « Hyphen-partner resolution has exactly two encodings and must
keep exactly two ». `core/reconcile.py` l'affirmait pour son propre module.
Soixante lignes plus bas, `_build_hyphen_pairs` (l. 72-81) rejoue la carte
rôle→slot que `pairing.forward_partner_ref` détient. `indexing._cross_page_partners`
(l. 96-97) lit les quatre champs pointeurs directement.

Comptage des accès aux champs `hyphen_*_pair_*` :

```
22  core/pairing.py     — le détenteur
13  core/units.py       — 5 lectures + 8 écritures (split_forward_link)
 6  core/reconcile.py   — _build_hyphen_pairs
 4  core/schemas/manifest.py — la déclaration
 2  core/indexing.py    — _cross_page_partners
 1  formats/alto/parser.py
```

La garde existante, `test_the_unit_projections_are_not_duplicates.py`, itère
sur exactement deux fonctions nommées à la main. Elle ne voit ni l'un ni
l'autre des deux sites ci-dessus.

`_build_hyphen_pairs` alimente `validate_llm_response(hyphen_pairs=…)`, donc
la garde d'intégrité de paire du validateur. Une divergence y serait
silencieuse : le validateur travaillerait sur une carte cohérente avec
elle-même. Aucun fichier de test ne nomme les deux fonctions.

Second point, mineur aujourd'hui : `_build_hyphen_pairs` clé sur le `line_id`
nu, ce que `ADR-001` interdit. Sûr parce que les chunks sont page-scopés —
donc sûr par circonstance, pas par construction.

## Constat 2 — les cliquets AST produisent des modules

`tests/test_orchestrator_budget.py` impose module ≤ 580 l., fonction ≤ 100 l.,
fonction ≤ 8 paramètres. Le fichier documente lui-même le premier effet de
bord : le plafond de longueur seul « récompense le défaut qu'il est censé
prévenir », `S2` ayant produit `_descend_granularity` à 12 arguments. Le
remède fut un second plafond ; `core/workspace.py` documente qu'il est né de
ce second plafond (`PageWorkspace` : 3 champs, 0 méthode, et son propre
docstring reconnaît qu'il ne rend rien immuable).

Neuf modules de `core/` font moins de 130 lignes pour une ou deux
définitions : `traces.py` (54), `workspace.py` (66), `redaction.py` (68),
`context.py` (89), `projection.py` (91), `indexing.py` (107), `finalize.py`
(117), `retry.py` (129), `decide.py` (135).

## Constat 3 — la prose est un journal de refactoring

0,84 ligne de prose par ligne de code. 121 occurrences de « used to /
historically / no longer / Measured 20xx » dans `src/`. Les modules les plus
chargés :

```
core/losses.py 4,27   core/schemas/report.py 3,30   errors.py 3,10
core/_norm.py 2,45    core/fidelity.py 2,26         core/page_alignment.py 2,18
core/decide.py 2,12   core/schemas/manifest.py 1,89 core/schemas/policies.py 1,71
```

`core/decide.py` : 85 lignes de docstring de module pour 40 lignes de code et
trois fonctions de 6, 12 et 2 lignes.

Trois catégories cohabitent et n'ont pas le même statut : l'**invariant**
(à garder), la **justification mesurée** (à garder — c'est ce qui empêche la
régression : « 27 108 paires », « 8 859 paires appariées », « 0 sur 4 752 »),
et le **récit de migration** (« It used to re-declare all thirteen »), qui a
un domicile ailleurs.

## Constat 4 — quatre représentations parallèles par ligne

`LineManifest` (22 champs, mutable), `LineTrace` (15 champs, mutable, écrite
par `setattr` dynamique), `LineDecision` (5 champs, immuable),
`LineOutcome` + trois stages (immuable, surface publique). Deux traducteurs :
`derive_decision_set`, `build_line_outcomes`. Le recopiage n'est vérifié par
aucun type ni aucun test ; le dépôt a déjà payé cette forme une fois
(`word_order_suspected` comptabilisé dans `losses`, `core/decisions.py:182`).

## Constat 5 — 21 seuils de garde non calibrés, à geler en `1.0`

`GuardConfig` expose 21 seuils publics répartis en trois étages, avec des
jumeaux délibérés (`part1_max_word_growth` 1 / `pair_drift_part1_word_growth`
2). Le docstring interdit de les dédupliquer, et ce plan écrit par ailleurs
que « les gardes ne sont pas calibrées ». On offre 21 boutons dont on dit
dans la même phrase qu'ils doivent être réglés ensemble et que leurs défauts
ne sont pas mesurés.

## Constat 6 — 17 modules pour suivre une correction

Chemin tracé pour la question de diagnostic la plus fréquente (« pourquoi
cette ligne n'a-t-elle pas été corrigée ? ») : `pipeline` → `driver` →
`routing` → `batching` → `planner` → `attempt` → `editing` → `validator` →
`hyphenation` → `outcome` → `acceptance` → `guards` → `reconcile` → `units` →
`pairing` → `decide` → `traces`, puis `finalize` → `decisions`.

Au moins **14 raisons de repli distinctes**, émises depuis 8 modules. La
liste n'existe nulle part ; elle a été reconstituée par `grep`.

## Constat 7 — 5 des 14 paramètres du pipeline pilotent des chemins inactifs

`qe_scorer`, `routing_policy`, `confidence_policy`, `confidence_scorers`,
`escalation_producer`. Le code les décrit lui-même comme « OFF by default »
et appartenant au « programme de recherche que le gel suspend ». Coût :
`core/routing.py` (218), `core/quality.py` (169), `core/confidence.py` (276),
`core/batching.py` (130), `core/page_alignment.py` (177),
`integrations/vision.py` (550), `producers/page_llm.py` (147) — 1 667 lignes
qu'aucun run par défaut n'emprunte, dont trois étapes que
`driver._plan_page_chunks` fait lire avant le cas nominal.

## Constat 8 — quatre affirmations fausses (corrigées le 2026-08-25)

1. `README.md` décrivait la démo FastAPI + React comme vivant dans ce dépôt ;
   elle est partie le 2026-08-16.
2. Cinq renvois dans `src/` à « the demo backend's staging writer ».
3. `producers/__init__.py` : « Import only `saknussemm.core` », contredit par
   `llm_edit.py` et `page_llm.py`.
4. `core/reconcile.py` : « none reads a pointer field directly » (constat 1).

Ce qui rend le lot instructif : le dépôt porte trois tests de vérité
documentaire (`test_references_resolve`, `test_a_cited_document_exists`,
`test_the_tooling_that_guards_us_actually_runs`) et **aucun** ne pouvait voir
ces quatre-là. Ils couvrent la syntaxe — un lien résout, un chemin backtické
existe — pas la sémantique. `test_a_cited_document_exists.py` avait déjà
écrit la leçon : « a guard that reads one syntax reports on one syntax ».

## Constat 9 — `RewriteResult.__iter__`, un shim que seuls les tests gardent

`core/protocols.py:412`, annoncé « Removed once the tuple call sites are
gone ». Aucun site de `src/` ne déballe ce tuple ; les ~15 appelants sont des
tests écrits contre lui. La condition de retrait est donc inatteignable.

## Constat 10 — `frozen=True` en surface

`DocumentManifest` est gelé ; ses `PageManifest`/`LineManifest` ne le sont
pas, et `LineManifest` **est** l'état de travail du run. La garantie réelle
(« l'entrée n'est jamais mutée ») vient d'un `model_copy(deep=True)` dans
`run()`, à 300 lignes de la déclaration.

## Faiblesses de test, hors constats ci-dessus

- ~3 200 lignes de tests basés sur l'AST du code source. Renommer une
  fonction privée casse `test_internal_seams_are_named` ; la déplacer casse
  `test_orchestrator_budget`.
- `tests/test_downgrade.py:35` et `tests/test_adjacent_duplicates.py:181`
  patchent `saknussemm.core.pipeline.asyncio.sleep`. `core/pipeline.py` ne
  dort pas — le back-off est en `core/attempt.py:455`. Le chemin résout vers
  le module `asyncio` global et le patche pour tout le processus.
- `core/driver.py` (465 l.) n'est nommé par aucun fichier de test. La
  descente de granularité et le budget partagé ne sont exercés qu'en bout de
  chaîne.
- `core/routing.py`, `core/preflight.py`, `core/provenance.py`,
  `core/projection.py`, `core/report.py`, `core/result.py`, `facade.py`,
  `core/events.py`, `core/indexing.py`, `core/traces.py`,
  `formats/page/adapter.py`, `integrations/page.py` : jamais nommés dans
  `tests/`, couverts indirectement.
- `docs/promises.md` s'avoue deux angles morts : « PAGE est le format
  sous-gardé » (six promesses), et « plusieurs tests d'EditScript sont
  mono-op », ce qui neutralise `E2b`, `E4a` et `E4c`.

## Ce qu'il ne faut pas toucher, et pourquoi

- **`formats/alto/rewriter.py`** — chaque branche porte un cas réel
  (`_NO_BREAK_SPACES` existe parce qu'un `<SP>` détruit une espace
  insécable). Le plan l'a déclaré hors-limites jusqu'à élargissement du
  corpus byte-parity.
- **`core/pairing.py`** — `forward_break_is_explicit` cite la ligne
  `PAG_00000002_TL000454` d'`examples/X0000002.xml` : lire le mauvais
  drapeau faisait disparaître le tiret du fichier livré.
- **`guards._similarity`, `autojunk=False`** — mesuré sur 27 108 paires, coût
  0,7 %, et un test dédié le garde.
- **`planner._try_window`** — le clamp de progression porte un cas reproduit
  (`model_copy(update=…)` contourne la validation pydantic).
- **`core/redaction.py`** — sécurité, 68 lignes, ordre des motifs
  significatif.

## Symptômes de surproduction assistée

Nommés parce qu'un relevé doit dire ce qu'il a vu, sans conclusion sur
l'origine : docstrings longues au rapport information/mots faible,
justification symétrique de chaque décision y compris triviale,
prolifération de modules à responsabilité très fine chacun préfacé d'un
exposé, instrumentation méta récursive (des tests qui testent les tests), ton
uniforme du `CHANGELOG` aux commentaires.

Contre-indices, sérieux : les mesures citées sont concrètes et vérifiables,
et le dépôt documente ses propres échecs (« fermée à tort le 2026-08-16,
rouverte », une promesse déclarée fausse, « un test épinglait la mauvaise
lecture comme comportement attendu »). Lecture retenue : un vrai travail
d'ingénierie dont la couche narrative est surproduite.
