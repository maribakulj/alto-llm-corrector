# Les promesses du contrat, et ce qui les garde

Ce document existe parce qu'un compteur ne mesurait pas la bonne chose.

`T1`/`T3` — les propriétés métamorphiques et différentielles — n'ont pas de
fin naturelle : on peut en écrire indéfiniment. La borne posée en août 2026
disait « s'arrêter après six propriétés sans qu'aucune ne trouve de
défaut ». Elle butait sur une question qu'elle ne pouvait pas trancher :
deux propriétés n'avaient trouvé aucun défaut du produit, mais un **angle
mort de la suite entière** — une mutation réaliste que les 1400 autres
tests laissaient au vert. Est-ce trouver quelque chose ?

La borne a été remplacée le 2026-08-16 (décision n°8) : **chaque promesse
vérifiable de `SPECS_LIB_V2.md` a au moins une propriété qui la garde,
prouvée par mutation. Quand la liste est couverte, `T1`/`T3` est clos — pas
épuisé, clos.**

Ceci est la liste. Elle est établie depuis ce que le contrat **promet**, et
non depuis ce que les tests couvrent déjà : bâtie dans l'autre sens, elle se
serait moulée sur l'existant et n'aurait rien trouvé.

## Comment lire les verdicts

- **gardée** — au moins un test vérifie la propriété elle-même. Un test qui
  touche au sujet sans vérifier la propriété ne compte pas.
- **partielle** — la propriété est vérifiée sur une partie de son domaine.
  Ce qui manque est nommé, parce qu'une couverture partielle non dite se lit
  comme une couverture.
- **aucune** — rien ne la garde. Deux de ces cas ne sont pas des trous de
  test mais des trous d'**implémentation** : la garde n'existe pas.

## Relevé du 2026-08-16

| # | promesse | verdict |
|---|---|---|
| I1 | le texte ne voyage jamais sans son ancre ; la recomposition est une écriture indexée | **gardée** |
| I2a | rien n'atteint le XML sans passer les gardes ; au doute, repli sur la source | **gardée** |
| I2b | une édition structurelle est **inexprimable** dans le protocole | **aucune** — l'interdit à l'exécution est bien tenu, mais rien ne fige l'union `EditOp`. Ajouter un `MergeLines` ne fait rougir aucun test |
| I3 | IDs, géométrie, ordre XML, attributs non textuels préservés quand rien ne change | **gardée** |
| I4a | le cœur et les formats n'importent aucune bibliothèque d'image | **gardée** |
| I4b | l'installation de base n'embarque aucune dépendance image | **fermée le 2026-08-16** — voir plus bas |
| I4c | l'extra `[vision]` importe Pillow paresseusement | **gardée** |
| E1 | `line_id` dans le chunk visé | **partielle** — le seul test confond « hors chunk » et « inconnue » ; retirer la première clause laisse la suite verte |
| E2a | spans sans chevauchement | **gardée** |
| E2b | application **de droite à gauche** | **aucune** — le test éponyme emploie deux spans de **longueur égale** : le résultat est identique dans l'autre sens |
| E3a/c/d | pas de `\n` et non-vide pour `replace_line` ; suppression permise par span | **gardées** |
| E3b | pas de `\n` sur la voie `replace_span` | **aucune** — la garde existe, rien ne l'exerce |
| E3e | rejet quand un span viderait la ligne | **aucune** — branche morte côté tests |
| E4a | borne de dérive **par op** | **partielle** — une seule op : rien ne prouve le « par op », ni le contrôle négatif sous la borne |
| E4b | budget de caractères modifiés, élagage préfixe/suffixe | **gardée** — le mieux tenu du lot |
| E4c | le budget est **par ligne**, cumulé sur plusieurs ops | **aucune** — les quatre tests E4 sont mono-op |
| E5a | une ligne de césure garde son tiret final | **partielle** — rôle `BOTH` et marques non-ASCII (`⸗`, `¬`) absents, alors que le répertoire est paramétré partout ailleurs |
| E5b | son **mot-frontière** ne peut pas être supprimé | **aucune, et la garde n'existe pas** — voir plus bas |
| E6a | les gardes s'appliquent au texte issu d'un span | **partielle** — l'étage sémantique n'est jamais exercé sur une sortie de span |
| E6b | span et `replace_line` obtiennent le même verdict sur le même résultat | **aucune** |
| F2a | liste blanche d'attributs en slow path | **partielle** — un seul attribut hors liste est relu dans la sortie |
| F2b | `WC`/`CC`/`SUBS_*` jamais recyclés | **gardée** |
| — | parité d'octets ALTO quand rien ne change | **partielle** — sha256 golden + sous-ensemble verbatim, pas la sérialisation entière |
| — | parité d'octets PAGE | **partielle, proche d'aucune** — texte seulement, aucun sha256 |
| §6.3 | texte canonique identique entre formats | **gardée**, sur une page |
| §6.3 | rôles de césure équivalents entre formats | **aucune** — le test qui porte ce titre compare deux variantes du **même** format |
| — | somme des pertes par ligne = agrégat | **partielle** — vérifiée sur ALTO, où l'accord est structurel ; pas sur PAGE, le seul format où les deux comptes sont calculés indépendamment |
| — | le rapport dit du fichier ce qui y est | **partielle** — contenus et identités gardés, compteurs non |
| — | rejouer le script rendu reproduit le fichier | **partielle** — ALTO seulement, alors que PAGE porte les transformations post-décision que la propriété existe pour attraper |
| — | niveaux de fidélité déclarés | **partielle** — ALTO seulement ; PAGE ne peut structurellement jamais annoncer `source_spelling`, et que ce soit correct n'est vérifié nulle part |
| — | `run()` ne mute jamais son entrée | **partielle** — jamais comparé sur l'objet entier ; les champs de césure, que le planificateur modifie réellement sur sa copie, ne sont pas couverts |
| — | identité de ligne = `(page_id, line_id)` | **gardée**, ALTO et PAGE |
| — | paires de césure atomiques dans le découpage | **gardée**, sous une forme plus honnête que la promesse : ensemble, **ou** séparées avec un `HyphenSplit` enregistré |
| — | l'ordre des fichiers d'entrée ne change rien | **partielle** — prouvé sur un corpus jouet de deux fichiers d'une ligne, là où c'est trivial |
| — | une seconde passe est un point fixe | **partielle** — PAGE absent |
| — | césure inter-pages | **gardée** |

