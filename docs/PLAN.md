# Corrigenda — plan de route unique

**C'est le seul document de planification vivant du dépôt.** Il remplace
`docs/history/PLAN-1.0-2026-07-15.md`, `docs/history/ROADMAP_LIB_V3.md` et la section §13
« plan de livraison » de `SPECS_LIB_V2.md`, tous trois déplacés ou marqués comme
historiques. Trois numérotations concurrentes et non ratifiées coexistaient ;
elles sont remplacées ici par une seule.

Répartition des rôles, à tenir :

- **`SPECS_LIB_V2.md`** dit ce que la bibliothèque **doit être** (contrats,
  invariants, formats). Normatif. Ne contient plus de calendrier.
- **Ce document** dit ce qui **reste à faire** et dans quel ordre.
- **`docs/audit/AUDIT-2026-07-25.md`** dit ce qui a été **constaté**, avec les
  preuves. Ne pas y ajouter de plan.
- **`docs/history/`** est gelé. Ne jamais s'y fier pour l'état courant.

Dernière mise à jour : 2026-07-25, après la première mesure d'un modèle réel
contre une vérité terrain.

---

## Objectif : `0.10.0`, pas `1.0.0`

Publier une `0.x` honnête plutôt qu'une `1.0` prématurée. Trois raisons :

1. La surface publique doit passer d'environ **95 symboles à ~8** (`S3`). C'est
   une rupture — publier `1.0` avant la gèlerait sous SemVer.
2. Les gardes ne sont pas calibrées ; le code le dit lui-même
   (`GuardConfig.vision()`, seuil « safe default, not a calibrated one »).
3. Un seul modèle, un seul profil de gardes, deux runs mesurés.

