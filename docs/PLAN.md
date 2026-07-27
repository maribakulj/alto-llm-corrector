# Corrigenda — plan de route unique

**C'est le seul document de planification vivant du dépôt.** Il remplace
`docs/history/PLAN-1.0-2026-07-15.md`, `docs/history/ROADMAP_LIB_V3.md` et la section §13
« plan de livraison » de `SPECS_LIB_V2.md`, tous trois déplacés ou marqués comme
historiques. Ne pas en écrire un second ; ne pas ressusciter les anciens.

Répartition des rôles, à tenir :

- **`SPECS_LIB_V2.md`** dit ce que la bibliothèque **doit être** (contrats,
  invariants, formats). Normatif. Ne contient plus de calendrier.
- **Ce document** dit ce qui **reste à faire** et dans quel ordre.
- **`docs/audit/`** dit ce qui a été **constaté**, avec les preuves. N'y ajouter
  aucun plan. Deux relevés courants : `AUDIT-2026-07-25.md` (première mesure
  réelle) et `AUDIT-2026-07-27.md` (contre-audit d'une analyse externe).
- **`docs/history/`** est gelé. Ne jamais s'y fier pour l'état courant, et ne
  jamais y renvoyer depuis un document normatif.

Dernière mise à jour : 2026-07-27, après contre-audit d'une analyse externe.
Cette révision **ne change pas le diagnostic** du 25 juillet — elle relève le
niveau de trois réponses (`L`, `S1`, tests), ajoute quatre items de vérité
documentaire, et écrit la règle de gel.

---

## Objectif : `0.10.0`, puis `1.0.0` — jamais l'inverse

Publier une `0.x` honnête plutôt qu'une `1.0` prématurée. Trois raisons
inchangées :

1. La surface publique doit passer de **95 symboles à sa clôture minimale**
   (`S3`). C'est une rupture — publier `1.0` avant la gèlerait sous SemVer.
2. Les gardes ne sont pas calibrées ; le code le dit lui-même
   (`GuardConfig.vision()`, seuil « safe default, not a calibrated one »).
3. Un seul modèle, un seul profil de gardes, deux runs mesurés.

`docs/versioning.md` autorise déjà explicitement la série `0.9.x` à casser.

### Ce que « v1 propre » veut dire

`1.0.0` n'est **pas** la fin de la liste ci-dessous ; c'est un ensemble de
propriétés tenables. Critères de sortie, à ne pas négocier à la baisse :

| # | critère | vérifié par |
|---|---|---|
| V1 | Aucune altération du texte livré qui ne soit **déclarée et comptée** | `L*` fermés, échelle de fidélité au rapport |
| V2 | La comptabilité des pertes ne produit **ni fantôme ni angle mort** | `R*` fermés, matrice versionnée |
| V3 | Une **seule** définition de l'unité de césure dans tout le code | `S1` fermé, 1 résolveur |
| V4 | Ce que le système **ne peut pas** établir est signalé, pas décidé | `review_required` livré (`G*`) |
| V5 | La surface publique est la clôture de ce que la façade retourne | `S3` fermé |
| V6 | Toute revendication chiffrée est un **intervalle**, sur ≥2 familles de modèles, dont le chemin inter-pages | `M*` fermés |
| V7 | Un corpus externe versionné **bloque** un merge | `M5` fermé |
| V8 | Aucun document normatif ne renvoie vers `docs/history/` ni ne décrit un périmètre faux | `D*` fermés |
| V9 | Licences des corpus tranchées | `Gate 0` |
| V10 | Revue humaine externe indépendante de l'API publique | `P3` |

`V1`-`V3`, `V8`, `V9` sont exigibles dès `0.10.0`. `V4`-`V7`, `V10` sont la
distance restante entre `0.10.0` et `1.0.0`.

---

## Règle de gel — applicable immédiatement

**Aucune fonctionnalité nouvelle tant que `L*` et `R*` ne sont pas fermés.**

Suspendu : nouveau producteur, nouveau format, nouvelle politique de routage,
optimisation de coût, écriture des confiances (`write_wc`), extension de l'API
publique.

Autorisé : correctifs, refactorisation **réductrice**, corpus, mesure,
documentation de vérité, tests.

Corollaire déjà en vigueur, conservé : **aucun correctif ne doit créer un 6ᵉ
chemin de résolution de partenaire.** Un correctif qui en a besoin est le signal
qu'il faut d'abord finir `S1`.

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
qui altère le texte livré sans trace contredit l'argument de vente lui-même.

**Changement d'approche depuis le 25 juillet.** `L1`, `L2`, `L4` et `L6` étaient
listés comme quatre correctifs indépendants. Ce sont quatre symptômes de deux
absences de modèle. Les traiter séparément recrée le mécanisme d'enlisement
décrit en `S` : quatre correctifs, quatre chemins de plus.

### L0 — Échelle de fidélité de projection *(prérequis de L1, L4)*

`_projection_normal_form` (`pipeline.py:280`) fait `" ".join(text.split())` :
l'invariant censé détecter une divergence entre décision et XML est aveugle à
une classe de divergences que le moteur **produit effectivement**. C'est le
défaut le plus grave du dépôt : il touche le mécanisme de crédibilité lui-même.

Le remède n'est pas de durcir l'invariant — `EXACT_XML_TEXT` est **inatteignable
en ALTO** (`<SP>` ne porte pas de contenu ; un blanc de bord n'a aucune
représentation). Le remède est de rendre le niveau atteint **explicite,
déclaré et journalisé au rapport** :

- une échelle ordonnée, de l'ordre de `EXACT_XML_TEXT` → `TOKEN_EQUIVALENT`
  → `NORMALIZED_DISPLAY` ;
- le niveau **visé** est une politique ; le niveau **atteint** est une donnée du
  rapport, par ligne agrégée par run ;
- toute descente d'un niveau est **comptée** (elle rejoint `R`) ;
- `" ".join(split())` cesse d'être l'invariant universel et devient
  la comparaison d'**un** niveau nommé.

### L1 — Blancs significatifs écrasés *(dépend de L0)*

U+00A0 et **U+202F** (espace fine insécable — l'espace typographique française
avant `%`, `;`, `!`, `?`, `:`, le cas le plus fréquent sur le corpus visé) sont
avalés par `\s` dans `_tokenize` (`alto/rewriter.py:56`) et ré-émis en `<SP>`
ordinaire. L'invariant ne le voit pas.

Le `.strip()` du chemin lent (`rewriter.py:617`) relève du **même** remède, pas
d'un correctif propre : sa raison technique (le pavage `HPOS` des enfants de
ligne) est valide et documentée. Ce qui manque est la déclaration, pas le
comportement.

