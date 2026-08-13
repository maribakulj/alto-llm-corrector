# Autopilot — la file de travail autonome

Ce fichier est **l'état**, pas un compte rendu. Une session réveillée par la
Routine n'a pas mon contexte : elle a ce fichier, `docs/PLAN.md`, et le dépôt.
Si les trois se contredisent, `docs/PLAN.md` gagne et ce fichier est corrigé.

Dernière mise à jour : 2026-08-13.

---

## Le contrat de boucle — piloté par les événements

**La PR ouverte est l'unité de travail, et « verte » est la condition de
sortie de chaque tour.** La boucle ne tourne plus à l'horloge : elle reprend
sur **événement** de la PR — résultat de CI, commentaire de revue, push,
conflit de merge — et rend la main quand la PR est verte et qu'il n'y a rien
en attente.

**PR courante :** [#72](https://github.com/maribakulj/corrigenda/pull/72),
ouverte le 2026-08-13 depuis `main` après le merge de
[#71](https://github.com/maribakulj/corrigenda/pull/71), et abonnée.

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
   chaque commit (`pytest` dans `packages/corrigenda`), plus `ruff check`,
   `ruff format --check` et `python -m mypy --strict src/corrigenda` avec le
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

Dans l'ordre. Un item se ferme quand son « fini quand » est vérifiable par
quelqu'un qui n'a pas suivi le travail.

### ~~1. `S3b`~~ — **déjà fait, retiré de la file le 2026-08-12**

`S3b` a été exécuté le **2026-08-01** et affiné par `RM-04` le 2026-08-06. Les
66 symboles actuels sont la clôture calculée, pas une accumulation, et
`tests/test_public_api_snapshot.py` porte le raisonnement complet.

Cet item figurait ici parce que `docs/PLAN.md` le décrivait encore comme
différé. **C'est le premier vrai piège de cette file** : un item peut être
clos dans le code et ouvert dans le plan, et la file hérite du plan. Corollaire
ajouté aux règles permanentes : *avant d'attaquer un item, vérifier dans le
code qu'il est encore ouvert.*

Ce que la tentative laisse : `tests/test_public_surface_is_the_closure.py`,
qui **recalcule** les deux clôtures de promesse à chaque run (34 types
retournés, 17 types du seam producteur, tous exportés) et épingle le prix du
troisième seam — les 9 noms que fermer `format_adapter`/`qe_scorer`/
`routing_policy`/`confidence_policy` coûterait, comme prix d'une décision et
non comme défaut.

### ~~2. `RM-08`~~ — **clos par la mesure le 2026-08-12, sans fusion**

Le constat était périmé, et la règle n°6 l'a attrapé : vérifié dans le code,
les deux projections lisent zéro pointeur et partagent la dérivation. Ce ne
sont plus des résolveurs parallèles mais **deux filtres d'une dérivation**,
qui divergent sur une chaîne quittant la page — le routeur voit `{}`, le
batcher voit les deux membres présents, et fusionner changerait l'un des deux
comportements en silence.

`tests/hyphenation/test_the_unit_projections_are_not_duplicates.py` l'exhibe
plutôt que de l'affirmer, et rouvrira l'item tout seul si un changement futur
les rend d'accord partout. Détail et raison dans `docs/PLAN.md`.

### 3. `T1` / `T3` — étendre métamorphiques et différentiels

**État : entamé, sans fin définie — donc borné ici.**

Le plan est explicite sur le pourquoi : les deux défauts d'intégrité de ligne
du 25 juillet sont sortis de la **mesure**, pas des tests, parce que « la
population de tests est trop proche des abstractions du code ». `T1` a trouvé
le cas de la page vide ; `T3` a trouvé `L10` et la promesse de jointure fausse.

**Borne** : trois propriétés nouvelles par réveil au maximum, chacune devant
échouer sur une mutation délibérée du code avant d'être commitée (sinon elle
ne teste rien). S'arrêter après six propriétés ajoutées sans qu'aucune ne
trouve de défaut — à ce stade l'écart est ailleurs et il faut le mesurer.

**Compteur : 4 propriétés ajoutées, 0 défaut trouvé** (2026-08-13). Deux
avant l'arrêt prévu par la borne.

Ce que la mutation délibérée a déjà payé, deux fois :

- la première version de la propriété « l'ordre des fichiers » comparait les
  octets livrés, passait au vert, et **ne détectait pas** la famille de
  défaut pour laquelle elle était écrite — `F4` corrompait le script
  d'édition en laissant le XML correct ;
- la mutation qui fait réutiliser le `postProcessingStep` précédent au lieu
  de l'ajouter laisse **toute la suite au vert** sauf la propriété qui vient
  d'être écrite. Ce n'est plus une vérification de la propriété, c'est une
  mesure de ce qu'elle apporte, et c'est la façon la moins chère de
  distinguer une propriété neuve d'une redite.

**Conséquence de méthode, à garder** : chaque nouvelle propriété se juge sur
sa mutation, et la mutation se lance **sur toute la suite**, pas seulement
sur le module. Une propriété que d'autres tests attrapent déjà n'est pas
fausse — elle ne compte simplement pas contre la borne.

### 4. `S4` — geler ce qui peut l'être

**État : partiel, et le reste est en grande partie hors d'atteinte.**

`Coords` et `DocumentManifest` sont gelés. `PageManifest`/`BlockManifest` sont
écrits par la désambiguïsation de `page_id` dans `core/pairing.py` — territoire
interdit. `LineManifest` a 246 sites d'affectation et **est** l'état de travail
du run.

**Autorisé ici** : uniquement documenter précisément ce qui bloque chaque type,
avec la mesure. **Interdit** : toucher `core/pairing.py`, ou entreprendre le
gel de `LineManifest`, qui est « un type de travail distinct » et non une
annotation.

### 5. `M1` (moitié hors-ligne) — préparer le corpus multi-pages

**État : à faire, et c'est la seule moitié de `M*` qui ne demande pas de run.**

Le chemin inter-pages n'est mesuré par **aucun** run : aucun fichier du corpus
ne finit sur un mot coupé, et le banc traite chaque fichier comme un document
d'une page. `corpus/BnF-bpt6k3265015q/` ne contient qu'un feuillet
(`X0000002`).

**Autorisé** : construire la fixture multi-pages à partir de ce qui est déjà
dans le dépôt, et écrire le harnais qui la consommera. **Interdit** :
télécharger quoi que ce soit — c'est `M5`/`M6`, licence et réseau, donc CLI.

---

## Passe la main au CLI

Ces items ne sont pas dans la file et ne doivent pas être tentés ici. Ils sont
listés pour que la raison soit lisible, pas pour être contournés.

| item | ce qu'il exige |
|---|---|
| `M2`, `M3` | ≥5 runs par configuration, ≥2 familles de modèles : clés API, budget, réseau |
| `M4`, `M7` | re-mesurer après `542c783` : les mêmes runs |
| `M5`, `M6` | télécharger et **trancher des licences** de corpus externes |
| `G1`-`G3` | `review_required` : décider *quelles règles* envoient en revue — conception |
| `P1`, `P2` | l'upload exige l'OIDC de GitHub Actions ; le tag est une décision de publication |
| `P3` | revue humaine externe |

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
