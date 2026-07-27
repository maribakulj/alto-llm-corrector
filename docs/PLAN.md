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
| V3 | Une **seule** définition de l'unité de césure dans tout le code | `S1` fermé : 1 primitive dirigée + 1 dérivation d'unité |
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

**État : `L0`, `L1`, `L2`, `L3`, `L9` faits ; `L4` retiré.** Les deux défauts qui
altéraient le texte livré sans laisser **aucune** trace — ni compteur, ni
erreur — sont fermés. `L4` s'est révélé faux à la vérification (§4.5 de
l'audit du 27) et laisse à sa place `L8`. `L3` est fermé, et l'a fait tomber
`L9`. Restent `L5`, `L6`, `L7`, `L8`.

### L0 — Échelle de fidélité de projection — **fait** *(prérequis de L1, L4)*

`_projection_normal_form` (`pipeline.py:280`) fait `" ".join(text.split())` :
l'invariant censé détecter une divergence entre décision et XML est aveugle à
une classe de divergences que le moteur **produit effectivement**. C'est le
défaut le plus grave du dépôt : il touche le mécanisme de crédibilité lui-même.

Le remède n'était pas de durcir l'invariant — `exact` est **inatteignable en
ALTO** pour une partie des cas (`<SP>` ne porte pas de contenu ; un blanc de
bord n'a aucune représentation). Il était de rendre le niveau atteint
**explicite, déclaré et journalisé au rapport**.

Livré (`core/fidelity.py`, 100 % couvert ; 31 tests) :

- échelle ordonnée `exact` → `token_equivalent` → `normalized`, chaque niveau
  distinguant ce que le **format coûte** (`<SP>` ne porte pas de contenu : une
  suite d'espaces et un blanc de bord ne peuvent pas survivre) de ce qui a été
  **substitué** (U+00A0, U+202F, tabulation aplatis en espace ordinaire) ;
- le niveau atteint est une donnée du rapport : `ProjectionStage.fidelity` par
  ligne, `CorrectionReport.projection_fidelity` par run (comptage par niveau).
  Champs additifs et optionnels — pas de bump de `CORRECTION_REPORT_VERSION` ;
- `" ".join(split())` a cessé d'être l'invariant universel : la divergence de
  **mots** lève toujours `ProjectionError`, tout le reste est classé et compté ;
- U+202F est couvert nommément.

Reste ouvert, volontairement :

- **le niveau *visé* comme politique.** Le plan le prévoyait ; l'ajouter
  maintenant étendrait la surface publique en pleine réduction (`S3`) et
  pendant le gel. Le plancher reste « les mots doivent correspondre »,
  inchangé. À rouvrir quand `S3` a arrêté la clôture d'API.
- **le branchement sur les compteurs de perte** — c'est `R8`, Lot 2.

### L1 — Blancs significatifs écrasés — **fait**

U+00A0 et **U+202F** (espace fine insécable — l'espace typographique française
avant `%`, `;`, `!`, `?`, `:`, le cas le plus fréquent sur le corpus visé)
étaient avalés par `\s` dans `_tokenize` (`alto/rewriter.py`) et ré-émis en
`<SP>` ordinaire, qui ne porte aucun contenu.

Correctif : **le tokeniseur ne scinde plus que sur les blancs sécables.** Un
blanc insécable est par définition un endroit où l'on ne coupe pas — sa place
est *à l'intérieur* du `String`, où il traverse l'aller-retour verbatim. Le
répertoire (`_NO_BREAK_SPACES`) : U+00A0, U+202F, U+2007. La classification
d'un token « espace » ne passe plus par `str.strip()`, qui considère un
insécable comme un blanc et le renvoyait donc en `<SP>` — c'était la
substitution elle-même.

Mesuré par `L0`, avant/après, sur le même chemin : U+00A0 et U+202F passent de
`normalized` à `exact`. La tabulation reste `normalized` — c'est une véritable
occasion de coupure, elle n'a pas de représentation ALTO, et le rapport le dit
maintenant au lieu de se taire.

Le `.strip()` du chemin lent est **clos** par `L0` : sa raison technique (le
pavage `HPOS` des enfants de ligne) est valide et documentée, et un blanc de
bord n'a aucune représentation en ALTO. Il sort désormais en
`token_equivalent`, déclaré. Ce qui manquait était la déclaration, pas le
comportement.

Reste ouvert : **le même travail côté PAGE.** `formats/page/rewriter.py` n'a
pas été audité pour cette classe ; PAGE porte son texte dans un nœud
`Unicode`, donc le mode de perte n'est pas le même et peut très bien ne pas
exister. À vérifier, pas à supposer.

### L2 — Signe de coupure doublé — **fait**

La déduplication qui empêche `String "Ober-"` + `HYP "-"` de rendre `Ober--` ne
testait que le tiret ASCII. Tous les autres signes du répertoire doublaient :
`Ober⸗` + `HYP "⸗"` se relisait `Ober⸗⸗`, `Ober¬` en `Ober¬¬`.

Silencieux parce que `reconstruct_textline` alimente **les deux côtés** de
l'invariant de projection — le `ocr_text` du parseur et la comparaison
UNTOUCHED du réécrivain : une erreur ici est commise identiquement des deux
côtés et se compare égale à elle-même. Ni `L0` ni aucun compteur ne pouvaient
la voir.

Correctif : la déduplication porte sur le répertoire (`_DEDUP_MARKS`), pas sur
`"-"`.

**Portée honnête** : aucun document des corpus du dépôt ne déclenche ce défaut
— vérifié, `corpus/37-GT-BNL` et `examples/X0000002.xml` n'ont aucune
combinaison `String`-avec-signe + `HYP`. C'est un chemin de corruption
silencieuse **latent**, reproduit synthétiquement par l'audit du 25. Réel, à
fermer, mais il ne faut pas lui prêter un effet mesuré qu'il n'a pas.

### L4 — U+00AD → `-` : **retiré, le constat était faux**

Le plan disait « décision ≠ octets du fichier ». Vérification faite, les octets
ne divergent pas : la collapse porte sur le texte *logique*, elle est
délibérée et documentée (`core/_norm.clean_content`, même raison), et les
chemins de réécriture réémettent le `<HYP>` d'origine avec son propre
`CONTENT` — le caractère source survit sur le disque.

Et elle est **portante** : 115 lignes de `examples/X0000002.xml` portent leur
signe dans le `<HYP>` seul, en U+00AD. Sans la collapse elles ne finissent pas
sur un caractère de coupure et ne s'apparient pas. Tenter de « corriger » ceci
casse dix tests dont la parité d'octets du seul corpus BnF du dépôt.

Ce qui reste, et qui n'est **pas** ce que disait `L4` : la normalisation n'est
déclarée nulle part. C'est un événement de classe `normalized` au sens de `L0`,
sur un caractère qui n'est pas un blanc → nouvel item `L8`.

Preuve et détail : `AUDIT-2026-07-27.md` §4.5.

### L8 — Étendre l'échelle de fidélité aux substitutions hors blancs

`L0` classe les substitutions de **blancs**. Une substitution de caractère
non-blanc délibérée — la collapse U+00AD (`L4`), et le `preserve_break_char`
de `pairing.py` — ne remonte nulle part. Même remède, même échelle : déclarer
plutôt que taire. Prérequis de `R8` (une substitution déclarée est une perte
comptable).

### L6 — Répertoire de coupure incomplet

`HYPHEN_CHARS` = `("-", "¬", "⸗", "­")` — manquent `=`, U+2010, U+2011, U+2013.

**Ne pas élargir sans mesure.** Ajouter U+2013 (tiret demi-cadratin) fait
apparier des lignes qui ne le sont peut-être pas ; `trailing_hyphen_char`
exige déjà un caractère alphabétique avant le signe, ce qui écarte `1789–`,
mais pas tout. Le répertoire est un paramètre à effet de corpus : il relève de
`M7` (mesure par classe Unicode), pas d'un ajout de tuple.

Porter le signe comme **donnée** dans l'unité de césure (codepoint source,
rôle logique, forme rendue, balisage explicite ou non) reste la bonne
structure, et appartient à `S1`.

### L3 — Membre inter-pages gelé sur son OCR — **fait**

Le réconciliateur possédait un join depuis sa **queue** : il réconciliait si la
queue était une cible du chunk. Pour une paire intra-page, très bien — les deux
membres sont en portée ensemble. Pour une paire **inter-pages**, c'était
inatteignable : la queue est toujours sur la page antérieure et décidée avant
que la tête n'existe, donc la passe de la queue lisait le texte de la tête dans
une réponse qui ne la mentionnait pas, retombait sur l'OCR brut, et écrivait ça
comme décision de la tête avec `status = CORRECTED`. La page suivante sautait
alors la ligne (`corrected_text is not None`) et jetait la correction qu'elle
venait de payer.

Correctif : **un join qui quitte la page appartient à sa tête** — le seul point
où les deux côtés existent.

Ce qui a rendu ça possible : `pairing.backward_partner_ref`, le miroir de
`forward_partner_ref`. Que cette direction n'ait **jamais eu de nom** est la
cause, pas un détail : sans arête entrante nommée, un join ne pouvait
appartenir qu'à sa queue. Les deux `xfail(strict)` sont passés en XPASS et sont
devenus des tests ordinaires.

Effet de bord requis : `_reconcile_one_pair` préfère désormais
`corrected_text` du côté queue — une queue inter-pages porte sa décision sur le
manifeste, pas dans la réponse du chunk courant.

### L9 — Une paire révoquée était rapportée `corrected` — **fait**

Trouvé en écrivant le test de la paire inter-pages incohérente, et **pas
limité à l'inter-pages** : `_reconcile_one_pair` posait `status = CORRECTED`
inconditionnellement, y compris quand `reconcile_hyphen_pair` avait fait
retomber **les deux** côtés sur leur OCR faute de cohérence. Deux lignes
gardaient donc leur texte source en se déclarant corrigées : aucun compteur de
fallback, aucun motif. Exactement la forme silencieuse de `L3`, sur un autre
chemin.

Le statut suit maintenant l'issue. `classify_reconcile_outcome` ne dit
« fallback » que si quelque chose a été proposé **et** jeté, donc une
correction identité reste `CORRECTED`.

**Deux tests épinglaient ce défaut** et affirmaient qu'un « clean run »
rapportait zéro fallback. Vérifié : sur ces fixtures la substitution casse le
mot joint, la paire est légitimement révoquée, et les deux lignes gardaient
bien leur OCR. Ils disent maintenant la vérité, et un vrai baseline
« ne change rien » a été ajouté à côté.

Les traces des deux membres sont rafraîchies par le réconciliateur : une queue
révoquée dont la page est déjà close n'a plus rien en aval pour corriger sa
trace, et `derive_decision_set` **lit le motif sur la trace** — sans ça, le
rapport montrait un fallback au motif vide.

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

**Première tranche faite (2026-07-27) — par soustraction, pas par ajout.**

- `planner._hyphen_partner_id` supprimé : **zéro appelant**. Le mécanisme pris
  en flagrant délit — `derive_hyphen_groups` avait remplacé son usage, la
  fonction n'a jamais été retirée. 5 résolveurs → 4.
- `pipeline._page_local_hyphen_unit` remplacé par `_page_local_units`, qui **ne
  lit plus aucun champ pointeur** : il interroge la dérivation partagée. 4 → 3.
- Ce qui a rendu ça possible sans dupliquer la traversée : `HyphenGroup.complete`,
  calculé **dans la boucle qui lit déjà les pointeurs**. Un consommateur qui doit
  déplacer une unité entière (routeur, batcher de la limite d'images) doit
  distinguer « voici toute l'unité » de « voici la part que je vois » ; il pose
  désormais la question au groupe. La reposer aux pointeurs est exactement
  comment un résolveur parallèle apparaît.
- Effet de bord : la dérivation est faite une fois par page, plus une fois par
  ligne — l'ancienne marche était quadratique en densité de césures.

**Deuxième tranche faite (2026-07-27).** `pipeline._hyphen_closure` supprimé,
remplacé par `units.units_containing` : la seconde marche à point fixe sur les
pointeurs a disparu. **5 résolveurs → 2.** Personne n'a rien vu passer — la
suite entière est restée verte au moment de l'échange, ce qui montrait
justement qu'aucun test n'exerçait la différence entre les deux encodages.
Sept tests l'épinglent désormais.

### Correction de la cible de `S1`

Le plan visait « **1** résolveur ». C'est faux, et une mauvaise cible produit
un mauvais refactor. La cartographie montre **deux notions distinctes**, à
garder distinctes :

| notion | question | primitive |
|---|---|---|
| arête **dirigée** | « sur quelle ligne mon mot continue-t-il ? » | `forward_partner_id` |
| **unité** non dirigée | « quelles lignes voyagent ensemble ? » | `derive_hyphen_groups` |

Les confondre est ce qui a produit les encodages parallèles. La bonne cible est
**une primitive dirigée + une dérivation d'unité**, pas une seule fonction.

**Troisième tranche faite (2026-07-27) — la primitive dirigée existe.**
`pipeline._resolve_partner` supprimé. **5 résolveurs → 0 doublon.** Ce qui
reste est la forme cible :

| | rôle |
|---|---|
| `pairing.pair_ref` / `forward_ref` | lisent **un** créneau, qualifié par page |
| `pairing.forward_partner_ref` | la carte rôle→créneau, et la seule |
| `pairing.forward_partner_id` | l'id nu, délègue — pour les recherches déjà limitées à une page |
| `units.derive_hyphen_groups` / `units_containing` | la dérivation d'unité |
| `pipeline._lookup_ref` | une **recherche**, pas une résolution : ref → manifeste |

**Le piège que ça ferme, et il valait le détour.** Les deux créneaux de liens
s'appellent `hyphen_pair_*` et `hyphen_forward_*` — et « forward » nomme le
**créneau**, pas la direction de lecture. Le mot d'une ligne `PART1` continue
sur la ligne de son créneau **PAIR** ; seule une ligne `BOTH` utilise le
créneau FORWARD pour ça. Le réconciliateur du pipeline avait cette carte
épelée **inline**, à deux lignes d'un helper qui la connaissait déjà. Seize
tests l'épinglent désormais (`tests/test_directed_link.py`), avec des leurres
dans les deux créneaux.

Lectures de champs pointeurs, par module : `pairing.py` 22 (c'est sa
fonction), `units.py` 13, `pipeline.py` **8** (était 18), `planner.py` **0**,
`hyphenation.py` **0**.

Reste `should_stay_in_same_chunk` (hyphenation) — prédicat mince sur
`forward_partner_id`, troisième formulation. À absorber ou à assumer.

Et reste le **vrai** cœur de `S1` : rendre l'unité **autoritaire**, c'est-à-dire
que la décision appartienne à l'unité et se projette sur les lignes physiques,
les pointeurs devenant dérivés. Le blocage est nommé et il est favorable :
`split_forward_link` est le **seul** mutateur de pointeur après le parsing
(vérifié — tous les autres sites sont dans les parseurs et `link_hyphen_pairs`),
et il est appelé par le planificateur. Une fois une page planifiée, ses
pointeurs sont figés pour l'exécution. Dériver l'index **après chaque
(re)planification** — descentes de granularité comprises — suffit ; il n'y a pas
de mutations dispersées à traquer.

Attention conservée : le site « un partenaire est-il tombé en fallback ? »
n'interroge que les partenaires **directs**, pas la chaîne transitive. Passer au
groupe élargit le comportement sur les chaînes de 3+ — défendable au titre de
l'atomicité, mais c'est un changement à mesurer, pas à glisser. Le commentaire
le dit sur place.

| id | item | mesure actuelle | cible |
|---|---|---|---|
| S1 | Queue de l'ADR-010 : **unité de césure de première classe** — membres ordonnés, pages, type explicite/heuristique, autorité `SUBS_CONTENT`, signe physique, état, décision atomique, projection par format. Pointeurs dérivés, jamais mutables séparément. Retrait des résolveurs obsolètes | **0** doublon de résolveur (était 5) ; 8 lectures de pointeur dans `pipeline.py` (était 18) ; unité pas encore autoritaire | 1 primitive dirigée + 1 dérivation d'unité, 0 pointeur mutable |
| S2 | Scinder `core/pipeline.py` en composants nommés — préflight, planification, routage, exécution de chunk, validation, acceptation, réconciliation d'unités, projection, assemblage du rapport. Le pipeline public **orchestre**, il ne réimplémente pas | **3052** lignes (3015 le 25/07 : `L0` en a ajouté ~50, `S1` en a rendu ~12) ; `_run_impl` 294/imbr. 4 ; `_attempt_chunk` 220/imbr. 5 | fichier principal < 800 l., aucune méthode > 100 l., assemblage du rapport indépendant du contrôle d'exécution |
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
| D1 | **Défaut de portée dans les mots, pas de conception.** L'architecture visée — cœur aveugle aux pixels, distribution de base sans Pillow, extra `corrigenda[vision]` qui traite les pixels — **est déjà implémentée et vérifiée mécaniquement** (`pyproject.toml:43-53` : Pillow hors des `dependencies`, import paresseux `# lazy — I4`, scan statique I4 + `tests/test_import_contract.py`). Le corps de I4 (`SPECS:37`) et la ligne rouge de §12 (`SPECS:585-591`) sont **déjà** portés sur `core` et exacts. Seuls le **titre** de I4 (`SPECS:36`) et un rappel (`SPECS:307`) disent « la lib » là où le texte veut dire « le cœur » ; `packages/corrigenda/README.md:36` a recopié la version large. Remplacement de mots à trois endroits — aucun arbitrage |
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
`M1`-`M5`, `M7`, `D1`, `D3`-`D5`, `D7`-`D11`, `P1`-`P2`.

**Claude Desktop** — recherche, décision, documents : `Gate 0`, `M6`, `D2`,
`D6`, `D12`, `G3`, `P3`.

### Ordre

**Lot 0 — vérité documentaire, sans risque, immédiat.** `D8`, `D9`, `D10`, puis
`D11` et `D1`. Ils ferment quatre mensonges de façade en quelques lignes et ne
dépendent de rien. À faire avant le reste, parce que chaque jour où ils restent
est un lecteur trompé.

`D1` était assigné à Desktop tant qu'on le croyait porteur d'un arbitrage de
conception. Il n'en porte aucun — l'architecture est déjà celle qu'il faut et
elle est testée ; il ne reste qu'un mot à corriger à trois endroits. Il revient
donc ici, en Lot 0.

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