### L2 — Signe de coupure comme donnée *(remplace « L2 + L4 + L6 »)*

Tant que le signe est redécouvert tardivement par `endswith(...)`, chaque
caractère ajouté au répertoire est un nouveau site de bug. Les trois défauts
connus **sont** ce bug :

- tiret fraktur doublé — `alto/_text.py:49` ne déduplique que sur `"-"` ;
- `<HYP CONTENT="­"/>` → `"-"` — décision ≠ octets du fichier (`_text.py:47`) ;
- `HYPHEN_CHARS` = `("-", "¬", "⸗", "­")` — manquent `=`, U+2010, U+2011, U+2013.

Porter le signe explicitement — codepoint source, rôle logique, forme rendue,
présence d'un balisage explicite — les fait tomber **par construction**. Cette
structure appartient à l'unité de césure de `S1` : `L2` et `S1` se font ensemble
ou dans cet ordre, jamais en parallèle.

### L3 — Membre inter-pages gelé sur son OCR

**Figé** en `xfail(strict)` (`test_cross_page_hyphen_decision.py`). La première
ligne de toute page qui continue un mot coupé n'est jamais corrigée, l'appel
modèle est facturé, et le statut `CORRECTED` la rend invisible aux compteurs de
fallback.

**À faire APRÈS `S1`** — le défaut vient de l'ambiguïté de propriété d'une unité
répartie sur deux pages, pas d'une erreur locale. Il doit tomber presque seul ;
basculer le test en normal au XPASS.

### L5 — Cas restants de détection

