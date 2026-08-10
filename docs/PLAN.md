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

Dernière mise à jour : 2026-08-06, après un audit structurel externe (§ `RM`).
Cette révision **ne change ni le diagnostic ni les priorités** : elle ajoute une
vague `RM` de dette *structurelle* — un défaut latent, un instrument de mesure
faussé, et de la réduction — qui ne ferme aucun item `L`, `R` ou `M` mais rend
`S1` praticable. Révision précédente : 2026-07-27, contre-audit d'une analyse
externe, qui relevait le niveau de trois réponses (`L`, `S1`, tests), ajoutait
quatre items de vérité documentaire, et écrivait la règle de gel.

---

## Objectif : `0.10.0`, puis `1.0.0` — jamais l'inverse

Publier une `0.x` honnête plutôt qu'une `1.0` prématurée. Trois raisons
inchangées :

1. La surface publique doit passer de **95 symboles à sa clôture minimale**
   (`S3b`). C'est une rupture — publier `1.0` avant la gèlerait sous SemVer.
   La coupe est différée jusqu'après `S2` ; ce qui est fait dès maintenant
   (`S3a`), c'est de **dire** qu'elle est provisoire, partout où la doc
   prétendait le contraire, et d'interdire qu'elle regrandisse.
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
| V3 | Une **seule** définition de l'unité de césure dans tout le code — **atteint** : une famille de primitives dirigées (`core/pairing.py`, seul lecteur des champs pointeurs) + une dérivation d'unité (`core/units.py`), et la cohérence des pointeurs est tenue par l'invariant de symétrie | fait |
| V4 | Ce que le système **ne peut pas** établir est signalé, pas décidé | `review_required` livré (`G*`) |
| V5 | La surface publique est la clôture de ce que la façade retourne | `S3b` fermé (`S3a`, son statut provisoire écrit, est fait) |
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

## Gate 0 — Licences des corpus — **clos (2026-07-27)**

Tranché, et plus petit qu'annoncé.

- **`corpus/37-GT-BNL/`** — ground truth de la Bibliothèque nationale du
  Luxembourg, **CC0 / domaine public** par déclaration de la BnL elle-même
  (« As part of BnL's AI strategy, we provide the ground truth data that falls
  into the public domain (CC0, see copyright notice) »). Rediffusion libre.
- **`corpus/BnF-bpt6k3265015q/`** — document de presse du 19e siècle, **domaine
  public**, librement téléchargeable depuis Gallica. Nuance consignée plutôt
  qu'ignorée : les conditions de la BnF portent sur la *reproduction numérique*
  et distinguent réutilisation non commerciale (libre) de commerciale (sous
  licence). Un usage comme fixture relève de la première.

**Et la troisième option du plan était déjà vraie** : les corpus vivent à la
racine du dépôt, hors de `packages/corrigenda/`, et `sdist.include` est un
allowlist explicite de quatre entrées. **Aucun corpus ne part dans la wheel ni
dans la sdist** — vérifié, et désormais épinglé par
`tests/test_packaging_excludes_corpora.py`, qui refuse aussi qu'un README de
corpus reparte en « À VÉRIFIER ».

La purge d'historique (`git filter-repo`) n'est donc **pas** requise pour
publier. Elle reste une option de poids (34 Mo + 9,2 Mo dans les objets git),
sur un critère de taille et non de droit.

---

## L — Intégrité de ligne (bloquant)

La promesse unique de cette bibliothèque est la sûreté structurelle. Un défaut
qui altère le texte livré sans trace contredit l'argument de vente lui-même.

**Changement d'approche depuis le 25 juillet.** `L1`, `L2`, `L4` et `L6` étaient
listés comme quatre correctifs indépendants. Ce sont quatre symptômes de deux
absences de modèle. Les traiter séparément recrée le mécanisme d'enlisement
décrit en `S` : quatre correctifs, quatre chemins de plus.

