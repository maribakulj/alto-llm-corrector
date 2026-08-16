# Autopilot — la file de travail autonome

Ce fichier est **l'état**, pas un compte rendu. Une session réveillée par la
Routine n'a pas mon contexte : elle a ce fichier, `docs/PLAN.md`, et le dépôt.
Si les trois se contredisent, `docs/PLAN.md` gagne et ce fichier est corrigé.

Dernière mise à jour : 2026-08-16.

---

## Le contrat de boucle — piloté par les événements

**La PR ouverte est l'unité de travail, et « verte » est la condition de
sortie de chaque tour.** La boucle ne tourne plus à l'horloge : elle reprend
sur **événement** de la PR — résultat de CI, commentaire de revue, push,
conflit de merge — et rend la main quand la PR est verte et qu'il n'y a rien
en attente.

**PR courante :** [#77](https://github.com/maribakulj/saknussemm/pull/77),
ouverte le 2026-08-16 depuis `main`, et abonnée. Une PR jumelle vit dans
`cinoc` — [#80](https://github.com/maribakulj/cinoc/pull/80) — et la boucle
surveille les deux : depuis le 2026-08-16 le travail s'étend à trois dépôts,
donc « verte » se qualifie sur chacun de ceux qu'un geste touche.

Quand une PR est mergée, la souscription meurt avec elle et **la boucle n'a
plus de moteur événementiel tant qu'aucune autre n'est ouverte** — c'est le
filet toutes les 6 h qui reprend la main, et c'est normal, pas une panne. Le
premier geste d'une nouvelle tranche est donc d'ouvrir une PR depuis une
branche neuve partant de `main`, puis de s'y abonner : sans ça, « verte »
n'a rien à qualifier.

Ordre de priorité à chaque réveil, sans exception :

1. **CI rouge, ou commentaire de revue en attente → c'est ça le travail.**
   Rien d'autre ne commence tant que la PR n'est pas revenue au vert. Une
   régression trouvée par la CI passe avant n'importe quel item de la file :
   elle est déjà payée, il ne reste qu'à la lire.
2. **PR verte et file non vide** → l'item non clos le plus haut, un geste, un
   commit, un push.
3. **Sinon** → arrêt, avec la raison au journal.

**Deux réserves qui ont valeur de règle.** Les webhooks ne livrent pas tout —
succès de CI, nouveaux pushes et passages en conflit arrivent en retard ou pas
du tout. Donc : *vérifier l'état réel de la PR plutôt que le supposer*, et un
**filet horaire toutes les 6 h** existe pour le cas où aucun événement
n'arrive. Ce filet n'est pas le moteur ; s'il fait le travail, c'est qu'un
événement s'est perdu.

**Et le vert local ne vaut pas le vert de la CI.** La CI exécute la suite sur
**3.11, 3.12 et 3.13**, plus le backend, le frontend, la dérive des types
OpenAPI, la construction Docker et le paquet. Un geste vert ici peut être
rouge là-bas — c'est précisément à ça que sert la PR, et c'est pour ça que
« verte » et non « la suite passe chez moi » est la condition de sortie.

---

## Règles permanentes

1. **Un geste, un commit vert.** La suite de la bibliothèque passe avant
   chaque commit (`pytest` dans `packages/saknussemm`), plus `ruff check`,
   `ruff format --check` et `python -m mypy --strict src/saknussemm` avec le
   pin de `[typecheck]` — le `mypy` du conteneur peut être d'une autre version
   et ne pas voir pydantic ; 55 faux positifs en sont sortis une fois.
2. **En cas de doute, s'arrêter et écrire la question.** Ne jamais trancher un
   arbitrage de produit. Les décisions déjà prises sont dans `docs/PLAN.md`,
   section « Décisions déléguées » ; tout ce qui n'y est pas et qui engage la
   surface publique, un coût, une licence ou une dépendance externe est un
   arrêt.
3. **Ne rien attaquer qui exige clés, réseau, argent ou humain.** Ces items
   sont listés plus bas sous « Passe la main au CLI » et ne sont pas dans la
   file. Les rencontrer est une condition d'arrêt, pas un problème à
   contourner.
4. **`P5` tient partout** : aucun cas de test supprimé, noms et docstrings
   conservés lors d'un déplacement, et la preuve est le diff des noms
   collectés par `pytest --collect-only`.
5. **Ce que la vague RM s'interdit reste interdit** : `core/pairing.py`,
   `core/hyphenation.py`, `formats/alto/rewriter.py` ne sont pas découpés.
6. **Avant d'attaquer un item, vérifier dans le CODE qu'il est encore
   ouvert.** Un item peut être clos dans le code et resté ouvert dans le plan
   — `S3b` l'était, et la file en a hérité. Le plan décrit l'intention ; les
   tests décrivent l'état.

### Conditions d'arrêt

La boucle s'arrête — et écrit pourquoi ici — dès que l'une est vraie :

- la CI est rouge pour une cause qu'on ne sait pas lire après une tentative ;
- la suite locale est rouge et la cause n'est pas le geste en cours ;
- l'item suivant exige clés, réseau, budget, licence ou revue humaine ;
- l'item suivant demande un arbitrage absent de « Décisions déléguées » ;
- deux réveils consécutifs sans progrès mesurable ;
- la file est vide.

---

## La file

**Réécrite le 2026-08-16.** Les cinq items précédents sont clos ou déplacés :
`S3b` et `RM-08` étaient déjà faits, `T1`/`T3` change de borne (décision n°8),
`S4` reste de la documentation pure, et `M1` part au banc avec le reste de la
mesure. La file suit désormais les phases des décisions du 2026-08-16.

Dans l'ordre. Un item se ferme quand son « fini quand » est vérifiable par
quelqu'un qui n'a pas suivi le travail.

### 1. Phase 0 — socle d'autonomie

**Fini quand** : ce fichier et `docs/PLAN.md` ne contredisent plus le dépôt, la
PR courante est ouverte et abonnée, et le smoke-test de déploiement de `cinoc`
teste une route qui existe.

- réconcilier ce journal et la section `M` du plan ✅
- inscrire les dix décisions du 2026-08-16 dans `docs/PLAN.md` ✅
- `cinoc` : la sonde de smoke interrogeait `/api/reports`, route supprimée
  répondant 404, en `curl -s` sans `-f` ✅ *(cinoc #80, mergée)*
- armer réellement la boucle ✅

### 2. Phase 1 — la scission

**Fini quand** les trois dépôts existent, chacun avec sa CI verte, et
qu'aucun ne contient ce qui appartient à un autre.

- `saknussemm-demo` : extraire `backend/`, `frontend/`, `tools/e2e/`,
  `Dockerfile`, `docker-compose.yml`, `docs/API.md`, `SECURITY.md`,
  `.github/workflows/hf-sync.yml`
- `cinoc` : recevoir `corpus/`, `measurements/`, `integrations/qe.py` et les
  quatre scripts QE
- ici : **retirer** le banc local (décision n°3), aplatir
  `packages/saknussemm/*` à la racine, réduire la CI aux cinq jobs de la
  bibliothèque
- garder ici : `examples/` — **60 fichiers de test en dépendent**, les
  fixtures sont la suite de tests d'une bibliothèque de parsing

**Attention, mesuré** : dans `corpus/37-GT-BNL`, les XML pèsent 552 Ko et les
PNG 33 Mo. La bibliothèque garde ses fixtures pour ~2 Mo et laisse partir tout
le poids. Cinq fichiers de test seulement touchent au corpus.

### 3. Phase 2 — la bibliothèque devient publiable

**Fini quand** aucun code livré n'échappe à la CI et que le `CHANGELOG` porte
une section de version.

- **le trou le plus sérieux** : aucun job n'installe `[vision]` ni `[qe]`.
  `tests/test_vision.py` (14 tests) se saute en silence sur les trois versions
  de Python, et `integrations/vision.py` est hors de la porte de couverture.
  Ajouter un job qui installe Pillow (gratuit) ; `[qe]` part au banc, ce qui
  ferme l'autre moitié
- couper une section de release dans le `CHANGELOG` (1316 lignes sous
  `[Unreleased]`)
- `T1`/`T3` sous sa nouvelle borne : établir d'abord la **liste des promesses**
  de `SPECS_LIB_V2.md`, puis une propriété par promesse non gardée
- `CLAUDE.md`, `README`, `CONTRIBUTING` remis en accord avec un dépôt sans démo

### 4. Phase 3 — `0.10.0rc1`, puis `0.10.0`

**Passe la main au CLI** pour le dispatch et les deux configurations externes.
Voir le tableau plus bas.

### 5. Phase 4 — l'intégration au banc

**Fini quand** `cinoc` sait répondre à « ce correcteur a-t-il déplacé du texte
entre les lignes ? ». Cinq briques, chacune utile à `cinoc` indépendamment de
`saknussemm` :

1. une étape `LAYOUT → LAYOUT` et une source ALTO/PAGE — aujourd'hui un run
   part **uniquement d'une image**
2. des métriques d'**identité de ligne** — `Line.id` est parsé et réécrit des
   deux côtés, **aucune métrique ne le lit** ; le patron existe pour les régions
3. la **dé-césure** `HypPart1/2` dans le projecteur — spécifiée dans le code,
   différée depuis toujours
4. des **runs répétés** — zéro mécanisme aujourd'hui, toute la dispersion
   affichée est inter-documents ; c'est ce que `M2` exige
5. la **vision pour l'adapter Ollama**, aujourd'hui `text_only` — c'est ce qui
   débloque `M3` à coût nul

Puis le moteur `saknussemm` lui-même (décisions n°4 et n°5).

### 6. Phase 5 — la mesure, sur le banc

`M2` rejouée post-correctif, `M3` par modèles locaux, `M1` (qui demande aussi
la notion de volume côté banc), `M7`. `M5` reste ici : c'est une porte de CI de
ce dépôt, et elle demande de retirer `continue-on-error`.

### 7. Phase 6 — `review_required` (`G1`-`G3`)

La dernière fonctionnalité, et un ADR avant toute ligne de code. `V4`.

## Passe la main au CLI

Ces items ne sont pas dans la file et ne doivent pas être tentés ici. Ils sont
listés pour que la raison soit lisible, pas pour être contournés.

| item | ce qu'il exige |
|---|---|
| `M2` | la moitié Mistral coûte de l'argent : plafond de dépense, donc arbitrage |
| `M5`, `M6` | **quels** corpus télécharger — un choix de projet, pas un critère technique. Les licences, elles, sont tranchées (`Gate 0`) |
| `G1`-`G3` | `review_required` : décider *quelles règles* envoient en revue — conception |
| `P1`, `P2` | deux configurations externes que seul le mainteneur peut faire : déclarer le *trusted publisher* sur pypi.org **et** test.pypi.org, et créer les environments GitHub `testpypi` / `pypi`. Puis dispatcher le workflow |
| `P3` | revue humaine externe |

**Ce qui a quitté ce tableau le 2026-08-16** : `M3` ne demande plus ni clé ni
budget (modèles locaux, décision n°10) ; `M4` est réfuté et doit être réécrit
avant d'être planifié ; `M7` est largement acquis par le déménagement au banc.

**Rappel qui vaut contrainte** : aucune revendication chiffrée ne sort du
dépôt sans `M2` + `M3`. Vérifié le 2026-08-11 — les deux `README` ne portent
aucun chiffre, et le rester est une contrainte sur toute note de version.

---

## Journal

Une ligne par réveil : date, item, résultat, ou la raison de l'arrêt.

- 2026-08-11 — file écrite, Routine armée.
- 2026-08-11 — `S3b` : mesure faite, **cible renversée**, garde posée
  (`test_public_surface_is_the_closure.py`, 4 cas). **Arrêt** : l'item demande
  un arbitrage absent des « Décisions déléguées » — la porte avancée est-elle
  publique ?
- 2026-08-11 — arbitrage **tranché** (décision n°5) : la porte est publique.
  `S3b` reste en tête de file, son contenu est maintenant exécutable sans
  décision : ajouter 9, rétrograder 4, reformuler `V5`, mettre `_LAZY`,
  `docs/versioning.md` et le `CHANGELOG` en accord.
- 2026-08-12 — **PR #71 ouverte**, 23 commits, **CI verte 17/17** (dont la
  suite sur 3.11/3.12/3.13, le backend, la dérive OpenAPI et le paquet). La
  boucle est recâblée sur les événements de la PR ; le cron passe de horaire à
  filet toutes les 6 h.
- 2026-08-12 (filet) — PR verte, 0 fil de revue, `mergeable_state: clean`.
  `S3b` attaqué, **puis annulé en cours de geste** : la lecture de
  `test_public_api_snapshot.py` a montré qu'il était **déjà fait** depuis le
  2026-08-01 et que les « 9 trous » sont un troisième seam laissé ouvert par
  écrit. Surface restaurée à 66, décision n°5 annulée, mesure du plan
  rétractée, règle n°6 ajoutée. Reste acquis : la garde qui recalcule les deux
  clôtures. **Prochain item : `RM-08`.**
- 2026-08-12 (filet) — PR verte 17/17, 0 fil de revue. `RM-08` **clos par la
  mesure, sans toucher au code** : constat périmé, les deux projections
  partagent la dérivation et divergent pour une raison écrite. Test de
  divergence ajouté (3 cas, sensibilité vérifiée en simulant la fusion). Le
  cliquet des internes a attrapé le test lui-même — symbole nommé. **Deux
  items de suite se sont révélés déjà clos ; c'est un motif, pas une
  coïncidence : le plan décrit l'intention, le code décrit l'état.**
  Prochain item : `T1`/`T3`.
- 2026-08-13 (filet) — PR verte 17/17, 0 fil de revue. `T1`/`T3` : **2
  propriétés ajoutées**, chacune vérifiée par mutation délibérée. (1) l'ordre
  des fichiers d'entrée ne change rien de ce que le run rend — la première
  version ne détectait pas `F4` et a été élargie au script d'édition ; (2) la
  somme des pertes par ligne reproduit l'agrégat — une promesse **écrite dans
  le contrat et vérifiée nulle part**, la famille `R1`. Aucun défaut trouvé.
  Prochain réveil : suite de `T1`/`T3` (4 propriétés avant la borne).
- 2026-08-13 (filet) — PR #72 verte 17/17, `mergeable_state: clean`, 0 fil
  de revue. `T1`/`T3` : **1 propriété ajoutée** — ce que le rapport dit du
  fichier, relu dans le fichier. Le réécriveur documente son raccourci (les
  textes de sortie sont lus sur l'arbre, « without a second full parse of
  the output ») ; rien ne relisait les octets réellement rendus. **Deuxième
  angle mort de la suite entière en deux tours** : `.replace(b"\xc2\xa0",
  b" ")` sur `etree.tostring`, une expression, laisse les **1407** autres
  tests au vert pendant que chaque fichier livré perd son espace insécable.
  Compteur à 5/6, et la question de ce que « trouver un défaut » veut dire
  est posée plus haut plutôt que tranchée. Prochain réveil : la 6ᵉ propriété
  déclenche la borne — donc `S4` (documentation seule) si le mainteneur n'a
  pas répondu.
- 2026-08-13 (filet) — aucune PR ouverte, donc aucun événement : le filet
  fait exactement ce pour quoi il existe. Branche repartie de `main`, **PR
  #72 ouverte et abonnée**, puis `T1`/`T3` : **2 propriétés ajoutées**. (1)
  `T3` — rejouer le script d'édition rendu doit reproduire le fichier rendu,
  une promesse écrite dans la docstring de `_build_final_edit_script` et
  comparée nulle part ; (2) `T1` — une seconde passe sur la sortie ne bouge
  rien sauf le `postProcessingStep` qu'elle ajoute. **La seconde a trouvé un
  angle mort de la suite entière** : réutiliser le pas de provenance au lieu
  de l'ajouter laisse les 1404 autres tests au vert. Aucun défaut dans le
  code. Compteur à 4/6. Prochain réveil : `T1`/`T3` (2 avant la borne), puis
  `S4` en documentation seule.
- 2026-08-13 — **PR #71 mergée** dans `main` (27 commits). Avant merge, deux
  décisions déléguées ont été trouvées **vidées de leur contenu** par la
  découverte que `S3b` était déjà fait : « pas d'extension de surface tant que
  `S3b` n'a pas coupé » ne contraignait plus rien, et « `S3b` avant tout tag »
  était satisfait avant d'être écrit. Reformulées, pas laissées. **Prochain
  geste : nouvelle branche depuis `main`, nouvelle PR, s'y abonner.**
- 2026-08-14 — **PR #72 mergée**, puis #74 (`T3` : la même phrase posée au
  réécriveur PAGE) et #75 (les deux cliquets de décision ne voyaient qu'une
  orthographe de l'écriture). Ces trois tours **n'ont pas été journalisés à
  l'époque** : la boucle a mergé sans repasser ici, ce que la règle du dépôt
  interdit. Réparé le 2026-08-16, à la lecture.
- 2026-08-16 — **PR #76 mergée** : la campagne `M2`, cinq runs. Non journalisée
  non plus, et c'est la plus coûteuse des trois omissions, parce que la
  campagne **invalide ses propres chiffres** : le correctif de banc `2e0b7bc`
  arrive après les cinq runs. La ligne `M2` du plan décrivait encore la
  campagne comme à faire, avec les chiffres de juillet. Le motif est celui que
  `D*` avait fermé et qui revient dès qu'on cesse de le surveiller : **le plan
  décrit l'intention, le code décrit l'état, et personne ne les rapproche.**
- 2026-08-16 — revue d'état complète demandée par le mainteneur, puis
  cartographie de `cinoc` par trois agents. Deux constats qui ne venaient
  d'aucun document : `cinoc` **est** le banc que ce plan s'apprêtait à
  reconstruire (1667 tests, 96 % de couverture, 24 métriques, Space en ligne),
  et il ne mentionne `saknussemm` **nulle part**. Les deux projets sont
  complémentaires sur la ligne exacte où chacun est aveugle : `cinoc` compare
  des pages aplaties et ne lit jamais `Line.id` ; `saknussemm` garantit la
  ligne et ne sait mesurer qu'un CER, dans un script faussé. Dix décisions en
  ont découlé (`docs/PLAN.md`), et cette file est réécrite autour.
- 2026-08-16 — **le renommage.** `corrigenda` devient `saknussemm` : 1979
  occurrences, 312 fichiers, quatre chemins, PR #80. Les quatre empreintes
  de parité d'octets ont bougé et ont été **classées avant d'être
  re-figées**, en rendant la même fixture avec le code d'avant dans un
  worktree : trois lignes de diff, toutes dans le tampon de provenance,
  10280 octets des deux côtés — les deux noms font la même longueur. Zéro
  dérive de ligne. `docs/history/` garde l'ancien nom, et une note en tête
  dit pourquoi : ces documents ont été écrits quand c'était le nom, et
  l'historique git le portera de toute façon. L'ordre des imports du
  backend a cassé — trouvé par la CI, pas en local, parce que la règle
  n'était activée que d'un côté. **Même leçon que l'extra `[test]` deux PR
  plus tôt : ce qui n'est déclaré qu'à un endroit finit par diverger.**
- 2026-08-16 — **la scission.** `saknussemm-demo` créé, public, 282 commits
  filtrés, 467 tests. Puis PR #81 : 148 fichiers retirés d'ici. Deux
  oublis de ma part rattrapés par un rouge plutôt que par un silence —
  l'installation depuis git échouait (`Multiple top-level packages
  discovered in a flat-layout`, d'où `#subdirectory=`), et un **second**
  `Dockerfile` copiait encore la bibliothèque. Le premier a transformé
  l'aplatissement de l'arbre en nécessité technique et non plus en
  préférence.
- 2026-08-16 — **trouvé en cherchant autre chose.** En cherchant un corpus
  multi-pages pour `M1`, la sonde Gallica a buté sur des ALTO BnF refusés à
  la porte : namespace d'éditeur (`bibnum.bnf.fr/ns/alto_prod`), et
  déclaration d'encodage fausse (ISO-8859-1 annoncé, UTF-8 réel). Les deux
  fermés, PR #79. Le parseur et le réécriveur étaient agnostiques depuis
  toujours — **la porte était le seul endroit marqué du dépôt.** `M1` reste
  ouvert : le corpus n'a pas été trouvé, le défaut si.
- 2026-08-16 (suite) — **la scission est finie, et onze dettes avec.**
  `saknussemm` ne contient plus que la bibliothèque : 347 fichiers suivis,
  la démo dans son dépôt, les corpus et les campagnes au banc, le scorer QE
  déposé là-bas aussi. Réglé au passage : la porte marquée sur un namespace
  d'éditeur, une déclaration d'encodage crue sur parole, l'environnement de
  test déclaré dans un workflow, la garde de publication égarée dans le
  backend, deux angles morts de la garde de profondeur, une exclusion de
  couverture justifiée par une raison devenue fausse, quatre sauts
  silencieux, le double parsing (−23 % au chargement), le corpus externe qui
  ne bloquait aucun merge (`V7` tenu), `.cache/` non ignoré, cinq références
  pourries dans la démo, et une garde de licence restée orpheline.

  **Le motif, énoncé une fois pour qu'on le reconnaisse plus vite** :
  presque chacune de ces dettes était une garde plus étroite que ce qu'elle
  prétendait couvrir, ou une raison écrite une fois et jamais revérifiée.
  Élargir la garde a trouvé, chaque fois, plus que la lecture : deux sauts
  silencieux lus contre quatre trouvés ; un `Dockerfile` vu contre deux
  existants ; deux portes lxml surveillées contre quatre réelles.

  **Et trois fois dans la journée, le vert local n'a pas valu le vert de la
  CI** : PyYAML présent d'un côté seulement, tri d'imports activé d'un seul
  côté, `.cache/` présent en local et absent là-bas. La vérification se fait
  désormais dans la condition de la CI, pas dans la sienne.

  Reste ici : retirer l'extra `[qe]` quand le dépôt du banc l'a accepté, et
  couper une section de release dans un `CHANGELOG` qui porte 1316 lignes
  sous `[Unreleased]`. Reste au mainteneur, et ça bloque la `0.10.0rc1` :
  les secrets HF de la démo, et le *trusted publisher* PyPI.
