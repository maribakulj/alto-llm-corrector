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
| E1 | `line_id` dans le chunk visé | **fermée le 2026-08-19** — la clause était *inatteignable*, pas mal testée : `attempt.py` passait TOUTES les lignes du chunk comme `chunk_line_ids`, donc « hors ensemble » n'était vrai que là où « inconnue » l'était déjà (constat du 2026-08-17). Elle passe désormais les **cibles**, et une édition sur une ligne de contexte est **refusée** avec son propre code `e1_context_line` au lieu d'être silencieusement jetée en aval. Le texte corrigé ne bouge pas — la suite entière est restée verte — seule la trace apparaît, ce que `edit_rejections` (`A2b`, 2026-08-17) permet enfin de porter. `test_a_context_edit_is_refused_not_dropped.py` |
| E2a | spans sans chevauchement | **gardée** |
| E2b | application **de droite à gauche** | **fermée le 2026-08-16** — un span qui change de longueur sépare enfin les deux ordres |
| E3a/c/d | pas de `\n` et non-vide pour `replace_line` ; suppression permise par span | **gardées** |
| E3b | pas de `\n` sur la voie `replace_span` | **fermée le 2026-08-16** |
| E3e | rejet quand un span viderait la ligne | **fermée le 2026-08-16** |
| E4a | borne de dérive **par op** | **partielle** — une seule op : rien ne prouve le « par op », ni le contrôle négatif sous la borne |
| E4b | budget de caractères modifiés, élagage préfixe/suffixe | **gardée** — le mieux tenu du lot |
| E4c | le budget est **par ligne**, cumulé sur plusieurs ops | **fermée le 2026-08-16** — deux ops de 8 caractères, refusées sous un budget de 12, acceptées sous 20 : c'est le cumul qui décide |
| E5a | une ligne de césure garde son tiret final | **fermée le 2026-08-16** — `test_e5_covers_every_break_mark_and_both_roles.py` balaie les six marques du répertoire × les deux rôles ouvrants, dans les deux sens (sectionner est refusé, préserver passe) plus un contrôle sur `NONE`. La marque que la suite exerçait, `-`, est la seule que le corpus n'emploie pas : les fixtures appariées marquent tout avec `¬` |
| E5b | son **mot-frontière** ne peut pas être supprimé | **aucune, et la garde n'existe pas** — voir plus bas |
| E6a | les gardes s'appliquent au texte issu d'un span | **partielle** — l'étage sémantique n'est jamais exercé sur une sortie de span |
| E6b | span et `replace_line` obtiennent le même verdict sur le même résultat | **aucune** — et ce n'est pas seulement une non-parité : `editing.py:329` dit en clair que la voie ligne entière ne passe ni par `E4` ni par `E5`, donc les deux gardes ne s'appliquent pas au producteur par défaut. Arbitrage en cours ; depuis le 2026-08-17 les refus qui ONT lieu sont au moins visibles (`A2b`) |
| F2a | liste blanche d'attributs en slow path | **partielle** — un seul attribut hors liste est relu dans la sortie |
| F2b | `WC`/`CC`/`SUBS_*` jamais recyclés | **gardée** |
| — | parité d'octets ALTO quand rien ne change | **partielle** — sha256 golden + sous-ensemble verbatim, pas la sérialisation entière |
| — | parité d'octets PAGE | **fermée le 2026-08-17** — `test_byte_parity_page_corpus.py` : quatre golden sha256 (deux fixtures × identité/scripté), et deux assertions qui valent plus que les empreintes. **Un run d'identité ne change aucun élément** — recensement d'éléments identique, les 20 octets de plus étant l'estampille de provenance ; ça survit à un changement justifié d'empreinte, ce qu'une empreinte ne fait pas. Et **chaque `<Word>` supprimé est compté** : `words_dropped` égale exactement le nombre de `<Word>` manquants des octets livrés (47 et 7), vérifié sur **les deux canaux** — la somme par ligne et le total du run. Le second a été ajouté après qu'une mutation ait traversé le premier : le compteur par ligne est *diffé* autour de chaque ligne (ADR-012), donc un décalage constant s'y annule. Quatre mutations mordent |
| §6.3 | texte canonique identique entre formats | **gardée**, sur une page |
| §6.3 | rôles de césure équivalents entre formats | **fermée le 2026-08-16** — `test_hyphen_roles_agree_across_formats.py` compare les deux détections sur les fixtures appariées : 44 lignes partagées, zéro désaccord sur rôle, partenaire, contenu `SUBS` et caractère explicite. Deux mutations se sont révélées inertes : la branche `BOTH` des deux parseurs est redérivée par le linker partagé |
| — | somme des pertes par ligne = agrégat | **fermée le 2026-08-16** — étendue à PAGE, le format où les deux comptes sont calculés indépendamment. Ils s'accordent : vérifié, plus supposé |
| — | le rapport dit du fichier ce qui y est | **partielle** — contenus et identités gardés, compteurs non |
| — | rejouer le script rendu reproduit le fichier | **fermée à tort le 2026-08-16, rouverte et fermée le 2026-08-17** — l'extension à PAGE était bonne et le verdict était faux : le script publié portait les ops que les gardes avaient REFUSÉES. Mesuré — livré `'Le peuple att-'`, publié le span refusé, rejeu `'Le peuple -'`. Le test restait vert parce qu'il pilote un producteur à lignes entières, donc le chemin « span refusé » n'était jamais emprunté. `test_the_published_script_carries_no_refused_op.py` assertit désormais le rejeu, pas l'absence d'une op |
| — | niveaux de fidélité déclarés | **fermée le 2026-08-16, et elle cachait un défaut** — PAGE annonçait `exact` sur un fichier décomposé qu'il orthographie autrement. Voir plus bas |
| — | `run()` ne mute jamais son entrée | **gardée** — `test_the_input_manifest_comes_back_untouched.py` compare les deux `model_dump()` complets, ALTO et PAGE, sous un producteur qui change le compte de mots ; plus le condensat du fichier source, que rien ne vérifiait. Mesuré : une fuite d'un seul pointeur de césure laisse `test_reentrancy_guard.py` vert et fait rougir celui-ci |
| — | identité de ligne = `(page_id, line_id)` | **gardée**, ALTO et PAGE |
| — | paires de césure atomiques dans le découpage | **gardée**, sous une forme plus honnête que la promesse : ensemble, **ou** séparées avec un `HyphenSplit` enregistré |
| — | ~~l'ordre des fichiers d'entrée ne change rien~~ | **FAUSSE, le 2026-08-17** — et « partielle » était trop généreux : la promesse est *contredite* par un comportement ratifié, pas partiellement couverte. Mesuré sur cinq fichiers réels : inverser l'ordre change les octets de 2 fichiers sur 5, l'entrelacer de 4 sur 5, le même ordre deux fois de 0 sur 5. Cause : `link_cross_page_hyphens` parcourt les pages *adjacentes* sans connaître les fichiers source, donc fichiers consécutifs = pages consécutives — ce que `tests/test_parser.py` affirme deux fois, fixtures nommées `page1.xml`/`page2.xml`, y compris pour le cas heuristique. Un fichier par page est la façon dont une bibliothèque numérique exporte un volume, donc c'est une fonctionnalité. Reste vraie et gardée : la moitié qui parlait d'`ADR-009`, aucune identité clée sur ce qui n'est unique que dans un fichier — vérifié sur 1808 lignes réelles, seules les lignes de couture bougent. Voir `test_input_order_on_the_real_corpora.py` |
| — | une seconde passe est un point fixe | **fermée le 2026-08-19** — PAGE ajouté via `formats.loader`, donc les deux formats sont le même test et pas deux copies. Le dépouillement de provenance a dû devenir format-conscient : ALTO écrit un élément par passe, PAGE 2013 **ajoute une ligne** à un unique `Metadata/Comments`, et un compteur d'éléments lisait ça « zéro passe ». Sensibilité mesurée sur quatre mutations ; la limite trouvée est écrite dans le test — une transformation déterministe appliquée aux DEUX passes est un point fixe par construction, donc cette propriété voit une asymétrie écriture/lecture, jamais un rewriter stablement faux |
| — | un artefact divergent n'est jamais livré | **gardée, et son rayon réduit le 2026-08-19** — la promesse tenait, sa portée était fausse : un fichier divergent faisait perdre le run entier, rapport compris. Le fichier est maintenant **absent** de `corrected_files` et nommé sur `undeliverable_files` ; `write()` refuse l'ensemble incomplet sauf `allow_partial=True`. Le contre-argument — un mot coupé à cheval sur deux fichiers livré à moitié — a été mesuré avant de décider : **0 sur 1 583 unités de césure** de deux fascicules Gallica réels, détecteur vérifié contre un positif fabriqué. Voir `test_projection_invariant.py`, `test_every_undeliverable_file_is_named_at_once.py` |
| — | césure inter-pages | **gardée** |