**État : `L*` fermés — `L0`-`L3`, `L5`-`L10` faits, `L4` retiré.** Les deux
défauts qui altéraient le texte livré sans laisser **aucune** trace — ni
compteur, ni erreur — sont fermés. `L4` s'est révélé faux à la vérification
(§4.5 de l'audit du 27) et a laissé `L8` à sa place, qui est fait à son tour :
`exact` ne se revendique plus sur 115 lignes dont le fichier dit autre chose.
`L3` est fermé ; il a fait tomber `L9`, et l'invariant écrit pour couvrir cette
famille a trouvé `L10`. `L5` a élargi `L7` en le corrigeant — la ligne blanche
enjambée a rendu atteignable une paire non adjacente que trois endroits du
découpage supposaient impossible — et `L7` a fermé les deux, plus le reste de
`S1` au passage.

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

- échelle ordonnée `exact` → `source_spelling` (ajouté par `L8`) →
  `token_equivalent` → `normalized`, chaque niveau distinguant ce que le
  **format coûte** (`<SP>` ne porte pas de contenu : une suite d'espaces et un
  blanc de bord ne peuvent pas survivre) de ce qui a été **substitué** (U+00A0,
  U+202F, tabulation aplatis en espace ordinaire) ;
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

### L8 — Substitutions hors blancs — **fait, et un des deux cas était déjà bon**

`L0` classait les substitutions de **blancs**. Deux substitutions de caractère
non-blanc étaient soupçonnées de ne remonter nulle part. Vérification faite,
**une seule** l'était.

**`preserve_break_char` : déjà déclaré.** Le pipeline force le signe de coupure
de la source *avant* que les décisions se matérialisent, et
`ProposalStage.output_text` conserve le texte **brut** du producteur. Un
consommateur voit donc `tou-` proposé et `tou¬` décidé, côte à côte dans le
rapport. Le commentaire du site d'application le dit déjà. Rien à faire —
résultat négatif utile, du même genre que l'invariant de symétrie.

**La collapse U+00AD : `exact` était un mensonge sur 115 lignes.** Le niveau
`EXACT` promet « l'artefact dit la décision, **caractère pour caractère** ». Sur
115 des 566 lignes de `examples/X0000002.xml`, le fichier porte son signe de
coupure en U+00AD dans le `<HYP>`, la reconstruction le relit `-`, la réécriture
réémet l'élément source intact — et le run classait les 115 en `exact`.

Il ne pouvait rien classer d'autre : **la collapse s'applique aux deux côtés de
la comparaison et s'égale à elle-même.** Même mécanisme d'aveuglement que `L2`.
Le remède n'est donc pas un invariant plus strict, c'est de donner à l'invariant
une seconde lecture — `RewriteResult.texts_verbatim`, le même parcours d'arbre
avec la table de substitution **désactivée**.

Nouveau niveau, **`source_spelling`**, entre `exact` et `token_equivalent` :
l'artefact dit la décision mais orthographie un caractère comme la **source**,
là où la décision porte la lecture normalisée. **Rien n'est perdu** — le fichier
est *plus* précis que la décision — et c'est précisément pourquoi le niveau est
au-dessus de `token_equivalent`, qui lui perd une suite de blancs pour de bon.
Classer un désaccord sans perte sous une perte réelle inverserait le sens de
l'échelle.

Mesure après correctif, sur le fichier BnF : **451 `exact`, 115
`source_spelling`, 0 `normalized`** — et les 115 sont exactement les lignes à
`<HYP CONTENT="U+00AD">`, épinglé par égalité d'ensembles, pas par comptage.

**Conséquence pour `R8`, à ne pas manquer** : « une substitution déclarée est
une perte comptable » est **faux pour `source_spelling`**. Le fichier garde son
caractère ; le compter en perte fabriquerait un fantôme — la forme de `R1`.
`R8` ne doit brancher la comptabilité que sur `normalized`.

PAGE ne substitue rien à la lecture (NFC + `strip`) et livre donc un
`texts_verbatim` vide. Ce n'est pas supposé : un test vérifie que le texte
logique de chaque ligne se retrouve **caractère pour caractère** dans les octets
livrés (échappement XML mis à part). ALTO et PAGE en désaccord silencieux sur la
même classe d'événement est exactement ce que `R4` a dû revenir corriger.

### L6 — Répertoire de coupure — **fait, sur mesure**

`HYPHEN_CHARS` passe de 4 à 6 : ajout de **U+2010 HYPHEN** et **U+2011
NON-BREAKING HYPHEN**.

Élargir n'est pas neutre — un nouveau membre fait apparier des lignes qui ne
l'étaient pas — donc chaque membre est là sur **preuve**. Mesuré sur les 40
fichiers ALTO/PAGE de `examples/` et `corpus/`, contenu textuel seulement :

| signe | occurrences | en fin de ligne |
|---|---|---|
| `-` U+002D | 238 | 119 |
| `⸗` U+2E17 | 36 | 25 |
| `¬` U+00AC | 0 | 0 |
| U+2010, U+2011, U+2013, `=` | **0** | **0** |

Les deux ajoutés sont **prouvablement sans effet** sur les corpus existants :
couverture latente pour un producteur qui les emploie, et rien d'autre que ces
caractères puissent signifier.

**`=` et U+2013 restent exclus**, pour la même raison : ils portent d'autres
sens (signe égal d'un tableau ; tiret de dialogue ou intervalle) et les corpus
ne donnent **aucune preuve** qu'ils soient nécessaires. La contrainte de
caractère alphabétique de `trailing_hyphen_char` écarte `1789–` mais pas une
ligne finissant sur un tiret de dialogue. Les admettre demande une mesure sur
un corpus qui en contient (`M7`), pas une édition de tuple.

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

### L10 — Coupure avant perdue sur une ligne à rôle mixte — **fait**

**Trouvé par un test, pas par une lecture** — le premier de la session.

`PAG_00000002_TL000454` de `examples/X0000002.xml` est `BOTH` : elle ouvre sur
un `SUBS_TYPE="HypPart2"` explicite et finit sur un simple tiret heuristique,
sans `<HYP>`. Lien arrière explicite, coupure avant heuristique, sur une seule
ligne.

Le réécrivain décidait de retirer le tiret du `String` en lisant
`hyphen_source_explicit` — qui décrit le lien **arrière**. Réponse
« explicite », donc il retirait le tiret en supposant qu'un `<HYP>` le rendrait.
Il n'y en a pas : **le signe disparaissait du fichier livré.**

Correctif : `pairing.forward_break_is_explicit`, la carte rôle→slot appliquée
au bon drapeau. Diff classé par TextLine sur le corpus réel : **1 sur 566**,
`Wal` → `Wal-`, rien d'autre. Le hash d'or épinglait le défaut.

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

**Fait (2026-07-28) sauf deux, et les deux qui restent demandent de la
géométrie, pas un correctif.**

Faits antérieurement : ~~page vide sautée~~, ~~PART1 sans partenaire annonçant
`join_with_next=True`~~, ~~rejet de `PairingPolicy` silencieux~~.

#### Le répertoire, dans les gardes — 32 lignes sur 363, mesurées

`HYPHEN_CHARS` a six membres et les parseurs s'en servent tous, donc une ligne
peut légitimement être PART1 en finissant par `⸗` ou `¬`. **Cinq sites de garde
testaient pourtant le seul tiret ASCII** (`endswith("-")`, `rstrip("-")`).

| signe | lignes PART1/BOTH |
|---|---|
| `-` U+002D | 331 |
| `⸗` U+2E17 | **24** |
| `¬` U+00AC | **8** |

**32 sur 363 — 8,8 %** tombaient hors de *toutes* ces vérifications. Pas
latent : `corpus/37-GT-BNL` est du Fraktur et son signe de coupure est `⸗`.

Conséquences réelles, chacune avec le test qui échoue avant :

- **garde orphelin** (`pipeline`) : un `⸗` supprimé par la correction n'était
  pas rattrapé — la ligne livrée ne disait plus que le mot continue ;
- **garde de croissance PART1** (`hyphenation`) : le signe restait collé au
  texte nu, donc chaque comparaison de longueur portait sur une chaîne **un
  caractère plus longue** que sa contrepartie. Le seuil étant un compte de
  caractères (`part1_last_word_char_growth`, 3), une complétion de mot de 4
  caractères se lisait 3 et passait ;
- **détection de fusion** (`validator`) : un modèle qui complète le mot **et**
  garde le signe (`nécessaires⸗`) ne correspondait jamais au mot logique — la
  fusion passait la validation alors que le texte de PART2 avait déjà migré.

Deux primitives dérivées du répertoire (`ends_with_break_mark`,
`strip_trailing_break_marks`) dans `pairing.py`, seul domicile du répertoire.
`ends_with_break_mark` n'impose **pas** la contrainte de caractère alphabétique
de `trailing_hyphen_char` : ses appelants savent déjà que la ligne coupe un mot
(le rôle le dit, éventuellement depuis un `SUBS_TYPE` explicite), et la
réimposer désarmerait une ligne explicitement marquée finissant par un chiffre.

#### La ligne vide — la même phrase que la page vide

`link_hyphen_pairs` prenait `lines[i + 1]`. Une ligne blanche entre un PART1 et
sa vraie continuation devenait donc le PART2 : elle ne porte aucun texte, donc
rien ne se réconcilie, les gardes de dérive de paire ne tournent jamais, et la
continuation réelle reste non liée. Même conséquence que le défaut page vide,
une échelle en dessous — et **la même phrase la règle** : une ligne sans texte
ne peut rien dire d'un mot qui l'enjambe ; c'est un fait sur le scan, pas sur la
phrase.

Appliqué aux **deux** parcours, avec une seule définition (`_substantive`) pour
que « une ligne vide ne porte rien » ne finisse pas par signifier deux choses.
Ça ferme aussi la facette « `link_cross_page_hyphens` ne regarde que
`lines[-1]`/`lines[0]` » : une blanche au pied d'une page ou en tête de la
suivante cachait un mot qui enjambe la couture. **Latent** — 0 ligne vide sur
1711 — donc onze tests, aucune mesure.

#### Ce qui reste, et pourquoi ce n'est pas un correctif

- **chaîne mixte jetant l'autorité `SUBS_CONTENT`** ;
- **cross-bloc en ordre de lecture dégradé**, et l'autre facette de
  `lines[-1]`/`lines[0]` : un en-tête ou un numéro de page en tête de page
  suivante n'est pas une ligne vide, c'est une ligne **hors ordre de lecture**.
  Décider qu'elle n'est pas la continuation demande de la géométrie — ce qui est
  exactement le métier de `PairingPolicy`, qui vet déjà les paires heuristiques
  géométriquement. Le trancher demande un corpus qui en contient (`M7`), pas une
  édition de prédicat.

### L7 — Découpage — **fait (2026-07-28)**, une racine pour trois symptômes

Les trois items étaient **le même défaut à trois endroits** : demander
« mon partenaire est-il la ligne **suivante** ? » au lieu de « **où** est mon
partenaire ? ». Et le troisième item n'était pas indépendant — il tombait avec
les deux autres.

**L'invariant, écrit comme tel.** Une paire liée n'a que deux issues légitimes
au moment du plan : **ensemble dans un chunk**, ou **coupée avec un
`HyphenSplit` sur le plan**. Ni l'un ni l'autre est un trou silencieux — le
validateur écarte une paire qui n'est pas entièrement dans le chunk, et le
réconciliateur pourrait écrire par-dessus la frontière.

**Et mon propre correctif `L5` avait élargi le trou.** Le suivi de chaîne de
`_plan_line` exigeait l'adjacence stricte ; dès que l'appariement a su enjamber
une ligne blanche, une paire liée `L0 → L2` échouait au test, la chaîne
s'arrêtait, les deux membres tombaient dans des chunks différents et le lien
restait **vivant**. Mesuré avant correctif :

```
chunks: [['L0'], ['L1'], ['L2'], ['L3']]
splits: []
L0 still linked to: L2
```

- **`_plan_line`** suit désormais le **lien** (une *recherche* id→position, pas
  un résolveur — la distinction que `S1` a posée), emmène les lignes
  intercalées avec la paire plutôt que de les laisser hors de tout chunk, et la
  condition de coupure devient « mon partenaire n'est pas dans mon chunk » au
  lieu de « le plafond m'a coupé » : les deux coïncidaient seulement tant que
  l'adjacence était requise. Un partenaire **hors page** (paire inter-pages,
  propriété du join de `L3`) ou **en arrière** n'est ni suivi ni coupé.
- **`_try_window`** avait la même racine, via `should_stay_in_same_chunk` —
  précisément la « troisième formulation » que `S1` laissait à absorber.
  Remplacée par `_unit_reach`, qui répond à la vraie question : *jusqu'où cette
  fenêtre doit-elle aller pour contenir tout lien qui en sort ?* Le prédicat
  pairwise était faux dans **deux** directions — il ne voyait ni un lien
  partant d'une ligne **antérieure** de la fenêtre, ni un partenaire non
  adjacent. **Absorbé et supprimé** : un seul appelant en production.
  **`S1` n'a plus de reste.**
- **Le troisième item — « la descente ne rapatrie pas les partenaires
  non-cibles » — n'est pas un défaut indépendant.** Mesuré : le ciblage de
  fenêtre (`_assign_window_targets`, qui utilise déjà la dérivation partagée)
  force les deux membres d'une paire dans la même fenêtre. Balayage de **3708
  chunks** sur 7 formes de page × une grille de configurations : **45
  violations, toutes de la forme « paire par-dessus une blanche »**, c'est-à-dire
  la paire non adjacente. Zéro après le correctif de fenêtre. Fermé par la même
  racine, sans code propre.
- **`_split_for_image_cap`** posait une autre question à la mauvaise fonction.
  `_page_local_units` répond « est-ce l'unité **entière** ? » et rend *rien*
  quand non — ce qui est juste pour le **routeur** : escalader une demi-unité la
  couperait, donc une unité incomplète reste au producteur primaire et ses
  membres restent ensemble **en ne faisant rien**. Le batcher n'a pas cette
  option : il **découpe** un chunk en appels, donc « ne rien faire » n'existe
  pas. Sans unité, il traitait chaque membre en singleton et pouvait mettre une
  paire dans deux appels. Deux formes y arrivaient : un groupe dont le dernier
  pointeur **pend**, et un groupe qui **continue sur une autre page** (son
  membre distant n'est pas là, ceux qui le sont appartiennent au même appel).
  Nouveau `_units_visible_on_page` — même dérivation partagée, zéro lecture de
  pointeur, **projection différente** : les membres présents, entiers ou non.

Les tests sont l'invariant, pas la forme du correctif : 48 combinaisons
forme × plafond, plus les cas qui ont exposé le défaut avec leurs chiffres.
Vérifié en revertant : **18 rouges** sur le planificateur, **3** sur le batcher.

Détail et preuves : `AUDIT-2026-07-25.md` §3a, §3c, §3d ; `AUDIT-2026-07-27.md`
§2.6, §3.1, §3.2, §4.3, §4.4.

---

## R — Comptabilité honnête (bloquant)

« Toute perte comptée » est une revendication d'auditabilité faite dans les docs
du projet. Elle était fausse **dans les deux sens** — ce qui est pire qu'une
absence de comptabilité, parce que le chiffre a l'apparence d'une garantie.

**État : `R0` à `R8` fermés (2026-07-28).** Deux des neuf se sont fermés par
mesure plutôt que par code — `R3` était plus étroit que son énoncé, `R8` était
déjà compté et c'est la *revendication* qui était fausse — et un troisième
(`R7`) est documenté et testé plutôt qu'armé, parce que l'armer changerait la
sortie livrée sans seuil mesuré. Le fil conducteur des neuf est **une** règle :
un événement, un compteur. Deux sites de comptabilité pour un même événement
sont libres de diverger, et c'est exactement ce qu'était `R1`.

| id | item |
|---|---|
| ~~R0~~ | **fait** — `core/losses.py`, matrice **versionnée et exécutable** (`LOSS_MATRIX_VERSION`). Écrite depuis la mesure, pas depuis la croyance : chaque sort a été observé sur les deux fixtures réelles × les trois chemins d'écriture. La distinction qui manquait : `STRUCTURAL` (l'attribut suit le token — le chemin lent passe de 3395 à **3963** `HPOS` parce qu'il écrit *plus* de mots, pas parce qu'il en perd) vs `SEMANTIC` (une assertion sur une lecture ; sa disparition est une perte). Quatre sorts : `PRESERVED` / `REWRITTEN` / `INVALIDATED` / `DROPPED`, plus `ALIGNMENT_SCOPED` pour ceux dont la perte est conditionnelle et comptée par une seconde passe. **Le réécrivain consomme la matrice** — il ne détient plus de seconde liste, et deux listes pour un attribut est précisément la forme de `R1`. Vérifiée par `test_loss_accounting_is_real.py` |
| ~~R1~~ | **fait** — `SUBS_TYPE`/`SUBS_CONTENT` étaient comptés perdus alors que `_apply_subs` les réécrit sur les **trois** chemins d'écriture. Mesuré avant correctif : **229 de chaque** revendiqués sur une seule page réelle de 566 lignes dont le fichier de sortie en porte exactement autant que la source. Trouvé par l'invariant différentiel `R0-test` |
| ~~R2~~ | **fait (2026-07-28)** — la reconstruction a **deux sorties** : une correction qui vide la ligne revient *avant* tout alignement (il n'y a aucun token cible sur quoi aligner), et cette sortie ne comptait aucun `STYLE`/`STYLEREFS`. Rien d'aligné veut dire tout perdu. **56 lignes** des corpus ALTO du dépôt portent ces attributs. Corrigé par **une** fonction de comptabilité appelée aux deux sorties — une seconde copie en ligne est exactement comment `R1` est arrivé |
| ~~R3~~ | **fait (2026-07-28), et plus étroit que l'énoncé.** « `<HYP>` d'une PART2 » évoque une ligne de continuation portant aussi un signe final : ce n'est **pas** une PART2. Le parseur lit le signe terminal comme une coupure avant, classe la ligne `BOTH`, et le `<HYP>` est **réémis**. Le seul chemin réel est un `<HYP>` **non terminal** — qu'ALTO ne définit pas, que le parseur tolère, et où l'élément part en silence. Compté `hyp_elements_removed` : ce qui part est l'**élément** (sa géométrie, son statut de balisage), pas le signe, dont le caractère revient dans le `CONTENT` reconstruit. Les deux moitiés sont assertées pour que personne ne « corrige » ça en resynthétisant un HYP qui doublerait le signe. **0 des 1711 lignes ALTO** des corpus ont cette forme : chemin latent, épinglé comme `L2` l'a été |
| ~~R4~~ | **fait (2026-07-28) — comptés, par LIGNE.** `WC`/`CC` n'étaient comptés nulle part en ALTO pendant que PAGE comptait `conf_dropped` **par occurrence** : silence d'un côté, unité incomparable de l'autre. Les deux arguments avaient raison sur des unités différentes, et l'unité était toute la décision — voir ci-dessous |
| ~~R5~~ | **fait (2026-07-28)** — le drapeau voyageait dans le dictionnaire de pertes, donc `sum(format_losses)` comptait un non-événement : rien n'a quitté le balisage, l'alignement n'a simplement pas pu se porter garant de l'ordre qu'on lui a remis. Il a son propre canal (`RewriteResult.word_order_suspected` → `ProjectionStage.word_order_suspected`). Signalé, jamais appliqué — inchangé |
| ~~R6~~ | **fait (2026-07-28)** — `CorrectionReport.hyphen_splits`. Et une mesure au passage : un split **n'arrive qu'à la granularité `LINE`**, que l'auto-sélection du planificateur n'atteint jamais (PAGE → BLOCK → WINDOW) ; le seul chemin réel est la **descente après échec de chunk**. L'événement est donc rare, et le test doit passer par cette porte-là. Ce qu'aucun autre champ ne dit : le split **remet le rôle de la queue à `NONE`**, donc `unpaired_breaks` — qui ne regarde que les lignes voulant encore un partenaire — y est aveugle par construction ; les deux côtés gardent leur texte, donc ce n'est pas un fallback ; rien ne quitte le balisage, donc ce n'est pas une perte de format. Ce que l'hôte reçoit est une ligne livrée dont le texte finit au milieu d'un mot et qui ne déclare aucune coupure |
| ~~R7~~ | **fait (2026-07-28) — documenté et épinglé, pas armé.** `word_count` n'est peuplé que par le parseur PAGE, donc `strict=True` sur un document ALTO rend **exactement** le comportement par défaut, en silence. La docstring le dit désormais franchement, et ajoute ce qui manquait vraiment : ce n'est **pas** « une réécriture ALTO ne perd rien ». Un changement de compte de mots reconstruit la ligne et lâche `TAGREFS`/`language`/attributs vendeur + le `STYLE` des `String` non alignés — **rapportés, gatés par aucun mode**. Armer la garde pour ALTO changerait la sortie livrée : ça demande un seuil mesuré, pas un drapeau retourné en passant. Trois tests tiennent les deux moitiés (`test_loss_policy_scope.py`) |
| ~~R8~~ | **fait (2026-07-28) — clos par la mesure, sans ajouter de compteur.** La perte **est déjà comptée** : une ligne `normalized` est agrégée par `projection_fidelity` et attribuée par ligne sur `ProjectionStage.fidelity`. Ce qui était faux, c'est la revendication autour : sur un run où une tabulation est aplatie, `format_losses` vaut **`None`** — et qui lit ce champ seul conclut « sans perte ». Corrigé dans le contrat aux trois endroits qui le disaient. **Et refuser d'ajouter une clé à `format_losses` est la même décision que `R4`** : elle coïnciderait avec `projection_fidelity["normalized"]` sur *tous* les runs par construction, et deux sites de comptabilité pour un événement sont libres de diverger par la suite — c'est ce qu'était `R1`. Les deux moitiés sont assertées : la perte est trouvable, et trouvable **à un seul endroit**. `source_spelling` reste hors comptabilité (`L8`) : le fichier garde son caractère |

### `R6` — une ride observée en l'épinglant, laissée telle quelle

`LineOutcome.hyphen_role` vient de la **trace** de la ligne, écrite quand son
chunk a été enrichi la première fois. Un split arrive **plus tard** — pendant la
descente de granularité qui suit un chunk en échec — donc une queue coupée peut
être rapportée avec le rôle qu'elle avait **avant** la coupure (`HypBoth` là où
le manifeste dit désormais `HypPart2`).

C'est un second problème de vérité, plus étroit que `R6`, et que le nouveau
champ ne corrige pas : c'est précisément pourquoi le split a besoin de son
**propre** enregistrement plutôt que d'être déduit des rôles du rapport. Épinglé
par un test (`test_the_reported_role_can_predate_the_split`) pour que ce soit
une quantité connue, et pour qu'un futur correctif ait un test à retourner.

---

### `R4` — l'unité était toute la décision (2026-07-28)

Le choix n'était pas « compter ou se taire », c'était **en quoi compter**.

| unité | ce que ça donne sur `X0000002.xml` (566 lignes) |
|---|---|
| par occurrence (ce que faisait PAGE) | **3339** |
| par ligne (retenu) | **566** en chemin lent, **492** en chemin rapide |
| silence (ce que faisait ALTO) | 0 |

Par occurrence, le compteur varie avec la **verbosité d'une ligne** et pas avec
ce sur quoi un archiviste agit ; à quatre chiffres il noierait les compteurs à
trois chiffres posés à côté. Par ligne, il énonce le fait : *ces lignes ne
portent plus la confiance du moteur.* C'est aussi la seule unité que le reste
du rapport parle — toute autre entrée de `format_losses` est attribuable à une
ligne (ADR-012), une valeur par occurrence ne l'aurait pas été.

**L'écart 492 / 566 est le contrôle qui compte.** Le chemin rapide ne retire
`WC` que des `String` dont le `CONTENT` a réellement bougé : 74 lignes gardent
leur confiance intacte, et le compteur le voit. Il est calculé par mesure
avant/après sur l'élément, pas déduit du chemin emprunté — « la ligne a été
réécrite » n'est pas « la ligne a perdu sa confiance », et c'est exactement le
genre de raccourci qui a produit les fantômes de `R1`.

Fait en un commit sur les deux formats, comme la matrice l'exigeait :
`COUNTS_INVALIDATION = True`, `INVALIDATION_UNIT = "line"`,
`INVALIDATION_COUNTER = "confidence_invalidated"` — une clé unique, émise par
ALTO **et** PAGE (`conf_dropped` disparaît). `LOSS_MATRIX_VERSION` passe à
`"2"`. La passe par `String` est tenue à l'écart des attributs `INVALIDATED`
(`is_unconditional_loss`), sans quoi le même attribut serait compté deux fois —
la forme de `R1`, encore.

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

### Décision (2026-07-27) — on s'arrête là, et `V3` est reformulé

**Le cœur de `S1` ne sera pas fait maintenant.** Le travail de cette session a
déjà capturé l'essentiel de sa valeur par des moyens beaucoup moins chers :

- la carte rôle→créneau ne vit qu'à un endroit ;
- une seule dérivation d'unité existe, et elle porte `complete` ;
- **l'invariant de symétrie** (`tests/test_link_symmetry.py`) teste que les
  pointeurs restent cohérents des deux bouts, sur corpus généré et fixtures
  réelles ;
- `split_forward_link` est **vérifié** comme seul mutateur post-parsing.

Le danger des pointeurs-comme-vérité était qu'ils se désynchronisent sans que
personne le voie. Trois tests le voient maintenant.

Ce que le refactor apporterait encore : rendre l'état illégitime
**inexprimable** plutôt que testé — une garantie de type, pas de suite.
Ce qu'il coûterait : le plus gros risque de régression du dépôt, sur la partie
la plus chargée du moteur, pour fermer un écart déjà surveillé.

`V3` est donc reformulé en « une famille de primitives dirigées + une
dérivation d'unité, cohérence tenue par invariant » — et il est **atteint**.

**À rouvrir seulement si `S2` le rend nécessaire.** Scinder les 3152 lignes de
`pipeline.py` pourrait l'exiger ; à ce moment-là les deux se font ensemble, et
pas avant.

### `S3` — la clôture, établie par calcul (2026-07-27)

Choisir la surface à la main, c'est comment on arrive à 95. Elle a donc été
**calculée** : partir de ce que `load` / `correct` / `correct_sync` retournent,
et suivre les annotations de type transitivement.

**Clôture des retours : 33 types.** 30 sont déjà exportés. **4 trous** — des
types qu'un appelant rencontre en typant la valeur de retour et qu'il ne peut
pas importer depuis le sommet :

| manquant | pourquoi il compte |
|---|---|
| `Coords` | la géométrie de chaque ligne du manifeste |
| `ProjectionFidelity` | le niveau que `L0` a mis sur `ProjectionStage` |
| `ReconcileMetrics` | porté par `CorrectionResult` |
| `CORRECTION_REPORT_VERSION` | `docs/versioning.md` dit aux consommateurs de **dispatcher dessus** (`D5`) — et `EDIT_PROTOCOL_VERSION`, lui, est exporté |

**Constat qui change la cible.** Le backend — le seul intégrateur réel —
**n'utilise ni `load`, ni `correct`, ni `correct_sync`**. Il passe par la porte
bas niveau : `CorrectionPipeline`, les policies, et les entrées de format par
leur chemin de module. Ce n'est pas un détail de style : ça dit que la façade
calculée n'est pas la porte empruntée, et qu'une réduction qui l'ignore
raterait sa cible.

**Correction (2026-07-28) d'une mesure fausse de ce plan.** La version
précédente de ce paragraphe affirmait « `build_document_manifest` 18×,
`parse_alto_file` 5×, `rewrite_alto_file` 2× » depuis le sommet. C'est faux :
le comptage confondait `from corrigenda import X` avec
`from corrigenda.formats.loader import X`. La mesure refaite, sur les
instructions d'import du dépôt entier :

| forme | dépôt | backend |
|---|---|---|
| `from corrigenda import …` (sommet) | **64** | 7 |
| `from corrigenda.<module> import …` | **695** | 60 |

Et les 7 du backend ne touchent que des symboles **gardés** par la répartition
ci-dessous, plus `sanitize_error` (3 sites). La conclusion tient toujours, mais
pour une raison plus forte que celle écrite : **le namespace de sommet est une
vitrine que le dépôt lui-même n'emprunte pas.** Le coût réel de la
rétrogradation est de 32 lignes d'import, dont 20 dans les tests de la lib, 6
dans des scripts et exemples, et **6 en production** — toutes pour
`sanitize_error`.

### Répartition proposée — **95 → 54**

**Gardés (50) + ajoutés (4)**

| groupe | n | contenu |
|---|---|---|
| façade | 4 | `load`, `correct`, `correct_sync`, `__version__` |
| ce que la façade retourne | 25 | `CorrectionResult`, `CorrectionReport`, `DecisionSet`, les manifestes, les étages du rapport, la provenance… |
| porte avancée | 7 | `CorrectionPipeline`, `EditProducer`, `PipelineObserver`, `BaseProvider`… |
| policies injectables | 7 | `RetryPolicy`, `GuardConfig`, `ChunkPlannerConfig`, `PairingPolicy`, `LossPolicy`, `ConfidencePolicy`, `RoutingPolicy` |
| erreurs | 7 | la hiérarchie `CorrigendaError` |
| **ajoutés** | 4 | les 4 trous ci-dessus |

**Rétrogradés (45)** — retirés de `corrigenda.*`, **toujours importables depuis
leur module** (vérifié : les 45 ont un module d'accueil réel).

| groupe | n |
|---|---|
| protocole d'édition | 12 |
| formats bas niveau | 8 |
| contrat LLM | 8 |
| producteurs concrets | 6 |
| QE / routage | 6 |
| enveloppe vision | 4 |
| divers (`ChunkGranularity`) | 1 |

**Le point à trancher avant de couper** : rétrograder oblige les appelants à
changer leurs imports — mécanique, pas une refonte — mais c'est un changement à
faire **dans le même commit** que la coupe, sinon le dépôt se casse lui-même.

### Décision (2026-07-28) — la coupe est différée, la vérité ne l'est pas

`S3` se scinde en deux, parce que ses deux moitiés n'ont ni le même coût ni le
même bon moment.

**`S3a` — dire ce qui est provisoire. Fait.** Ce qui coûtait quelque chose
aujourd'hui n'était pas la longueur de `__all__` : c'était que trois documents
la décrivaient faussement.

- `tests/test_public_api_snapshot.py` nommait la liste `PUBLIC_API_1_0` et la
  décrivait comme « the frozen 1.0 surface ». Elle n'a jamais été ratifiée ;
  elle a été **accumulée**. Le test contredisait donc ce plan, et aurait fait
  passer la coupe pour une régression. Renommée `CURRENT_TOP_LEVEL_SURFACE`,
  docstring réécrite.
- `SPECS_LIB_V2.md §8.1` déclarait `reconcile_hyphen_pair`, `check_line`,
  `plan_page` « déjà publics, maintenus ». Ils ne sont pas dans `__all__` — la
  spec normative promettait trois symboles absents pendant que `__all__` en
  exposait 95 dont la spec ne parlait pas. **Les deux se contredisaient dans
  les deux sens.** La promesse est retirée (et non honorée : le gel suspend
  l'extension de l'API publique, et `S3` réduit).
- `versioning.md` et `README.md` énoncent désormais le statut provisoire et la
  règle des **deux portes** — `corrigenda.*` sous SemVer strict *à partir de*
  `1.0.0`, chemins de modules supportés et documentés. Un symbole rétrogradé
  n'est pas supprimé, il est déplacé.

**`S3b` — couper. Différé jusqu'après `S2`.** Trois raisons, dans l'ordre de
poids :

1. `S2` scinde `core/pipeline.py` (3152 lignes) en composants nommés. Ça peut
   déplacer ce qui mérite d'être exposé. Couper avant, c'est migrer les imports
   **deux fois**.
2. Rien n'est gelé avant `1.0.0` : `docs/versioning.md` autorise explicitement
   `0.9.x` à casser. Le coût de l'attente est donc nul, à une condition — la
   liste ne doit pas regrandir.
3. Cette condition est **déjà tenue**, et c'est ce qui rend l'attente sûre :
   le test de cliquet interdit toute croissance de `__all__`, et le gel de
   fonctionnalités suspend de toute façon l'extension de l'API publique. Un
   ajout ne peut pas passer en silence — il faudrait toucher le snapshot et le
   `CHANGELOG`.

Ce qui reste dû par `S3b`, inchangé : la répartition 95 → 54 ci-dessus, les 4
trous de clôture ajoutés, les 32 lignes d'import migrées, le tout **en un
commit**. Décision restée ouverte pour ce moment-là : garder `sanitize_error`
au sommet (surface 55) parce que c'est un utilitaire de sécurité avec une vraie
dépendance en production — un outil de sécurité se rend facile à trouver.

**Ce que cette décision ne fait pas** : elle ne repousse pas `V5`. `1.0.0` reste
conditionnée à `S3b` fermé. Elle ordonne, elle n'annule pas.


| id | item | mesure actuelle | cible |
|---|---|---|---|
| S1 | Queue de l'ADR-010 : **unité de césure de première classe** — membres ordonnés, pages, type explicite/heuristique, autorité `SUBS_CONTENT`, signe physique, état, décision atomique, projection par format. Pointeurs dérivés, jamais mutables séparément. Retrait des résolveurs obsolètes | **0** doublon de résolveur (était 5) ; 8 lectures de pointeur dans `pipeline.py` (était 18) ; unité pas encore autoritaire | 1 primitive dirigée + 1 dérivation d'unité, 0 pointeur mutable |
| S2 | Scinder `core/pipeline.py` en composants nommés — préflight, planification, routage, exécution de chunk, validation, acceptation, réconciliation d'unités, projection, assemblage du rapport. Le pipeline public **orchestre**, il ne réimplémente pas | **3244 → 568** (−82 %), 19 modules nommés, 14 tranches (2026-08-01). Fichier principal **568 < 800** ; assemblage du rapport sorti du contrôle d'exécution ; boucle interne isolée dans `core/driver.py` (`PageDriver`). **Aucune fonction des modules que `S2` a produits ou déplacés ne dépasse 100 lignes** — les 4 qui restaient sont faites (`_reconcile_chunk_hyphens` 158→54, `_render_outputs` 140→83, `_route_and_filter_chunks` 110→61, `driver::_run_chunk` 104→78), et `rendering` est passé de 81 % à 97 % de couverture au passage (`tests/test_rendering_channels.py`, écrit avant le découpage). **Dette distincte, non close, épinglée** : 7 fonctions de `core/` dépassent encore 100 lignes et **préexistent toutes à `S2`** — `validator` 149, `pairing` 119, `editing` 114 et 103, `hyphenation` 110 et 101, `acceptance` 107. Deux d'entre elles (`link_hyphen_pairs`, `reconcile_hyphen_pair`) sont de la résolution de partenaire de césure : **ne pas y toucher sans finir `S1`**, règle en vigueur. Non croissantes par `tests/test_orchestrator_budget.py` | **atteinte** — reformulée le 2026-08-01 : la cible portait sur le périmètre de `S2`, pas sur les fonctions que `S2` n'a jamais touchées ; celles-là sont une dette nommée, pas une file d'attente |
| S3a | **Dire** que la surface est provisoire, là où trois documents disaient le contraire — snapshot renommé, `§8.1` corrigé (3 symboles promis et absents), règle des deux portes écrite, cliquet anti-croissance | **fait (2026-07-28)** | — |
| S3b | **Couper** : réduire la surface à la clôture transitive de ce que la façade retourne | **fait (2026-08-01) — 95 → 68**. La répartition 95 → 54 écrite ici **ne se reproduisait pas** : elle comptait la porte avancée pour ses 7 points d'entrée sans leur clôture, ce qui aurait laissé exactement les trous que `S3b` doit fermer (un appelant nommant `CorrectionPipeline` sans pouvoir nommer `ProducerOptions` ni `CorrectionRequest`). Recalculé : **deux clôtures** — ce que `load`/`correct`/`correct_sync` retournent (34 types, dont les 4 trous que le plan avait correctement identifiés) et ce que la couture producteur oblige à nommer, parce que la première phrase du README promet « any custom `EditProducer` ». **33 rétrogradés** vers leur module d'accueil (vérifié importable pour les 33), **6 ajoutés**. Laissé hors surface délibérément : la couture `FormatAdapter` (`RewriteResult`, `RewriteMetrics`, `AlignedPair`, `TokenAlignment`) — injection optionnelle, et vocabulaire interne du réécrivain que `R5`/`R8`/`L8` ont déplacé cette année ; le geler sous SemVer à `1.0` promettrait une stabilité que rien ne soutient | **68**, calculée et non choisie, close sur ses deux promesses, non croissante |
| S4 | Queue de l'ADR-011 : geler les types `Source*` (l'immuabilité repose sur une copie défensive, pas sur le type) | **partiel (2026-08-01)**. Mesuré plutôt qu'estimé — et l'item est nettement plus gros que « une demi-tranche » : **`Coords` et `DocumentManifest` sont gelés** (0 site d'écriture dans `src/`, 1 dans un test, corrigé en `model_copy`). Reste : `PageManifest`/`BlockManifest`, écrits une fois chacun par la désambiguïsation de `page_id` dans `core/pairing.py` — la même boucle réécrit des pointeurs de césure, donc c'est du territoire `S1` ; et **`LineManifest`, 246 sites d'affectation**, qui EST l'état de travail du run (`corrected_text`, `status`, les pointeurs). Le geler demande un type de travail distinct, pas une annotation. Le renommage `Source*` reste à trancher : les 4 types de manifeste sont dans la surface publique que `S3b` vient de figer à 68 | 5 types gelés, 0 mutation de manifeste hors d'un type de travail nommé |
| S5 | Écrire `docs/adr/012-*.md` : cité par le code, inexistant ; `docs/adr/README.md` s'arrête à 008 alors que 009-011 existent | **fait (2026-08-01)**. `012-loss-policy-and-per-line-attribution.md` écrit à partir du code et non de mémoire ; index complété (009-012) et entrée 004 corrigée (`institutional` → `proxy_protected`, renommé le 2026-07-28). Tenu par `tests/test_adr_references_resolve.py` : tout `ADR-NNN` cité par une source a un fichier, tout fichier est indexé, tout lien de l'index résout | — |

**`S3b` doit précéder toute publication `1.0`** : publier d'abord gèlerait 95
symboles sous SemVer. Il ne bloque en revanche pas `0.10.0`, que
`docs/versioning.md` autorise à casser. **`S2` doit précéder `S3b`.**
**`S1` doit précéder `L3`**, et porte `L2`.

---

## RM — Remédiation structurelle (audit du 2026-08-06)

Origine : un audit statique externe du dépôt, lu à `26d6f53`. Il **ne rouvre
aucun** item `L`, `R`, `M` ou `G` et ne conteste aucune priorité. Il constate
autre chose : le prix de la discipline elle-même. Un seul de ses onze constats
est un défaut au sens strict (`RM-01`) ; les autres sont de la dette dont
l'effet est un coût d'évolution, et qui tombe sur `S1`.

Les onze items tiennent tous dans les catégories que la règle de gel autorise —
correctifs, refactorisation **réductrice**, mesure, documentation de vérité,
tests. Aucun n'en sort. `RM-08` est explicitement **transmis à `S1`** et ne
s'exécute pas dans cette vague.

### Carte

| ID | Titre | Nature | Gravité | Fichiers | Dépend de | Statut |
|---|---|---|---|---|---|---|
| `RM-11` | Contradictions documentaires : `CLAUDE.md` vs ce plan sur `S1` ; 2 docstrings fausses ; 1 clause dupliquée | vérité | secondaire | `CLAUDE.md`, `core/outcome.py`, `core/quality.py`, `tests/test_import_contract.py` | — | **fait (2026-08-06)** |
| `RM-02` | Ratchet goodhartisé : mesure la longueur, pas le couplage ; périmètre limité à `core/` | outillage | important | `tests/test_orchestrator_budget.py` | — | **fait (2026-08-06)** |
| `RM-10` | `_rebuild_line` (203 l.) et `rewrite_alto_file` (161 l.) hors de toute mesure | mesure | important | `formats/alto/rewriter.py` (lecture seule) | `RM-02` | **fait (2026-08-06)** |
| `RM-05a` | Aucun test ne protège l'ordre des passes de `core/finalize.py` | tests | important | `tests/decision/` (nouveau) | — | **fait (2026-08-06)** |
| `RM-01` | L'écriture de la décision terminale d'une ligne est dispersée sur 5 modules ; l'ordre des passes est porté par une docstring | **bugfix** | **critique** | `core/decide.py` (nouveau), `core/outcome.py`, `core/acceptance.py`, `core/reconcile.py`, `core/routing.py`, `core/finalize.py` | `RM-02`, `RM-05a` | **fait (2026-08-06)** |
| `RM-04` | ~20 % du code du paquet n'est exécuté par aucun chemin par défaut et est gelé par ce plan | nettoyage | important | `__init__.py`, `pyproject.toml`, `CHANGELOG.md` | `RM-11` + ratification | **fait (2026-08-06), périmètre corrigé** |
| `RM-07` | `core` connaît les formats : `core/losses.py` porte la table des attributs ALTO ; le contrat d'import plafonne à `== 3` au lieu de nommer une règle | réducteur | important | `core/losses.py`, `core/provenance.py`, `tests/test_import_contract.py` | — | à faire |
| `RM-03` | Drilling de paramètres : 10 à 20 arguments sur le chemin chaud | réducteur | important | `core/workspace.py` (nouveau), `core/driver.py`, `core/outcome.py`, `core/reconcile.py`, `core/routing.py`, `core/pipeline.py`, `core/retry.py` | `RM-01`, `RM-02` | **fait (2026-08-06)** |
| `RM-06` | ~480 tags de vocabulaire privé, dont certains pointent vers `docs/history/` | vérité | secondaire | tout `src/` | `RM-11` | à faire |
| `RM-05b` | 124 fichiers de test organisés par vague de remédiation ; 277 imports de symboles privés | tests | important | `tests/` | `RM-05a` | à faire |
| `RM-09` | `core/schemas.py` fourre-tout : 1 538 l., 44 importateurs, 4 familles de types | nettoyage | secondaire | `core/schemas.py` → `core/schemas/` | — | à faire |
| `RM-08` | Cinq projections voisines de l'unité de césure (`_page_local_units` / `_units_visible_on_page` quasi identiques) | réducteur | important | `core/reconcile.py`, `core/units.py` | **`S1`** | **hors vague → `S1`** |

### Ordre, et pourquoi

Quatre dépendances seulement, toutes réelles :

1. **`RM-11` d'abord.** `CLAUDE.md` affirmait cinq résolveurs de partenaire
   quand ce plan en mesure zéro. C'est le document qui gouverne le travail
   quotidien ; tant qu'il est faux, chaque session part d'une carte erronée.
2. **`RM-02` avant `RM-03`.** Le ratchet actuel récompense le découpage qui
   augmente le nombre de paramètres — c'est lui qui a produit
   `_descend_granularity` à 13 arguments. Réparer les signatures sans réparer
   d'abord la métrique garantit que le prochain découpage les reproduira.
   `RM-10` est le même geste, étendu à `formats/`.
3. **`RM-05a` avant `RM-01`.** Le défaut n'est pas détectable par la suite
   actuelle : elle vérifie l'état *final* d'un run, pas sa dépendance à l'ordre
   des passes. Le test doit exister **et échouer** avant qu'on touche au code.
   Sous-dépendance : la **table de précédence des raisons de fallback** est un
   livrable de mesure, écrit avant la centralisation — le code encode
   aujourd'hui une priorité « premier arrivé » par des `if not
   trace.fallback_reason` répartis sur cinq fichiers.
4. **Ratification avant `RM-04`.** Il retire des symboles de `__all__`, que
   `S3b` vient de figer à 68 par calcul de clôture. `docs/versioning.md`
   autorise la série `0.9.x` à casser, mais dépenser cette cartouche est un
   arbitrage de produit. **Tranché le 2026-08-06 : option A** — extra
   `corrigenda[research]`, les modules restent dans l'arbre et sortent de
   `__all__` et de la couverture obligatoire. L'option B (paquet
   `corrigenda-lab` séparé) est réservée au cas où la levée du gel dépasse
   `0.10.0`.

`RM-09` arrive tard bien qu'il soit le moins risqué : avec 44 importateurs il
produit le plus gros diff de la vague. Fait en dernier, avec un
`schemas/__init__.py` qui réexporte tout, il ne touche aucun importateur.

### Lots

- **Lot RM-0 — vérité** : `RM-11`. Fait.
- **Lot RM-1 — instrument** : `RM-02`, `RM-10`. Aucun fichier de `src/`.
- **Lot RM-2 — le défaut** : `RM-05a` → table de précédence → `RM-01`.
  Le seul correctif de la vague, et le seul lot à risque élevé.
- **Lot RM-3 — dégonfler** : `RM-04`, option A.
- **Lot RM-4 — frontière** : `RM-07`.
- **Lot RM-5 — signatures** : `RM-03`. Interdit tant que RM-1 n'est pas mergé
  et RM-2 pas fermé.
- **Lot RM-6 — nettoyages progressifs** : `RM-06`, `RM-05b`, `RM-09`.

### Ce que la vague ne touche pas

`core/pairing.py`, `core/units.py`, `core/hyphenation.py` et la résolution de
partenaire de `core/reconcile.py` — territoire `S1`. `formats/alto/rewriter.py`
est **mesuré** (`RM-10`), jamais découpé : 203 lignes sur le chemin qui produit
le fichier livré, et le corpus de parité octet n'est pas encore assez large.
Les seuils de `GuardConfig` (non calibrés) et l'allowlist d'erreurs `ADR-008`
restent intacts.

### Suivi

Dernière mise à jour : 2026-08-06 — session 5. Lots `RM-0` et `RM-1` clos ;
`RM-2` en cours, filet et table clos, migration à 4 sites sur 7.
Branche : `claude/technical-repository-audit-61yzfb`.

- **Done** — `RM-11` (session 1) : règle « pas de 6ᵉ chemin » de `CLAUDE.md`
  reformulée en propriété (deux encodages, pas un compte historique) ;
  docstring de `_fall_back_to_source` qui se disait « the single place »
  corrigée ; clause dupliquée de `RoutingPolicy` réparée et alignée sur
  `core/pipeline.py` ; en-tête de `tests/test_import_contract.py` qui situait
  `_adapter_for_format` dans `core/pipeline.py` corrigé vers
  `core/provenance.py`.
- **Done** — `RM-02` + `RM-10` (session 2) : `_PARAMETER_TARGET = 8` rejoint
  `_FUNCTION_TARGET`, avec la même sémantique de cliquet et 13 fonctions
  épinglées à leur arité mesurée (`_OVERPARAMETERISED`) ; le scan passe de
  `core/*.py` à `src/corrigenda/**/*.py`, et 6 fonctions de `formats/`
  rejoignent `_OVERSIZED` à leur taille mesurée. **Épingler n'est pas
  s'engager à couper** : `formats/alto/rewriter.py` reste hors d'atteinte.
  Sensibilité vérifiée dans les deux sens puis annulée (un 10ᵉ argument sur
  `PageDriver._run_chunk` → rouge ; une fonction longue et large ajoutée à
  `formats/page/_text.py` → rouge sur les deux gardes, cas que l'ancien scan
  ne voyait pas). Aucun fichier de `src/` modifié.
- **Done** — `RM-05a` (session 3) : `tests/decision/`, trois tests, aucun
  fichier de `src/` touché. Le test d'ordre **passe** et il est pire que
  prévu : permuter deux des trois passes ne renumérote pas un rapport, il
  change le **texte livré**. Deux lignes adjacentes proposant la même
  correction depuis des sources différentes sont un doublon, et l'ordre
  canonique les révoque toutes les deux ; la porte `token_realign` passée en
  premier révoque celle dont le compte de mots change, ce qui **efface la
  preuve du doublon**, et la seconde livre alors une correction que l'ordre
  canonique rejetait — en `corrected`, sans raison, sans entrée sidecar. Un
  échange, une hallucination livrée. Le `xfail` (strict) porte la propriété
  due : un ordre faux doit être **refusé**, pas produire d'autres octets ; il
  épingle l'exigence, pas le mécanisme. La caractérisation des raisons pose
  la règle réelle — ni premier ni dernier écrivain, **les deux** : 4 écritures
  assignent, 3 défèrent derrière `if not trace.fallback_reason`. Le cliquet
  d'exclusivité épingle 22 écritures / 7 fonctions / 5 modules, ne peut que
  descendre, et exempte `core/decide.py` avant son existence.
- **Done** — `RM-01` phase 1/3 (session 4) : la règle de précédence est une
  décision motivée, `docs/adr/013-fallback-reason-precedence.md`, et non plus
  un motif à re-déduire de trois `if`. Livrable en ADR plutôt qu'en constante
  dans un `core/decide.py` neuf : le dépôt tient déjà une discipline ADR
  testée, créer le module vide allumerait trop tôt l'exemption du cliquet
  d'exclusivité, une constante sans logique serait du poids mort dans un
  paquet que `RM-04` dégonfle, et `ADR-013` est citable depuis le code là où
  `RM-01` ne l'est pas. **Décision : garder le partage 4/3** — l'écrivain
  unique de `RM-01` diffère sur les sept chemins, ce qui est un changement de
  comportement sur les quatre sites assignants **invisible parce que `I-1`
  les rend inatteignables deux fois**. Couverture des 7 sites complétée (4 →
  7) ; le cas tranchant est réécrit avec la même assertion et la lecture
  inverse — il était épinglé comme défaut à corriger, il est épinglé comme
  correction à protéger.
- **Done** — `RM-01` phase 2/3, première moitié (session 5) : `core/decide.py`
  existe et **4 sites sur 7 y passent**, un commit par site — 22 → **15**
  écritures de décision hors du writer unique. Trois verbes plutôt qu'un,
  parce qu'il y a trois choses différentes à dire d'une ligne : `accept`
  (une correction tient), `fall_back` (une correction est retirée),
  `renormalise` (une décision déjà prise tient, seule son orthographe
  change).

  **Le seul changement de comportement de la migration a été mesuré avant
  d'être fait.** `_fall_back_to_source` assignait `fallback_reason` ;
  `decide.fall_back` diffère (`ADR-013`). Les deux règles ne divergent que
  sur une collision, donc la question était : une collision est-elle
  atteignable ? Instrumenté sur tous les corpus du dépôt, avec un producteur
  échouant ~20 % de ses appels pour forcer le chemin d'épuisement — **145
  fallbacks sur 190 lignes, zéro collision**. Ce que `I-1` prédisait, et ce
  que les corpus disent maintenant.

  Deux questions tranchées et écrites là où le code est.
  `routing._confirm_skipped_lines` → `accept` : un skip est une
  **acceptation**, pas un repli, et ce que `accept` **ne** touche pas
  (`model_input_text`) est ce qui garde la signature auditable du skip.
  `finalize._preserve_break_chars` → `renormalise`, ni `accept` ni dehors :
  la passe ne décide rien, elle réorthographie une décision prise, et
  `accept` estamperait `CORRECTED` sur des lignes dont elle n'a pas à fixer
  le statut.
- **Done** — `RM-01` **fermé** (session 6) : les 3 sites restants migrés, un
  commit par site. **22 → 0** écriture de décision hors `core/decide.py`, et
  **4 → 0** écriture non conditionnelle de `fallback_reason` dans tout
  `core/`. Les deux pièges annoncés se sont levés par **preuve**, pas par
  exception : les 5 branches de rejet de `check_line` retournent
  `source_ocr` avec une raison non nulle (donc `fall_back` y écrit
  exactement le texte que le site écrivait), et `classify_reconcile_outcome`
  ne retourne `"fallback"` **que si** `final_p1 == ocr_1 and final_p2 ==
  ocr_2` — la classification est *définie* par cette égalité. Aucune
  exception écrite n'a été nécessaire. Les deux garanties sont épinglées
  (`test_acceptance_translation.py`, `test_reconcile_translation.py`) parce
  qu'elles sont invisibles au site d'appel. `hyphen_subs_content` reste dans
  `_reconcile_one_pair` : ce n'est pas un champ de décision, c'est de l'état
  de césure, et le déplacer mettrait du territoire `S1` dans `RM-01`.
- **Done** — le **garde d'ordre** (session 6) : `_FinalizeOrder`, jeton de
  séquencement **par run**, créé dans `_finalize_document`, jamais partagé.
  Écarté : un drapeau d'état sur le manifeste (remettrait de l'état de run
  sur un objet partagé, ce qu'`ADR-011` a retiré) et « un point d'entrée
  unique » (`_finalize_document` l'est déjà et ne refuse rien — les passes
  restent importables). `RuntimeError` et non `CorrigendaError` : un ordre
  faux est un bug moteur, et `CorrigendaError` est la famille que la boucle
  de chunk absorbe (`ADR-008`). Le jeton est **optionnel** — `None` =
  non vérifié — parce que c'est la seule façon pour le test de
  démonstration de tourner l'ordre faux ; l'échappatoire est fermée de
  l'autre côté par un test statique qui lit `_finalize_document` et échoue
  si une passe y est appelée sans jeton. **Le `xfail` strict est levé ; il
  ne reste aucun `xfail` dans la suite.**
- **Done** — `RM-04` (session 7), **et son périmètre était surestimé de
  moitié** : la mesure a précédé le déplacement, et elle a coupé l'item en
  deux. `integrations/qe.py` et `integrations/vision.py` — **818 des 1600
  lignes** — étaient **déjà** derrière `corrigenda[qe]` / `corrigenda[vision]`
  et **déjà** hors de la barre de couverture, avant la vague. Le mécanisme
  d'option A était en place ; ce qui manquait, c'était **ce qui tient la
  frontière**. Une entrée `pyproject.toml` et un `omit` de couverture
  n'empêchent aucun module du chemin d'installation de base d'en importer un,
  et un seul import transforme une dépendance optionnelle en dépendance
  obligatoire au runtime — la panne tombant sur qui a installé exactement ce
  que les métadonnées annonçaient. Le test de frontière est écrit et vérifié
  en sous-processus (import du paquet **et** run par défaut complet, parce
  qu'un scan statique ne voit pas un import paresseux sur le chemin chaud).
- **Périmètre retiré de `RM-04`, mesuré** : `core/routing.py`,
  `core/quality.py`, `core/confidence.py`, `core/batching.py` **ne peuvent
  pas** sortir de la couverture. Sur un run par défaut avec producteur
  factice : batching **27 %**, confidence **21 %**, quality **49 %**, routing
  **22 %**. Ils sont importés par `core/driver.py` et `core/pipeline.py`, et
  leurs chemins no-op s'exécutent à chaque run. Les omettre ne mettrait pas
  du code de recherche derrière une porte, cela **cesserait de mesurer du
  code qui part dans la wheel**. Le « 20 % non exercé » de l'audit était un
  compte d'**énoncés** juste ; ce n'était pas un compte de **modules
  séparables**, et `RM-04` ne peut déplacer que les seconds. Réduire ces
  quatre-là demande de retirer les 5 boutons correspondants du constructeur
  — rupture bien plus large, à instruire séparément, pas à glisser ici.
- **Done** — `RM-07` (session 8) : `core` n'énumère plus les formats. Le
  partage de `core/losses.py` a été **mesuré, pas jugé** — le réécriveur PAGE
  n'importait que `COUNTS_INVALIDATION` et `INVALIDATION_COUNTER` et n'a
  jamais eu besoin de la table ; ALTO en importait cinq, dont trois que seule
  la table peut répondre. La moitié partagée est donc ce que les deux formats
  lisent et qu'aucun ne possède ; tout ce que la table répond part avec elle
  dans `formats/alto/losses.py`. **Aucune valeur n'a changé** :
  `test_loss_accounting_is_real.py` est le différentiel qui compare le
  réécriveur à la table sur les trois chemins d'écriture, vert à la nouvelle
  adresse, plus la parité octet et la parité de rapport PAGE.
  `_adapter_for_format` rejoint `formats/loader.py`, à côté de la dispatch de
  parseurs qui répond à la même question. `core/rendering.py` atteint toujours
  un format — le moteur doit bien en toucher un pour écrire — mais **ne sait
  plus lesquels existent** : il demande au loader. Le seam est resté,
  l'énumération a bougé. Bilan : **3 imports interdits dans `core` → 1**.
- **Done** — le contrat d'import énonce une **règle** au lieu d'un compte
  (session 8). `assert len(violations) == 3` était un plafond : il disait
  combien d'effraction était tolérée sans dire par qui, donc une nouvelle
  violation n'importe où dans `core` restait légale tant qu'une ancienne
  disparaissait dans le même commit. C'est désormais une carte nommée
  (`_render_outputs`, `for_provider`), qui échoue dans les deux sens — une
  fonction non nommée qui atteint un format, et une fonction nommée qui a
  cessé de le faire. Une seconde règle interdit l'import de niveau module.
- **Décision tranchée** — la boucle `from corrigenda import __version__`
  (`core/rendering.py`, `core/provenance.py`) **reste ouverte**, et sur le
  fond : elle porte **un** symbole, une chaîne de niveau module ; un import
  paresseux ne peut ni interbloquer ni rendre un objet à moitié initialisé.
  La fermer veut dire déplacer `__version__` dans son module, donc éditer
  `[tool.hatch.version] path` (la source de version de la wheel) **et** le job
  CI qui grep `__init__.py` — la chaîne de publication, pour zéro gain de
  comportement, dans un item dont le sujet est « le cœur ignore les
  **formats** ». Mais elle est désormais **bornée** plutôt que simplement
  connue : les deux fichiers sont épinglés par nom et l'ensemble des symboles
  portés est épinglé à `{"__version__"}` — un troisième site ou un second
  symbole est une décision différente, pas la même.
- **Done** — `RM-03` (session 9), trois gestes. **`PageWorkspace`** : les
  trois index qui voyageaient ensemble (`line_by_id` 24 occurrences,
  `cross_page_partners` 38, `traces` 35) sont liés une fois par page. Le
  périmètre a été **mesuré avant d'être choisi** — les 9 fonctions portant
  les trois sont *exactement* le chemin de chunk, ce qui fait de la
  frontière un constat et non une préférence. Gelé, sans méthode, et la
  limite de cette affirmation est écrite : les dicts à l'intérieur sont
  l'état vivant du run, `traces` est écrit par `decide.py`, et les
  regrouper ne les rend pas immuables — ce que ça rend impossible, c'est de
  les **séparer**. Le piège nommé (en refaire le fourre-tout qu'`ADR-011` a
  retiré) est fermé par un test et non par une résolution :
  `test_page_workspace_is_not_a_bag.py` échoue sur un 4ᵉ champ, sur le
  dégel, et sur **toute** méthode — cette dernière règle étant la subtile,
  une méthode qui muterait serait un second écrivain de décision déguisé en
  objet, invisible au cliquet d'exclusivité qui scanne l'affectation
  d'attribut et non l'intention.
- **Done** — `for_provider` **19 → 9** paramètres nommés. La recopie
  manuelle de 13 arguments n'était pas seulement longue : c'était une
  **seconde déclaration** de la signature d'`__init__`, que rien ne
  contraignait à concorder — un bouton ajouté au constructeur et oublié ici
  était silencieusement inatteignable par la porte que le README met devant
  tout usager LLM. `observer` reste **nommé** à contre-courant, et c'est le
  snapshot d'API publique qui l'a attrapé : transférer un argument *requis*
  déplace l'erreur du site d'appel vers le constructeur. Le pin a résisté
  pour une vraie raison, ce qui est ce à quoi sert un pin.
- **Done** — `budget: list[int]` → `ChunkBudget`. Une cellule mutable
  déguisée en liste, correcte (une descente dépense la **même** bourse) et
  coûtant deux questions au lecteur à chacun de ses 8 sites. Délibérément
  **non gelé**, à l'inverse de `PageWorkspace` un commit plus tôt, et le
  contraste est le propos : un workspace se lit, un budget se dépense.
- **Blocked** — aucun.
- **Remaining** — `RM-01`, `RM-04`, `RM-07`, `RM-03`, `RM-06`, `RM-05b`,
  `RM-09`.
- **New bugs discovered** — un, trouvé en étendant le ratchet et corrigé dans
  le même geste (l'instrument était en cause, pas `src/`) : la clé était le
  nom nu de la fonction, donc un fichier déclarant deux fois le même nom
  n'en mesurait qu'un. `core/confidence.py::score_line` et
  `core/quality.py::needs_correction` existent chacun en double (protocole,
  puis implémentation) et une moitié de chaque paire échappait au test. Clés
  désormais qualifiées, et les quatre définitions sont épinglées.
- **New bugs discovered** — deux phrases brouillées de plus dans `core/
  schemas.py`, **non corrigées** (P6 : hors périmètre d'une session
  tests-only, et `src/` ne devait pas bouger) : `LossPolicy.
  min_alignment_score` dit « Calibration against a real corpus is the job of
  a calibration against a real corpus » ; `ConfidencePolicy` dit « locked
  until the calibration against a real corpus harness proves the values
  against a real corpus ». Même famille que la clause dupliquée de
  `RoutingPolicy` fermée par `RM-11` — un mot a manifestement été substitué
  en masse dans les docstrings à un moment. À ramasser avec `RM-06`.
- **~~New bugs discovered~~ — RETIRÉ (session 4, vérifié faux).** La session 3
  annonçait que l'attribution d'une révocation pouvait être fausse et que
  `CorrectionResult.fallback_reasons` comptait faux d'autant de lignes
  signalées deux fois. **C'est inexact.** Le constat de code était juste
  (`_apply_unit_reverts` écrit texte et statut sans condition, la raison
  seulement dans une trace vide) ; l'inférence ne l'était pas. Elle supposait
  qu'une ligne puisse porter une raison **tout en tenant encore une
  correction**, ce qui n'arrive pas :

  > **I-1 — une ligne porteuse d'un `fallback_reason` est déjà revenue à sa
  > source : son texte final égale son texte OCR.**

  Mesuré, pas supposé : producteur adverse sur `X0000002`, `sample`, les
  quatre fixtures PAGE et `corpus_gt`, sous trois politiques de perte — **756
  lignes décidées, les 8 familles de raisons, zéro ligne** porteuse d'une
  raison en tenant une correction. Une seconde révocation est donc
  **idempotente** sur le texte ; la passe qui a réellement retiré la
  correction est la première, et différer est ce qui garde la raison
  **vraie**. Le dernier-écrivain-gagne nommerait une passe qui n'a rien fait.
  Tranché et écrit en `ADR-013` ; `I-1` est désormais un test.
- **New bugs discovered** — aucun en session 4.
- **New bugs discovered** — session 8, **non corrigé** (P6) :
  `LOSS_MATRIX_VERSION` n'est **lu par personne**. Son commentaire dit « les
  consommateurs du rapport y accrochent leurs attentes, pas à la version de
  la bibliothèque » — or il n'apparaît dans aucun champ de
  `CorrectionReport`, dans aucun test, dans aucun script. C'est un contrat
  versionné qui n'est émis nulle part : soit il rejoint le rapport, soit le
  commentaire cesse de promettre. À trancher avec `R*`, pas ici.
- **New bugs discovered** — aucun en session 9 ; aucun en session 7 ni 6.
- **New bugs discovered** — session 5, **non corrigé** (P6, hors périmètre) :
  `LineTrace.projected_text` peut être périmé pour un consommateur.
  `_finalize_chunk_traces` le fixe au `corrected_text` du moment, puis
  `_preserve_break_chars` réécrit `corrected_text` sans le rafraîchir. Le
  champ est écrit à 6 endroits et **lu nulle part dans `src/`** — c'est de
  l'information pure pour l'hôte, et `LineTrace` est dans la surface
  publique. Sans effet sur le texte livré ni sur les décisions, donc hors
  `L*`. `decide.renormalise` a délibérément gardé le comportement
  historique (aucune écriture de trace) plutôt que de corriger au passage.
- **Tests added** — session 2, `tests/test_orchestrator_budget.py` : `RM-02`
  ajoute `test_no_unnamed_function_exceeds_the_parameter_target`,
  `test_known_overparameterised_functions_only_shrink`,
  `test_finished_signatures_are_not_still_listed` ; `RM-10` ajoute
  `test_the_scan_sees_the_whole_package` ; le trou de clés ajoute
  `test_keys_are_unique_per_definition`. 11 → 34 cas dans le module.
- **Tests added** — session 3, `tests/decision/` (5 fichiers, 19 cas dont 1
  `xfail` strict et 1 `skip` conditionné à l'existence de `core/decide.py`) :
  `test_finalize_pass_order.py` (l'ordre change le texte livré ; un ordre
  faux n'est pas refusé), `test_fallback_reason_precedence.py`
  (caractérisation des 7 écritures de raison + épinglage statique du partage
  4/3), `test_decision_write_exclusivity.py` (cliquet des 22 écritures).
  Premier répertoire de tests groupé par **invariant** et non par vague —
  amorce de `RM-05b`.
- **Tests added** — session 9, `tests/test_page_workspace_is_not_a_bag.py`
  (4 cas) : champs exacts, gel, aucune méthode, et le gel exercé plutôt
  qu'introspecté.
- **Tests added** — session 8, `tests/test_import_contract.py` : la règle
  nommée remplace le compte (`test_only_the_named_sites_reach_a_format_or_producer`),
  l'interdit d'import de niveau module (`test_no_core_module_reaches_out_at_import_time`),
  et la borne sur l'auto-import du paquet
  (`test_the_package_self_import_stays_where_it_was_measured`). Sensibilité
  vérifiée puis annulée : un 3ᵉ site d'accès depuis `core` échoue **par nom**.
- **Tests added** — session 7, `tests/test_research_boundary.py` (8 cas) :
  le paquet et un run par défaut ne chargent aucun module derrière un extra
  (sous-processus), et les 6 chemins d'import des 4 scripts de calibration
  résolvent toujours — « derrière une porte » ne doit jamais devenir
  « déplacé ».
- **Tests added** — session 4, `tests/decision/test_fallback_reason_precedence.py`
  passe de 6 à 21 cas : un pin par site (1-3 `_apply_line_acceptance`, 6
  `_refresh_pair_traces` × 3 branches), le mécanisme qui empêche les sites
  assignants de se croiser (l'acceptation saute toute ligne déjà décidée), et
  **`I-1` bout-en-bout** paramétré sur 2 corpus × 3 politiques de perte, avec
  une garde contre le vert par vacuité : si le producteur adverse cesse de
  produire des fallbacks, le test échoue au lieu de passer sans rien vérifier.
- **Risks remaining** — `RM-01` reste ouvert, et la session 3 a relevé son
  enjeu : la classe de défaut visée n'est pas seulement une ligne
  `CORRECTED` portant son texte source (`L9`), c'est une **correction non
  validée qui part dans le fichier** dès que deux passes s'exécutent dans le
  mauvais ordre. Démontré, pas supposé.
- **Risks remaining** — (levé) propre à `RM-1` : la consigne « plafond, pas
  file d'attente » a été tenue — `integrations/vision.py`,
  `producers/llm_edit.py` et `formats/alto/rewriter.py::_emit_string` sont
  intacts. Il reste **8 entrées**, et ce qui reste est une dette d'une autre
  nature avec une autre réponse : les deux constructeurs de `pipeline` sont
  de la **surface de configuration**, pas du threading, et `_attempt_chunk`
  / `_build_correction_report` **assemblent** depuis plusieurs sources au
  lieu de faire suivre une seule chose. Aucun `PageWorkspace` ne les aidera ;
  les réduire demande de trancher ce que le pipeline expose, ce qui touche
  `RM-04` et le gel. À instruire, pas à enchaîner.
- **Risks remaining** — propre à `RM-05a` : les trois tests visent des
  fonctions privées et sont **délibérément tournés vers l'implémentation**.
  C'est le prix d'un filet posé avant la correction ; `RM-01` doit les
  réécrire, pas les contourner, et le `xfail` strict est ce qui force la
  question à se reposer le jour où le garde arrive.

### Mesures de référence — base 2026-08-06, à recomparer à la clôture

Arités mesurées `self`/`cls` exclus : ce qu'un APPELANT doit assembler.

| Métrique | Base | Courant | Cible |
|---|---|---|---|
| Écritures de décision (`corrected_text`/`status`) | 22 énoncés, 7 fonctions, 5 modules | **0** hors `core/decide.py` | atteint |
| Écritures de `fallback_reason` | 4 sans condition / 3 différées | **0 / 2**, un seul écrivain | atteint |
| Ordre des passes de finalisation | contrat en docstring, 0 garde | **refusé si faux** (`_FinalizeOrder`) | atteint |
| `xfail` dans la suite | 1 (strict, `RM-01`) | **0** | 0 |
| Fonctions > 100 lignes, `core/` | 7 (toutes épinglées) | **6** | ≤ 7 |
| `I-1` (raison ⇒ ligne revenue à sa source) | vraie, non énoncée, 0 test | énoncée (`ADR-013`), 6 tests | tenue par `RM-01` |
| Paramètres, maximum du paquet | 19 (`for_provider`) | **11** | ≤ 8 |
| Fonctions > 8 paramètres | 13 | **8**, épinglées | 0 hors liste |
| Fonctions > 8 params sur le chemin de chunk | 9 | **3** | 0 |
| Fonctions > 100 lignes, paquet entier | 13, dont 6 hors mesure | 13, épinglées | ≤ 13 |
| Définitions sous mesure | 0 hors `core/` | 348, paquet entier | tout `src/` |
| Symboles dans `__init__.__all__` | 68 | **66** | atteint (`RM-04`) |
| Modules derrière un extra, frontière tenue | 2 gelés, 0 test | 2 gelés, **3 tests** | tenue |
| Imports interdits dans `core/` | 3, plafonnés par un compte | **1**, nommé par une règle | 1 (seam d'écriture) |
| Noms de format cités dans `core/` | ALTO ×12 attributs + dispatch | **0** | 0 |
| Imports de symboles privés depuis `tests/` | 277 | 277 | en baisse |
| Ratio (commentaires + docstrings) / code, lib | 0,79 | 0,79 | non ciblé, mesuré |
| Couverture bibliothèque | 96,4 % (seuil 85 %) | 96,4 % | ≥ 85 % |

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
| T1 | **Métamorphiques** — **entamé** (`test_metamorphic_hyphenation.py`) : page vide insérée → mêmes décisions **et** paire toujours liée (a trouvé le cas `L5` de la page vide) ; même coupure intra-page ou inter-pages → même texte ; tout signe du répertoire apparie pareil. Même document découpé autrement → même décision (`fcd7804`) ; mêmes pages regroupées autrement → même décision ; même césure intra-page ou inter-pages → même résultat logique ; page vide ajoutée → aucune autre décision ne bouge ; signe de coupure substitué par un équivalent autorisé → unité conservée |
| T2 | **Corpus adversarial** — le corpus de formes qui n'existe pas : U+00A0 et U+202F, gamme complète des tirets, chaînes de 3-4 membres, césure inter-pages réelle, lignes sans `SUBS_TYPE`, lignes vides et éléments non textuels intercalés, ALTO de plusieurs producteurs, PAGE Transkribus et eScriptorium réels |
| T3 | **Différentiels** — comparer décision logique, texte réextrait, octets XML, attributs conservés, géométrie, compteurs de perte et statut de ligne. « Le XML est valide » n'est pas le résultat attendu. **Entamé, trois invariants** : `test_status_truthfulness.py` (statut × texte source × proposition) a trouvé `L10` sur le fichier BnF ; `test_payload_truthfulness.py` (ce qu'on dit au modèle × ce que porte le manifeste) a trouvé la promesse de jointure fausse ; `test_link_symmetry.py` (A pointe B ⟺ B pointe A) — **résultat négatif** : la symétrie tient sur le corpus généré et les fixtures réelles, ce sur quoi le cœur de `S1` pourra s'appuyer |

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

## D — Vérité documentaire — **close (2026-07-28)**

Le 25 juillet a consolidé `docs/` ; **les documents d'entrée n'ont pas suivi**.
`D8`-`D11` étaient les trois portes par lesquelles un lecteur arrive.

**Les douze sont fermés.** Le motif récurrent mérite d'être noté, parce qu'il
se reproduira : dans **cinq** cas sur douze le corps du texte était juste et
c'est le **nom** ou le **titre** qui mentait — `institutional` (`D12`),
`PUBLIC_API_1_0` (`S3a`), le titre d'`I4` (`D1`), les en-têtes de version du
`CHANGELOG` (`D4`), l'arbre `§3` (`D2`). Un lecteur fait confiance à
l'étiquette avant le paragraphe. Et dans **deux** cas, l'énoncé du plan était
lui-même inexact (`D2` plus large, `D4` plus dur), ce qui est la raison de
mesurer avant de corriger.

| id | item |
|---|---|
| ~~D1~~ | **fait** — vérifié le 2026-07-28 : `SPECS §I4` est titré « Le cœur est aveugle aux pixels » et porte la portée en trois niveaux ; `packages/corrigenda/README.md` dit « **the core** forwards an opaque image reference and touches no pixel ». Remplacement de mots, aucun arbitrage — la conception, elle, était déjà juste et vérifiée mécaniquement |
| ~~D2~~ | **fait (2026-07-28)** — et plus large que l'énoncé. L'arbre `§3` décrivait un paquet nommé `lib/` avec **7** modules de cœur, sans `integrations/`, sans `errors.py`, sans `facade.py`, et avec un `producers/llm.py` inexistant ; le vrai cœur en a **21**. Réécrit depuis l'arborescence réelle. `§5.1` montrait `produce(payload: ModelPayload, *, policy: RetryPolicy)` : un type qui n'existe pas, et le `RetryPolicy` complet que **P3.7 a précisément retiré** de cette couture — la spec contredisait sa propre prose sur `ProducerOptions` |
| ~~D3~~ | **fait (2026-07-28)** — `0.0021` porte désormais sa provenance : un **VLM oracle**, producteur simulé qui rend la vérité terrain. Le chiffre mesure le **routage**, pas un modèle. Lu comme une borne supérieure de ce que le routage peut acheter, jamais comme une revendication de qualité |
| ~~D4~~ | **fait (2026-07-28) — et le vrai constat est plus dur que l'énoncé.** Le nombre a grossi : **1 221** lignes / **81** entrées sous `[Unreleased]` (827 au 25/07). Mais le défaut n'est pas la taille : le `CHANGELOG` porte **trois en-têtes de version datés** (`[0.9.0]`, `[0.9.0 initial scope]`, `[0.1.0a1]`) alors qu'il existe **0 tag git** et **0 publication** — des jalons de développement présentés comme des versions. Corrigé en tête de fichier, sans mentir : rien n'a jamais été publié, donc rien n'est dû à personne, et la section qui porte tout l'historique des ruptures d'API est bien celle que SemVer déclare non engageante. Plus un **index des ruptures** (13 entrées) pour qu'elles soient une *liste* et non une trouvaille au défilement. Découper une section de release demande un tag : c'est `P1`/`P2`, pas ici |
| ~~D5~~ | **fait (2026-07-28) — l'asymétrie était juste, son silence ne l'était pas.** On dispatche sur `report.report_version`, le **champ** lu sur l'artefact qu'on tient : la constante dit ce que *cette* installation émet, donc la comparer à un rapport chargé n'apprend rien sur ce rapport. D'où la différence avec `EDIT_PROTOCOL_VERSION`, exporté : la version du protocole d'édition, un producteur la **déclare** ; celle du rapport, un lecteur la **trouve**. Écrit dans `versioning.md`, avec le chemin de module pour l'outil qui a vraiment besoin de la constante. Ajouter la constante à `__all__` aurait fait **grandir** la surface, ce que le cliquet de `S3a` interdit |
| ~~D6~~ | **fait (2026-07-28)** — `packages/corrigenda/docs/reading-a-report.md` : pour chaque chiffre du rapport, ce qu'il dit **et ce qu'il ne dit pas**. `0 fallback` = « aucune proposition refusée », ce qui est presque l'inverse de « rien n'a changé » ; `format_losses is None` ≠ « rien n'a été perdu » (un caractère aplati est compté sur l'échelle de fidélité) ; `exact` compare le fichier à la **décision**, pas à la vérité. Plus la section qu'aucun chiffre ne couvre : les gardes sont **structurelles** — aucune ne connaît le français, et une lecture plausible, fluide et fausse les passe toutes |
| ~~D7~~ | **fait (2026-07-28) — zéro sur les quatre.** Mesuré avant : `src/`+`app/` **27** `ROADMAP V3` / **69** `Phase N` / **25** `Audit-F`, tests **33 / 56 / 4 / 1**. Après : **0 / 0 / 0 / 0** dans tout `.py` et dans les documents normatifs. La forme dominante était une **étiquette de provenance** devant une phrase qui portait déjà sa raison : l'étiquette part, la phrase reste. Les usages en prose (« la calibration de Phase 2 ») sont remplacés par la **raison** — « la calibration contre un corpus réel » — parce qu'un numéro de jalon d'une feuille de route gelée n'est pas consultable. Quatre fichiers de test dont le **nom** était l'étiquette ont été renommés d'après ce qu'ils testent. **Incident à retenir** : la première passe portait une règle de rangement de parenthèses qui a recollé des fermetures multi-lignes dans **213 fichiers** — syntaxiquement valide, donc les tests seraient passés au vert sur un diff qui reformatait tout le dépôt. Revertée. Un balayage sur du source touche le **texte** des commentaires, jamais la forme du code autour |
| ~~D8~~ | **fait** — le `README` annonce ALTO **et** PAGE dès le titre, l'accroche et la matrice de versions |
| ~~D9~~ | **fait** — la carte documentaire nomme `docs/PLAN.md` comme **le** plan unique et `docs/audit/` comme les constats, à côté de l'avertissement sur `docs/history/` |
| ~~D10~~ | **fait** — `SECURITY.md` ne renvoie plus vers `docs/history/` : vérifié, zéro occurrence. La question qui décide de l'adoption ne pointe plus vers un document gelé |
| ~~D11~~ | **fait** — vérifié le 2026-07-28 : la seule chaîne visible par l'utilisateur dit « Upload ALTO / PAGE files ». Les occurrences restantes d'« ALTO » dans `frontend/src` sont des commentaires internes et des fixtures de test |
| ~~D12~~ | **fait (2026-07-28)** — `institutional` → **`proxy_protected`**. Le corps de `SECURITY.md` était honnête (pas de comptes, pas de propriété de job, pas de quotas, pas de base, mono-worker) ; le **nom** disait l'inverse de son propre paragraphe. Le nouveau nom énonce exactement ce qui est asserté : un proxy authentifiant est devant, rien de plus. `DEPLOYMENT_PROFILE` est une variable **publique**, donc l'ancienne valeur reste acceptée et **avertit** — et pas seulement par courtoisie : une valeur inconnue retombait sur le défaut tolérant au CORS joker, donc un simple renommage aurait fait **accepter en silence** ce qu'un opérateur avait demandé de refuser. Cinq tests, dont celui du message d'erreur qui doit nommer le **nouveau** nom |

---

## P — Publication

| id | item |
|---|---|
| P1 | Répétition sur TestPyPI (le workflow n'a jamais été exercé, 0 tag git) | **répétée en local (2026-08-01), upload non fait** — il demande l'OIDC de GitHub Actions. Toute la chaîne du workflow rejouée : `python -m build`, `twine check` (PASSED sur les deux artefacts), smoke-install de la wheel (`_smoke_imports.py` : 68 symboles publics), SBOM CycloneDX + l'assertion anti-pollution, cohérence `__version__` ↔ CHANGELOG, forme du tag attendu (`corrigenda-v0.9.0`). **Deux constats, corrigés** : (a) le sdist livré ne correspondait pas à son allowlist — hatchling traite les entrées comme des MOTIFS, donc `README.md` attrapait `tests/corpus_gt/README.md` et `tests/external_corpus/pinned/README.md` ; aucune donnée de corpus n'est jamais partie, mais le test de packaging vérifiait la *déclaration* et non l'artefact. Entrées ancrées (`/README.md`), test réécrit pour lire le sdist et la wheel CONSTRUITS. (b) la CI sautait `twine check` sur une raison périmée (twine < 7 rejetait `License-File` de Metadata 2.4) : twine 7 l'accepte, vérifié sur cette wheel, la porte est rétablie | reste : dispatcher le workflow sur `testpypi` depuis GitHub, ce qui exige le tag donc `P2` |
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

**Vague `RM` — structurelle, s'intercale avant `S1`.** `RM-0` (vérité) est fait.
`RM-1` (instrument) et `RM-2` (le défaut `RM-01`) précèdent tout autre travail
sur `core/` : le premier répare la métrique qui gouverne les découpages, le
second ferme la seule classe de défaut latent de la vague. `RM-3` à `RM-6`
peuvent s'intercaler librement. **`RM-1` et `RM-2` doivent précéder `S1`** —
`S1` est le plus gros refactor restant sur `core/`, et l'engager avec une
métrique qui récompense le drilling et sans garde sur l'ordre des passes
reproduirait dans la famille césure ce que `S2` a produit dans
l'orchestration. `RM-08` est un constat d'entrée de `S1`, pas un item séparé.

`Gate 0` en parallèle sur Desktop, du premier jour au dernier — c'est le seul
item qui peut bloquer `P2` sans avertissement.

---

## Clos — déplacé dans `docs/history/`

- `AUDIT-2026-07-13.md` + `PLAN-CORRECTIONS.md` — 37 findings, exécutés intégralement.
- `PLAN-REMEDIATION-2026-07-15.md` — vagues 1-4 livrées ; seul reliquat `V4.5`,
  repris ici en `P3`.
- `PLAN-1.0-2026-07-15.md`, `ROADMAP_LIB_V3.md` — remplacés par ce document.