## Les deux trous d'implémentation

Ce ne sont pas des tests manquants. Ce sont des promesses écrites que le
code ne tient pas.

**E5b — le mot-frontière n'est protégé par rien.** `_e5_hyphen_ok` retourne
`True` sans condition pour `PART2`, et sa docstring dit que le mot-frontière
est « garanti par le contrôle de non-vacuité ». Il ne l'est pas : sur une
ligne `PART2` valant `« sieurs et le reste »`, effacer `« sieurs »` laisse
une ligne non vide, donc acceptée — et la paire se relit `« plu- »` +
`« et le reste »`. Le mot qui continuait le mot coupé a disparu. La
non-vacuité garantit que la *ligne* survit, pas que le *mot-frontière*
survit ; ce sont deux propriétés différentes et la docstring les confond.

**Reste à trancher avant de corriger** : la forme exacte de la règle. « Ne
pas supprimer le mot-frontière » est clair pour un humain et flou pour un
prédicat — une édition légitime peut corriger ce mot (`ſieurs` → `sieurs`).
La formulation conservatrice serait : un span ne peut pas supprimer
entièrement, sans remplacement, la plage couvrant le premier mot d'une ligne
`PART2`/`BOTH`. C'est une décision de conception, pas un portage.

**I4b — fermé le 2026-08-16.** Aucun test ne lisait `[project].dependencies`.
Celui qui en avait l'air comparait la provenance à un tuple codé en dur dans
la source : ajouter `pillow` au `pyproject` laissait tout vert. C'était la
promesse la plus facile à casser en silence de tout le lot, et sur
l'invariant que le projet met en avant le plus souvent.

## Le motif dominant

**PAGE est le format sous-gardé.** Six promesses passent de gardée à
partielle pour cette seule raison, et toujours de la même façon : la
propriété est écrite, exercée sur ALTO, et le second format n'est pas
ajouté. C'est d'autant plus coûteux que PAGE est le format où plusieurs de
ces propriétés sont *moins* structurellement vraies — la comptabilité des
pertes y est calculée par deux chemins indépendants, là où ALTO l'alimente
depuis un site unique.

**Et plusieurs tests d'EditScript sont mono-op**, ce qui neutralise
exactement les invariants qui parlent de pluralité : `E2b` (droite à
gauche), `E4a` (par op), `E4c` (cumul par ligne). Un invariant sur
l'interaction de plusieurs opérations, testé avec une seule, ne teste rien.

## Ce que ce document n'est pas

Une liste de tâches à faire dans l'ordre. C'est un relevé : il dit ce qui
est tenu et ce qui ne l'est pas, à une date. `docs/PLAN.md` dit ce qu'on en
fait.