## Le défaut que le relevé a fait sortir

En vérifiant la dernière « partielle » de la liste — les niveaux de
fidélité, tenus sur ALTO et jamais sur PAGE — la raison écrite s'est
révélée fausse, et le défaut derrière elle réel.

`EXACT` promet la chose la plus forte de l'échelle : *l'artefact dit la
décision, caractère pour caractère*. `L8` avait trouvé cette promesse
rompue sur ALTO — 115 lignes s'en réclamaient pendant que le fichier
portait `U+00AD` là où la lecture rendait `-`. Le remède ne fut pas un
invariant plus strict mais une **seconde lecture**, table de substitution
désactivée, plus un niveau `source_spelling`.

Ce remède n'a jamais atteint PAGE, sur une raison écrite au plan et jamais
revérifiée : *PAGE ne substitue rien à la lecture (NFC + strip)*.

**NFC est une substitution.** Un fichier portant `e` + `U+0301` produit une
décision portant `U+00E9` — un codepoint là où le fichier en a deux. Mesuré
avant correctif, sur la fixture PAGE normalisée en NFD : le run annonçait
`{'exact': 32}` alors que **9 de ces 32 lignes** étaient orthographiées
autrement dans le fichier. Après : `{'exact': 23, 'source_spelling': 9}`,
et le fichier composé reste à `{'exact': 32}` — pas un faux positif.