Page vide sautée ; garde orphelin ASCII-only ; PART1 sans partenaire annoncé
`join_with_next=True` au modèle ; rejet de `PairingPolicy` silencieux ; chaîne
mixte jetant l'autorité `SUBS_CONTENT` ; ligne vide intercalée capturant PART2 ;
cross-bloc en ordre de lecture dégradé ; `link_cross_page_hyphens` ne regardant
que `lines[-1]`/`lines[0]`.

### L7 — Découpage

`_split_for_image_cap` coupe les unités non page-locales ; granularité LINE,
partenaire non adjacent coupé sans trace `HyphenSplit` ; la descente de
granularité ne rapatrie pas les partenaires non-cibles.

Détail et preuves : `AUDIT-2026-07-25.md` §3a, §3c, §3d ; `AUDIT-2026-07-27.md`
§2.6, §3.1, §3.2, §4.3, §4.4.

---

## R — Comptabilité honnête (bloquant)

« Toute perte comptée » est une revendication d'auditabilité faite dans les docs
du projet. Elle est aujourd'hui fausse **dans les deux sens** — ce qui est pire
qu'une absence de comptabilité, parce que le chiffre a l'apparence d'une
garantie.

| id | item |
|---|---|
| R0 | **Matrice versionnée** : pour chaque format × attribut, dire s'il est conservé, invalidé, recalculé, supprimé ; comment la suppression est comptée ; ce que fait `strict`. Les compteurs actuels sont apparus au fil des correctifs — la matrice précède `R1`-`R7`, elle ne les résume pas |
| R1 | `SUBS_TYPE`/`SUBS_CONTENT` comptés perdus alors que `_apply_subs` les réécrit — **18 des 23** pertes « genuine » restantes sont fantômes |
| R2 | Ligne vidée : `STYLE`/`STYLEREFS` réellement perdus, non comptés |
| R3 | `<HYP>` d'une PART2 supprimé sans compteur |
| R4 | `WC`/`CC` jamais comptés en ALTO alors que PAGE compte `conf_dropped` |
| R5 | `word_order_suspected` n'est pas une perte, sortir de `format_losses` |
| R6 | `hyphen_splits` lu par personne : la seule opération destructrice assumée est invisible pour l'hôte |
| R7 | `LossPolicy(strict=True)` inopérant en ALTO (`word_count` PAGE-only) : l'armer ou documenter la restriction |
| R8 | Brancher la descente de niveau de fidélité `L0` sur la comptabilité : une perte de blanc significatif est une perte |

---

## S — Dette structurelle

Le mécanisme d'enlisement est identifié : `derive_hyphen_groups` a été
introduite pour unifier quatre façons de demander « qui est le partenaire », est
bien utilisée, mais **les quatre anciennes n'ont jamais été retirées**.
L'unification a atterri en ajout — cinq chemins au lieu de quatre.

| id | item | mesure actuelle | cible |
|---|---|---|---|
| S1 | Queue de l'ADR-010 : **unité de césure de première classe** — membres ordonnés, pages, type explicite/heuristique, autorité `SUBS_CONTENT`, signe physique (`L2`), état, décision atomique, projection par format. Pointeurs dérivés, jamais mutables séparément. Retrait des 4 résolveurs obsolètes | 45 usages / 5 modules, **5** résolveurs | **1** résolveur, 0 pointeur mutable |
| S2 | Scinder `core/pipeline.py` en composants nommés — préflight, planification, routage, exécution de chunk, validation, acceptation, réconciliation d'unités, projection, assemblage du rapport. Le pipeline public **orchestre**, il ne réimplémente pas | **3015** lignes ; `_run_impl` 294/imbr. 4 ; `_attempt_chunk` 220/imbr. 5 | fichier principal < 800 l., aucune méthode > 100 l., assemblage du rapport indépendant du contrôle d'exécution |
| S3 | Réduire la surface publique. **La cible n'est pas « 8 » mais la clôture transitive de ce que la façade retourne** : `load`/`correct`/`correct_sync` + `LoadedDocument`, `CorrectionResult`, `CorrectionReport`, `DecisionSet`, `LineDecision`, `LineRef`, `EditProducer`, les policies injectables, `CorrigendaError`, `CORRECTION_REPORT_VERSION`, `__version__`. Le reste reste importable depuis son module, sans être façade | **95** exports | clôture arrêtée et gelée |
| S4 | Queue de l'ADR-011 : geler les types `Source*` (l'immuabilité repose sur une copie défensive, pas sur le type) | — | — |
| S5 | Écrire `docs/adr/012-*.md` : cité par le code, inexistant ; `docs/adr/README.md` s'arrête à 008 alors que 009-011 existent | — | — |