`docs/versioning.md` autorise déjà explicitement la série `0.9.x` à casser.
`1.0.0` reste conditionné à une revue humaine externe indépendante de l'API
publique (`V4.5` de l'ancien plan de remédiation, seul reliquat de ce document).

---

## Gate 0 — Licences des corpus (bloquant, non technique)

`corpus/37-GT-BNL/` et `corpus/BnF-bpt6k3265015q/` portent tous deux
« Provenance et licence — À VÉRIFIER » et sont marqués temporaires. Le JPEG de
9,2 Mo est **définitif dans l'historique git** ; une purge réelle demanderait
`git filter-repo`.

**Aucune publication n'est possible avant que ce soit tranché.** Trois issues :
confirmer le domaine public et documenter ; exclure les corpus du paquet
distribué ; purger l'historique.

→ Claude Desktop (le MCP Gallica est l'outil adapté).

---

## L — Intégrité de ligne (bloquant)

La promesse unique de cette bibliothèque est la sûreté structurelle. Un défaut
qui désactive les gardes de paire contredit l'argument de vente lui-même.

| id | item | état |
|---|---|---|
| L1 | Insécables (`\xa0`, ` `, tab) écrasées ; l'invariant de projection est aveugle car il fait `" ".join(split())` | ouvert |
| L2 | Tiret fraktur doublé par `reconstruct_textline` (`alto/_text.py:49`) | ouvert |
| L3 | Membre inter-pages gelé sur son OCR et marqué `CORRECTED` | **figé** en `xfail(strict)` — faire APRÈS `S1` |
| L4 | `<HYP CONTENT="­"/>` → `"-"` : décision ≠ octets du fichier | ouvert |
| L5 | Cas restants de détection : page vide sautée, garde orphelin ASCII-only, PART1 sans partenaire annoncé `join_with_next=True`, rejet de `PairingPolicy` silencieux, chaîne mixte jetant l'autorité `SUBS_CONTENT`, ligne vide intercalée | ouvert |
| L6 | `HYPHEN_CHARS` : ajouter `=`, U+2010, U+2011, U+2013 | ouvert |
| L7 | Découpage : `_split_for_image_cap` coupe les unités non page-locales ; granularité LINE, partenaire non adjacent coupé sans trace | ouvert |

`L1` et `L2` sont les seuls défauts qui **altèrent le texte livré sans laisser
aucune trace** — ni compteur, ni erreur. Priorité absolue du lot.

Détail et preuves : `docs/audit/AUDIT-2026-07-25.md` §3a, §3c, §3d.

---

## R — Comptabilité honnête (bloquant)

« Toute perte comptée » est une revendication d'auditabilité faite dans les docs
du projet. Elle est aujourd'hui fausse dans les deux sens.

| id | item |
|---|---|
| R1 | `SUBS_TYPE`/`SUBS_CONTENT` comptés perdus alors que `_apply_subs` les réécrit — **18 des 23** pertes « genuine » restantes sont fantômes |
| R2 | Ligne vidée : `STYLE`/`STYLEREFS` réellement perdus, non comptés |
| R3 | `<HYP>` d'une PART2 supprimé sans compteur |
| R4 | `WC`/`CC` jamais comptés en ALTO alors que PAGE compte `conf_dropped` |
| R5 | `word_order_suspected` n'est pas une perte, sortir de `format_losses` |
| R6 | `hyphen_splits` lu par personne : la seule opération destructrice assumée est invisible pour l'hôte |
| R7 | `LossPolicy(strict=True)` inopérant en ALTO (`word_count` PAGE-only) : l'armer ou documenter la restriction |

---

## S — Dette structurelle

Le mécanisme d'enlisement est identifié : `derive_hyphen_groups` a été
introduite pour unifier quatre façons de demander « qui est le partenaire », est
bien utilisée, mais **les quatre anciennes n'ont jamais été retirées**.
L'unification a atterri en ajout — cinq chemins au lieu de quatre.

**Règle : aucun correctif ne doit créer un 6ᵉ chemin.** Un correctif qui en a
besoin est le signal qu'il faut d'abord finir `S1`.

| id | item | mesure actuelle |
|---|---|---|
| S1 | Queue de l'ADR-010 : unité de première classe, pointeurs dérivés, retrait des 4 résolveurs obsolètes | 45 usages sur 5 modules, 5 résolveurs |
| S2 | Scinder `core/pipeline.py` | 3015 lignes ; `_run_impl` 294/imbr. 4 ; `_attempt_chunk` 220/imbr. 5 |
| S3 | **P3.11** — réduire la surface publique | ~95 exports pour une cible de ~8 |
| S4 | Queue de l'ADR-011 : geler les types `Source*` (l'immuabilité repose sur une copie défensive, pas sur le type) | — |
| S5 | Écrire le fichier ADR-012 : cité par le code, inexistant ; `docs/adr/README.md` s'arrête à 008 | — |

**`S3` doit précéder toute publication** : publier d'abord gèlerait 95 symboles
sous SemVer. **`S1` doit précéder `L3`.**

---

## M — Mesure

| id | item |
|---|---|
| M1 | Le chemin **inter-pages n'est mesuré par aucun run** : aucun fichier du corpus ne finit sur un mot coupé, et le banc traite chaque fichier comme un document d'une page. Construire un corpus multi-pages réel (`bpt6k3265015q` f2/f3) |
| M2 | Variance : deux runs identiques donnent 0.0252 et 0.0266 (6 %). Faire 5 runs, publier une fourchette, jamais une décimale isolée |
| M3 | Un second modèle (Anthropic est déjà câblé) pour séparer ce qui tient du système de ce qui tient du modèle |
| M4 | Récupérer les **16,5 %** de CER dus à deux normalisations systématiques (`⸗` effacé 34/34, `’`→`'` 69/69) : consigne de prompt ou normalisation inverse |
| M5 | Remplir `tests/external_corpus/pinned/` — vide aujourd'hui, et le tier téléchargé est `continue-on-error` : **aucune page externe ne bloque un merge** |
| M6 | Corpus GT : 2 paires réelles seulement dans `tests/corpus_gt/`. Sourcer de la GT publiée plutôt que la fabriquer |

---

## D — Vérité documentaire

| id | item |
|---|---|
| D1 | `SPECS_LIB_V2 §12` interdit tout pixel dans la lib ; `integrations/vision.py` fait 497 lignes avec Pillow. Amender le spec (le code est défendable, le spec ne l'a jamais reconnu) |
| D2 | `SPECS_LIB_V2 §3` : `integrations/` absent de l'arbre cible ; `§5.1` : signature `produce()` périmée |
| D3 | `CHANGELOG.md` cite `0.0021` sans le mot « oracle » à l'entrée la plus récente. Mettre le vrai chiffre en face |
| D4 | Version : `0.9.0` avec ~827 lignes sous `[Unreleased]`, dont des ruptures d'API |
| D5 | `CORRECTION_REPORT_VERSION` non exporté alors que `docs/versioning.md` dit aux consommateurs de dispatcher dessus |
| D6 | **Documenter les angles morts des gardes** pour les institutions : « 0 fallback » signifie « aucune proposition refusée », pas « rien n'a été altéré » |
| D7 | **27 références « ROADMAP V3 » dans 13 fichiers source** (67 « Phase N » au total) pointent vers un document désormais historique. `PLAN-1.0` §V4.4 et `CLAUDE.md` interdisent déjà les références de piste d'audit dans le code : les retirer ou les remplacer par la raison, pas par le numéro de phase |

---

## P — Publication

| id | item |
|---|---|
| P1 | Répétition sur TestPyPI (le workflow n'a jamais été exercé, 0 tag git) |
| P2 | Premier tag, SBOM, publier l'artefact testé |
| P3 | `1.0.0` uniquement : revue humaine externe indépendante de l'API publique |

---

## Explicitement différé — NE PAS TOUCHER

Ce sont des décisions, pas des oublis. Détail et justification dans
`docs/audit/AUDIT-2026-07-25.md` §5.

- **`OracleVisionProducer`** — pas du code mort : c'est la mesure du plancher de
  plomberie, hors ligne et gratuite. Reste le défaut du banc.
- **`write_wc`** verrouillé tant que la calibration ne passe pas.
- **`CandidateSet`**, **sérialisation seq2seq** (§5.4), **producteur
  `replace_span`** (v2.1), **remappage d'offsets `custom` PAGE** (v2.x).
- **`split_forward_link` retirant Stage A/B** — repli conservateur assumé.
- **Césure inter-pages jamais escaladée vers le VLM** — conservateur volontaire.
- **L'aveuglement sémantique des gardes** — propriété de conception. Aucun
  réglage de seuil ne ferme cette famille ; la réponse est `review_required`
  (non commencé, post-`0.10`).
- **Parité inter-formats §6.3**, byte-parity côté PAGE, fixtures eScriptorium —
  post-`0.10`.

---

## Répartition

**Claude Code CLI** — dépôt, tests, mesures : `L*`, `R*`, `S*`, `M1`-`M5`, `D3`-`D5`, `P1`-`P2`.

**Claude Desktop** — recherche, décision, documents : `Gate 0`, `M6`, `D1`, `D2`,
`D6`, `P3`, et la décision « ce que publiable veut dire ».

**Ordre recommandé :** `L1`+`L2` → `S1` → `L3` (doit tomber presque seul) → `S2`
→ `R*` → `S3` → `M*` → `P*`. `Gate 0` en parallèle, sur Desktop.

---

## Clos — déplacé dans `docs/history/`

- `AUDIT-2026-07-13.md` + `PLAN-CORRECTIONS.md` — 37 findings, exécutés intégralement.
- `PLAN-REMEDIATION-2026-07-15.md` — vagues 1-4 livrées ; seul reliquat `V4.5`,
  repris ici en `P3`.
- `PLAN-1.0-2026-07-15.md`, `ROADMAP_LIB_V3.md` — remplacés par ce document.
