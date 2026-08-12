# Autopilot — la file de travail autonome

Ce fichier est **l'état**, pas un compte rendu. Une session réveillée par la
Routine n'a pas mon contexte : elle a ce fichier, `docs/PLAN.md`, et le dépôt.
Si les trois se contredisent, `docs/PLAN.md` gagne et ce fichier est corrigé.

Dernière mise à jour : 2026-08-12.

---

## Le contrat de boucle — piloté par les événements

**La PR ouverte est l'unité de travail, et « verte » est la condition de
sortie de chaque tour.** La boucle ne tourne plus à l'horloge : elle reprend
sur **événement** de la PR — résultat de CI, commentaire de revue, push,
conflit de merge — et rend la main quand la PR est verte et qu'il n'y a rien
en attente.

PR courante : **[#71](https://github.com/maribakulj/corrigenda/pull/71)**,
`claude/rm-session-10-nettoyages-qb74pu` → `main`. La session y est abonnée.

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

### 1. `S3b` — couper la surface publique à sa clôture

**État : à faire. C'est le plus gros item restant qui soit entièrement
autonome, et il est entièrement spécifié.**

`docs/PLAN.md` §`S3` a calculé la cible : **54 symboles** (50 gardés + les 4
trous : `Coords`, `ProjectionFidelity`, `ReconcileMetrics`,
`CORRECTION_REPORT_VERSION`). La surface est à **68** aujourd'hui — `RM-04`
l'a déjà dégonflée depuis 95. Les 45 rétrogradés ont tous un module d'accueil
réel, vérifié par le plan.

Contrainte que le plan pose explicitement : **la coupe et la mise à jour des
appelants sont le même commit**, sinon le dépôt se casse lui-même. Coût
mesuré : 32 lignes d'import, dont 6 en production, toutes pour
`sanitize_error`.

**Mesuré le 2026-08-11, et la cible est renversée** — voir `docs/PLAN.md`
§ « Mesure du 2026-08-11 ». La surface est **4 trop grande et 9 trop
petite**, pas 41 trop grande : la clôture des retours (34 types) est
intégralement exportée, et la porte avancée exige 9 types qu'on ne peut pas
importer depuis le sommet. La question devient « la porte est-elle
publique ? », et aucune clôture n'y répond.

**L'arbitrage est tranché** (décision déléguée n°5, 2026-08-11) : **la porte
est publique, `S3b` devient « la fermer »** — ajouter les 9, rétrograder les
4, reformuler `V5` en « ce que la bibliothèque retourne *et accepte* ». La
mesure et sa garde sont faites
(`tests/test_public_surface_is_the_closure.py`) ; **reste l'exécution**, qui
est un geste à part entière : la coupe et la mise à jour des appelants sont le
même commit, et `_LAZY` doit suivre `__all__` (un test l'exige).

**Fini quand** : l'arbitrage est tranché ; `corrigenda.__all__` vaut la cible
qui en découle ; les rétrogradés sont importables depuis leur module, prouvé
par un test ; la lib, le backend et les scripts sont verts ;
`docs/versioning.md` et le `CHANGELOG` disent la rupture.

### 2. `RM-08` — fusionner les projections voisines de l'unité

**État : à faire, et son blocage a été levé (voir « Décisions déléguées »).**

Cinq projections voisines, dont `_page_local_units` et
`_units_visible_on_page` quasi identiques. Le plan les bloquait derrière `S1`
au motif qu'unifier avant que l'unité soit autoritaire produirait une 6ᵉ
formulation. La fusion est autorisée **à la condition qu'elle ne touche pas au
stockage de référence** : les champs pointeurs restent la vérité, on retire
des lectures redondantes, on n'en ajoute aucune.

**Fini quand** : le nombre de projections a baissé, aucune nouvelle n'existe,
`tests/hyphenation/` est vert sans modification de cas, et
`tests/test_internal_seams_are_named.py` reflète les symboles qui ont disparu.
**Si la fusion exige de rendre l'unité autoritaire, s'arrêter** : c'est `S1`,
et `S1` est parké.

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
  filet toutes les 6 h. Prochain geste : exécuter `S3b`.