**`S3` doit précéder toute publication** : publier d'abord gèlerait 95 symboles
sous SemVer. **`S1` doit précéder `L3`**, et porte `L2`.

---

## T — Programme de tests (nouveau)

868 fonctions de test bibliothèque, 400 backend — et les deux défauts
d'intégrité de ligne du 25 juillet sont sortis de la **mesure**, pas de la
relecture ni des tests. La cause est identifiée : les fixtures portaient les
`SUBS_TYPE` explicites qui évitaient précisément le chemin heuristique cassé.
**La population de tests est trop proche des abstractions du code.**

Ajouter des tests unitaires ne referme pas cet écart. Trois familles :

| id | item |
|---|---|
| T1 | **Métamorphiques** — même document découpé autrement → même décision (seul cas existant, `fcd7804`) ; mêmes pages regroupées autrement → même décision ; même césure intra-page ou inter-pages → même résultat logique ; page vide ajoutée → aucune autre décision ne bouge ; signe de coupure substitué par un équivalent autorisé → unité conservée |
| T2 | **Corpus adversarial** — le corpus de formes qui n'existe pas : U+00A0 et U+202F, gamme complète des tirets, chaînes de 3-4 membres, césure inter-pages réelle, lignes sans `SUBS_TYPE`, lignes vides et éléments non textuels intercalés, ALTO de plusieurs producteurs, PAGE Transkribus et eScriptorium réels |
| T3 | **Différentiels** — comparer décision logique, texte réextrait, octets XML, attributs conservés, géométrie, compteurs de perte et statut de ligne. « Le XML est valide » n'est pas le résultat attendu |

`T2` alimente `M5` (le corpus épinglé bloquant) : c'est le même corpus.

---

## G — Ce que le système ne peut pas établir (post-`0.10`, requis pour `1.0`)

Les gardes comparent des caractères et n'ont **aucune notion de sens** : sur 12
contre-exemples passés dans la vraie `check_line`, tous acceptés aux deux seuils
— dont une négation supprimée (0.8955), une date changée (0.9388), un montant
tronqué (0.9643) et la copie verbatim d'une ligne voisine (0.8852).
**Aucun réglage de seuil ne ferme cette famille** ; c'est une propriété de
conception, pas un bug à corriger par des seuils.

Un détecteur empirique a levé 56 lignes à chiffres modifiés sur le run réel : la
quasi-totalité étaient de **bonnes** corrections, ce qui n'a pu être déterminé
qu'avec la vérité terrain. En production il n'y en a pas.

| id | item |
|---|---|
| G1 | État `review_required`, distinct de `CORRECTED` / `FALLBACK` / `FAILED` |
| G2 | Règles conservatrices d'envoi en revue : chiffres, dates et montants modifiés ; négation modifiée ; nom propre probable ; **substitution systématique au niveau du run** (le cas `⸗` 34/34 et `’` 69/69 — invisible ligne à ligne, évident au run) ; signe typographique supprimé sur toutes ses occurrences ; ligne propre modifiée ; désaccord producteur texte / producteur vision ; confiance non calibrée sous seuil |
| G3 | Le système ne prétend pas décider si le changement est correct — seulement reconnaître qu'il n'a pas les moyens de l'établir. À documenter comme tel (`D6`) |

---

## M — Mesure