Et il y avait un test pour le protéger. Il affirmait que PAGE ne substitue
rien, sa docstring nommait la faiblesse d'affirmer un dictionnaire vide, et
elle vérifiait donc la revendication elle-même — **sur une fixture
composée, où NFC ne fait rien.** La garde contre l'assertion faible était
faible sur le même axe.

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

## Le harnais ne pouvait pas lire PAGE

Découvert le 2026-08-16 en essayant d'étendre une propriété au second
format : `tests/_pipeline_harness.py` importait le parseur **ALTO**
directement, au lieu du loader générique. Or `formats/loader.py` documente
ce cas exact dans son propre docstring :

> l'ALTO parser appliqué à un fichier PAGE valide ne trouve aucune page
> ALTO et rend un manifeste VIDE (0 page, 0 ligne) au lieu d'une erreur —
> une mauvaise lecture silencieuse, pas un refus.

Un run PAGE via le harnais rendait donc `0 page, 0 ligne` sur un fichier
qui en porte 32, et **toute propriété qu'on y aurait affirmée serait passée
au vert sur un run vide.**

Ça éclaire le motif « PAGE est sous-gardé » autrement que par la
négligence : l'outil principal ne pouvait pas exercer ce format, et il
échouait en silence plutôt que bruyamment. L'avertissement existait,
écrit dans le module même qui existe pour empêcher ça.

Le harnais refuse désormais un manifeste sans lignes, quelle qu'en soit la
cause — mauvais parseur, fixture vide, chemin résolu ailleurs.

**Et le défaut a été fermé à sa source**, parce qu'il ne se limitait pas au
harnais : **63 modules de tests importent le parseur ALTO directement**,
six seulement passent par le loader. Le parseur ALTO refuse désormais un
document qui n'est pas de l'ALTO, au lieu d'en rendre un manifeste vide —
ce qui corrige les 63 sites d'un coup, sans en éditer un seul.

Le plus parlant : **un test épinglait la mauvaise lecture comme
comportement attendu**, avec un commentaire disant « the silent mis-read,
still true ». Le danger était connu, documenté, testé — et traité comme un
fait de la vie qu'on contourne, plutôt que comme un défaut qu'on retire. Ce
test affirme maintenant le refus.

## Ce qui a été fermé depuis le relevé

Quatre entrées « aucune » sur neuf, le 2026-08-16 même, parce qu'elles ne
demandaient aucun arbitrage : les gardes existaient déjà dans le code et
rien ne les atteignait. `E3b`, `E3e` et `E4c` étaient des branches mortes
côté tests. `E2b` était pire — un test portait le nom de la propriété et ne
la testait pas.

Restent cinq « aucune », dont les deux trous d'implémentation ci-dessus et
trois qui demandent une décision : figer l'union `EditOp` (`I2b`), faire
converger les deux voies d'édition sur un même verdict (`E6b`), et comparer
les rôles de césure entre formats (`§6.3`).

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