| id | item |
|---|---|
| M1 | Le chemin **inter-pages n'est mesuré par aucun run** : aucun fichier du corpus ne finit sur un mot coupé, et le banc traite chaque fichier comme un document d'une page. Construire un corpus multi-pages réel (`bpt6k3265015q` f2/f3) |
| M2 | Variance : deux runs identiques donnent 0.0252 et 0.0266 (6 %). **≥5 runs par configuration, publier une fourchette, jamais une décimale isolée** |
| M3 | **≥2 familles de modèles** (Anthropic est déjà câblé) pour séparer ce qui tient du système de ce qui tient du modèle |
| M4 | Récupérer les **16,5 %** de CER dus à deux normalisations systématiques (`⸗` effacé 34/34, `’`→`'` 69/69) : consigne de prompt ou normalisation inverse. Feed direct de `G2` |
| M5 | Remplir `tests/external_corpus/pinned/` — vide aujourd'hui (un `README.md`), et le tier téléchargé est `continue-on-error` : **aucune page externe ne bloque un merge**. Le corpus épinglé permet de bloquer sans dépendre de gallica.bnf.fr ; c'est le corpus de `T2` |
| M6 | Corpus GT : 2 paires réelles seulement dans `tests/corpus_gt/`. Sourcer de la GT publiée plutôt que la fabriquer |
| M7 | Rendre publiables : CER **et** WER, lignes améliorées / dégradées / faux positifs, **analyse par classe Unicode**, et mesure séparée sur OCR mauvais / moyen / déjà propre. Re-mesurer après `542c783` (24 césures `⸗` entrées dans l'appariement depuis le run) |

Aucune revendication de qualité ne sort du dépôt sans `M2` + `M3`.

---

## D — Vérité documentaire

Le 25 juillet a consolidé `docs/` ; **les documents d'entrée n'ont pas suivi**.
`D8`-`D11` sont les trois portes par lesquelles un lecteur arrive.

| id | item |
|---|---|
| D1 | `SPECS_LIB_V2 §12` interdit tout pixel dans la lib ; `integrations/vision.py` fait 497 lignes avec Pillow. Amender le spec : le **cœur** est aveugle aux pixels, la **distribution de base** n'importe pas Pillow, l'extra `corrigenda[vision]` traite effectivement les pixels. Corriger la même phrase dans `packages/corrigenda/README.md:36` |
| D2 | `SPECS_LIB_V2 §3` : `integrations/` absent de l'arbre cible ; `§5.1` : signature `produce()` périmée |
| D3 | `CHANGELOG.md` cite `0.0021` sans le mot « oracle » à l'entrée la plus récente. Mettre le vrai chiffre en face |
| D4 | **827 lignes** sous `[Unreleased]` pour **0 tag git** : le seul récit continu des ruptures d'API est dans une section que SemVer déclare non engageante |
| D5 | `CORRECTION_REPORT_VERSION` non exporté alors que `docs/versioning.md` dit aux consommateurs de dispatcher dessus |
| D6 | **Documenter les angles morts des gardes** pour les institutions : « 0 fallback » signifie « aucune proposition refusée », **pas** « rien n'a été altéré » |
| D7 | Références d'historique dans le code — **deux fois plus lourdes que mesurées** : `src/`+`app/` 28 `ROADMAP V3` / 70 `Phase N` / 25 `Audit-F` / 17 `Wave`, et **les tests en portent autant** (33 / 56 / 4 / 9). Retirer ou remplacer par la **raison**, jamais par le numéro. Inclut `packages/corrigenda/docs/format-support.md:3` — un document courant qui date son autorité d'un document gelé |
| D8 | **`README.md` annonce ALTO seul** alors que PAGE est supporté de bout en bout (lib, backend `jobs.py:257`, XSD 2013/2019/2024). Corriger le titre, l'accroche et la section d'usage |
| D9 | **La carte documentaire du `README.md` omet `docs/PLAN.md` et `docs/audit/`** : le plan unique n'est nommé que dans `CLAUDE.md`. Un contributeur voit `docs/history/` signalé comme gelé et ne voit jamais ce qui l'a remplacé |
| D10 | **`SECURITY.md` renvoie vers `docs/history/PLAN-REMEDIATION-2026-07-15.md`** (Vague 5) pour propriété de job / quotas / persistance — un document normatif pointant vers l'historique gelé, sur la question même qui décide de l'adoption institutionnelle |
| D11 | **Le frontend dit ALTO seul** (`App.tsx:266,483`, `DownloadButton.tsx:82`) : un utilisateur PAGE emprunte un chemin qui marche et n'est étiqueté nulle part |
| D12 | Renommer le profil `institutional` → `proxy_protected` (ou équivalent) : le corps de `SECURITY.md` est honnête, le **nom** travaille contre son texte. Variable d'environnement publique → période de dépréciation |

---

## P — Publication

| id | item |
|---|---|
| P1 | Répétition sur TestPyPI (le workflow n'a jamais été exercé, 0 tag git) |
| P2 | Premier tag `0.10.0`, SBOM, publier l'artefact testé |
| P3 | `1.0.0` uniquement : revue humaine externe indépendante de l'API publique, après `V1`-`V9` |

---

## Explicitement différé — NE PAS TOUCHER

Ce sont des décisions, pas des oublis. Détail et justification dans
`AUDIT-2026-07-25.md` §5.

- **`OracleVisionProducer`** — pas du code mort : c'est la mesure du plancher de
  plomberie, hors ligne et gratuite. Reste le défaut du banc.
- **`write_wc`** verrouillé tant que la calibration ne passe pas.
- **`CandidateSet`**, **sérialisation seq2seq** (§5.4), **producteur
  `replace_span`** (v2.1), **remappage d'offsets `custom` PAGE** (v2.x).
- **`split_forward_link` retirant Stage A/B** — repli conservateur assumé.
- **Césure inter-pages jamais escaladée vers le VLM** — conservateur volontaire.
- **L'aveuglement sémantique des gardes** — propriété de conception. Aucun
  réglage de seuil ne ferme cette famille ; la réponse est `G*`, post-`0.10`.
- **Parité inter-formats §6.3**, byte-parity côté PAGE, fixtures eScriptorium —
  post-`0.10`.

---

## Répartition

**Claude Code CLI** — dépôt, tests, mesures : `L*`, `R*`, `S*`, `T*`, `G1`-`G2`,
`M1`-`M5`, `M7`, `D3`-`D5`, `D7`-`D11`, `P1`-`P2`.

**Claude Desktop** — recherche, décision, documents : `Gate 0`, `M6`, `D1`, `D2`,
`D6`, `D12`, `G3`, `P3`.

### Ordre

**Lot 0 — vérité documentaire, sans risque, immédiat.** `D8`, `D9`, `D10`
ferment trois mensonges de façade en quelques lignes et ne dépendent de rien.
`D11` suit. À faire avant le reste, parce que chaque jour où ils restent est un
lecteur trompé.

**Lot 1 — intégrité (bloquant `0.10`).** `L0` → `L1` → `S1`+`L2` ensemble →
`L3` (doit tomber presque seul) → `L5`, `L7`.

**Lot 2 — honnêteté (bloquant `0.10`).** `R0` d'abord, puis `R1`-`R8`. `S2` peut
s'intercaler ici : la comptabilité est plus facile à réparer une fois le rapport
assemblé hors du contrôle d'exécution.

**Lot 3 — réduction (bloquant publication).** `S3`, `S4`, `S5`, `D7`, `D4`,
`D5`. Puis `P1`, `P2` → **`0.10.0`**.

**Lot 4 — vers `1.0`.** `T1`-`T3` et `M5` en continu dès le lot 1 (ils trouvent
les défauts des lots suivants) ; `M1`-`M3`, `M7` ; `G1`-`G3` ; `D12` ; `P3`.

`Gate 0` en parallèle sur Desktop, du premier jour au dernier — c'est le seul
item qui peut bloquer `P2` sans avertissement.

---

## Clos — déplacé dans `docs/history/`

- `AUDIT-2026-07-13.md` + `PLAN-CORRECTIONS.md` — 37 findings, exécutés intégralement.
- `PLAN-REMEDIATION-2026-07-15.md` — vagues 1-4 livrées ; seul reliquat `V4.5`,
  repris ici en `P3`.
- `PLAN-1.0-2026-07-15.md`, `ROADMAP_LIB_V3.md` — remplacés par ce document.
