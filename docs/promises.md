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
| I2b | une édition structurelle est **inexprimable** dans le protocole | **fermée le 2026-08-19** — `test_the_edit_union_does_not_grow_by_accident.py`. Le test ne décide **pas** que l'union ne grandira jamais : il décide qu'elle ne grandira pas *par accident*, comme `test_public_api_snapshot` pour la surface. Une liste figée, plus trois propriétés — toute op nomme **une** ligne, porte un texte de remplacement (donc propose une lecture au lieu d'ordonner une opération), et a son propre discriminant. Deux corrections apportées par la mesure : la règle « aucun champ pluriel » gardait une orthographe et laissait passer `with_line_id` ; et paramétrer les propriétés sur la liste figée plutôt que sur l'union réelle faisait qu'un nouveau membre ne rencontrait jamais les propriétés censées le juger — alors que la liste figée est la première assertion qu'un auteur pressé modifie. Un `MergeLines` fait désormais tomber **trois** assertions, dont deux par propriété |
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
| E4a | borne de dérive **par op** | **fermée le 2026-08-19** — `test_the_growth_bound_is_per_op.py`. Le contrôle négatif manquait (une suite qui n'asserte que des refus reste verte contre une garde qui refuse tout), et le « par op » aussi. **Le test à deux ops évident ne le prouve pas non plus** : si chaque op respecte `len_i ≤ r × span_i`, leur somme aussi, donc une borne cumulative accepte exactement les mêmes scripts — écrit ainsi d'abord, et la mutation cumulative l'a laissé vert. Le cas discriminant va dans l'autre sens : une op qui rétrécit un long span, une op qui crève le ratio sur un court ; cumulée, la marge de la première paie la seconde. Trois mutations attrapées (borne cumulative, dénominateur nul sur une insertion, refus qui emporte tout le script) |
| E4b | budget de caractères modifiés, élagage préfixe/suffixe | **gardée** — le mieux tenu du lot |
| E4c | le budget est **par ligne**, cumulé sur plusieurs ops | **fermée le 2026-08-16** — deux ops de 8 caractères, refusées sous un budget de 12, acceptées sous 20 : c'est le cumul qui décide |
| E5a | une ligne de césure garde son tiret final | **fermée le 2026-08-16** — `test_e5_covers_every_break_mark_and_both_roles.py` balaie les six marques du répertoire × les deux rôles ouvrants, dans les deux sens (sectionner est refusé, préserver passe) plus un contrôle sur `NONE`. La marque que la suite exerçait, `-`, est la seule que le corpus n'emploie pas : les fixtures appariées marquent tout avec `¬` |
| E5b | son **mot-frontière** ne peut pas être supprimé | **fermée le 2026-08-19, arbitrage tranché sur mesure** — la règle retenue est « un span ne peut pas effacer, sans remplacement, la plage couvrant le premier mot ». Pourquoi *effacer* et non *changer* : sur **1 433 lignes PART2/BOTH d'un vrai run** `mistral-small-latest`, le mot-frontière est laissé tel quel 63 %, corrigé 12 %, et **remplacé par du méconnaissable 25 %** — parce que c'est l'endroit le plus dégradé de la ligne, souvent réduit à un caractère isolé (`'•'` → `'seil'`, `';'` → `'dré'`, `'j'` → `'parole'`, toutes justes). Un seuil de similarité refuserait donc **23–31 %** des corrections réelles, et précisément là où elles valent le plus. Refuser le seul effacement en coûte **0**. Le trou lui-même est étroit — il faut paire heuristique **et** mot effacé **et** mot suivant partageant deux caractères initiaux — soit **0 occurrence sur 4 752** lignes réelles, mais reproductible sur une ligne construite, d'où une assurance à coût nul plutôt qu'une note. `test_the_boundary_word_cannot_be_erased.py` |
| E6a | les gardes s'appliquent au texte issu d'un span | **fermée le 2026-08-19** — `test_a_span_output_faces_the_semantic_guards.py`. Un span structurellement irréprochable — ancre en portée, une op par ligne, sans chevauchement, et **plus court** que ce qu'il remplace donc `E4` n'a rien à dire — dont le résultat ne ressemble plus à la ligne d'origine : seul l'étage sémantique peut le voir, et il le refuse (`too_different_from_source`). Avec son contrôle : un span raisonnable atterrit, sans quoi la propriété prouvée serait l'inverse de celle annoncée. Sensibilité mesurée sur deux mutations — `check_line` court-circuité (les deux tombent), `min_source_similarity` à 0 (seul le refus tombe, ce qui attribue le refus au bon seuil) |
| E6b | span et `replace_line` obtiennent le même verdict sur le même résultat | **fermée le 2026-08-19, arbitrage tranché sur mesure** — la voie ligne entière passe désormais par `E4` et `E5`. Coût mesuré avant de décider, sur **1 796 propositions réelles** : `E4` refuse **0** (ligne médiane 20 caractères changés, pire 168, budget 200) ; `E5` refuse **205**, dont **204 étaient déjà refusées** en aval — elle ne refuse pas plus, elle refuse **plus tôt et en nommant pourquoi**, et les cas le méritent (marque disparue, texte de la ligne SUIVANTE, fragment de la PART2). La 205ᵉ a fait **affiner `E5`** : une espace avant la marque n'est refusée que si la correction l'a **introduite**, car sur ces 205 elle est héritée de la source 1 fois et introduite 0 fois — et cette unique ligne est `#126`, une excellente correction que juger sur le seul résultat punirait pour sa fidélité. Rejoué sur les données du run : **204 refusées, 0 verdict changé**. `test_both_edit_paths_face_the_same_drift_guards.py` |
| F2a | liste blanche d'attributs en slow path | **fermée le 2026-08-19** — `test_the_whitelist_is_a_whitelist.py`. Un seul attribut prouve qu'*il* est jeté, pas que la règle est une liste **blanche** : une liste noire nommant ce seul attribut passe le même test, et une liste blanche élargie d'un quatrième nom aussi. Le test asserte donc la **clôture** — après reconstruction, un `String` porte la liste blanche, la géométrie recalculée, son nouveau `CONTENT`, et rien d'autre — contre cinq intrus dont deux inventés (le cas pour lequel le défaut conservateur de `fate_of` existe). Plus que la perte est **comptée**, et que le style atterrit sur le `String` que l'**appariement** a retenu, jamais sur celui qui occupe la même position. Trois mutations attrapées |
| F2b | `WC`/`CC`/`SUBS_*` jamais recyclés | **gardée** |
| — | parité d'octets ALTO quand rien ne change | **fermée le 2026-08-19** — `test_an_identity_run_reserialises_the_source.py`. Un golden sha256 épingle que la sortie ne bouge pas entre deux versions ; il ne dit pas qu'elle EST la source, et un rewriter qui reformaterait tous les fichiers de la même façon le satisferait toujours. Le contrôle par ligne compare des textes, aveugle à l'ordre des attributs, aux espaces inter-éléments, aux balises auto-fermantes. Ce test compare la **sérialisation entière**, à l'unique `postProcessingStep` près — et la première version a échoué la mesure, pas le code : elle retirait la trace de l'ARBRE et re-sérialisait les deux côtés, ce qui normalisait précisément ce que la promesse vise (`pretty_print=True` la laissait verte). Découpée dans les OCTETS, trois mutations sont attrapées |
| — | parité d'octets PAGE | **fermée le 2026-08-17** — `test_byte_parity_page_corpus.py` : quatre golden sha256 (deux fixtures × identité/scripté), et deux assertions qui valent plus que les empreintes. **Un run d'identité ne change aucun élément** — recensement d'éléments identique, les 20 octets de plus étant l'estampille de provenance ; ça survit à un changement justifié d'empreinte, ce qu'une empreinte ne fait pas. Et **chaque `<Word>` supprimé est compté** : `words_dropped` égale exactement le nombre de `<Word>` manquants des octets livrés (47 et 7), vérifié sur **les deux canaux** — la somme par ligne et le total du run. Le second a été ajouté après qu'une mutation ait traversé le premier : le compteur par ligne est *diffé* autour de chaque ligne (ADR-012), donc un décalage constant s'y annule. Quatre mutations mordent |
| §6.3 | texte canonique identique entre formats | **gardée**, sur une page |
| §6.3 | rôles de césure équivalents entre formats | **fermée le 2026-08-16** — `test_hyphen_roles_agree_across_formats.py` compare les deux détections sur les fixtures appariées : 44 lignes partagées, zéro désaccord sur rôle, partenaire, contenu `SUBS` et caractère explicite. Deux mutations se sont révélées inertes : la branche `BOTH` des deux parseurs est redérivée par le linker partagé |
| — | somme des pertes par ligne = agrégat | **fermée le 2026-08-16** — étendue à PAGE, le format où les deux comptes sont calculés indépendamment. Ils s'accordent : vérifié, plus supposé |
| — | le rapport dit du fichier ce qui y est | **fermée le 2026-08-19** — `test_the_reports_counters_match_the_file.py`. Les compteurs sont la moitié qu'un consommateur lit vraiment — un tableau de bord affiche « 1 035 lignes, 412 corrigées, tout exact » et personne ne reparse le XML. Chacun est donc dérivé des **octets livrés**, pas des objets en mémoire qui l'ont produit : un compteur vérifié contre sa propre source s'accorde avec lui-même par construction. Trois mutations, chacune tombant sur **sa** assertion, ce qui dit que les trois vérifient trois choses. Limite énoncée : `fallback_lines` n'est PAS vérifiable ainsi — une ligne corrigée peut atterrir sur un texte identique à sa source, donc l'artefact ne peut pas les distinguer, et l'autorité est le `DecisionSet` (`test_status_truthfulness.py`) |
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

**Les cinq restantes ont été fermées le 2026-08-19** : les deux trous
d'implémentation (`E5b`, `E6a`) ont été comblés, et les trois qui demandaient
une décision ont été tranchées — figer l'union `EditOp` (`I2b`), faire
converger les deux voies d'édition sur un même verdict (`E6b`), et comparer
les rôles de césure entre formats (`§6.3`).

**Décompte au 2026-08-21 : 24 promesses, 10 gardées et 14 fermées, aucune
découverte.** Le paragraphe ci-dessus est resté trois jours à dire « restent
cinq » alors que la table disait le contraire — un fichier d'état qui se
contredit lui-même est pire qu'un fichier absent, parce qu'on le croit. La
table fait foi ; ce texte la commente et doit être relu quand elle change.

## Relevé complémentaire du 2026-08-25 — vague `RS`

Deux entrées de la table changent d'état, et une promesse non écrite s'ajoute.

**« parité d'octets ALTO quand rien ne change » et « le rapport dit du
fichier ce qui y est » étaient gardées sur un ÉCHANTILLON.** Onze des quinze
documents du dépôt ne passaient sous aucune empreinte — dont les deux pages
NewsEye de 2,4 Mo, les trois pages Gallica épinglées et les paires ALTO/PAGE
de Descartes et La Fayette. `tests/test_byte_parity_all_fixtures.py` met les
quinze sous empreinte, sur quatre scénarios dont deux traversent le pipeline
entier, et une assertion refuse qu'un document du dépôt échappe à la liste.

**Et l'échantillon cachait un défaut, ce qui est le motif habituel de ce
document.** La géométrie des tokens ALTO dépendait de la version de Python :
`sum()` de flottants a changé d'algorithme en CPython 3.12, donc les mêmes
poids de tokens donnaient un total différent, et un `<SP>` d'une ligne réelle
sortait un pixel plus large sur 3.11 que sur 3.12. La CI matriçait pourtant
déjà les trois versions — mais aucune empreinte préexistante ne tombait sur
un arrondi à la demi-unité, donc rien ne pouvait le voir.

**Une promesse s'ajoute, qui n'était écrite nulle part : le vocabulaire des
raisons de repli est clos.** Un consommateur agrège sur ces codes ; il y en
avait vingt, dispersés en littéraux sur huit modules, et rien ne disait
combien. `core.decide.FALLBACK_REASON_CODES` les porte,
`tests/test_the_fallback_reasons_are_a_closed_set.py` les garde dans les deux
sens et vérifie que `docs/la-vie-d-une-ligne.md` les liste tous.

**Ce que la vague n'a PAS fermé, et qui reste au motif dominant ci-dessous :**
les scénarios `probe` et `drift` du nouveau golden exercent PAGE comme ALTO,
ce qui réduit l'écart — mais aucune des six promesses « partielles pour cause
de PAGE » n'est reprise une par une. Le motif tient.

## Relevé complémentaire du 2026-08-27 — l'état `review_required`

**Une promesse s'ajoute, et elle est d'une autre nature que les autres :
elle porte sur ce que la bibliothèque NE promet pas.**

> Un statut `corrected` ne dit pas « cette correction est juste ». Il dit
> « aucune garde n'y a rien trouvé à redire ». Depuis `review_required`,
> les cas où la différence compte sont nommés au lieu d'être fondus dans le
> premier.

Ce qui la garde : `tests/test_review_pass.py`, huit assertions sur un run
réel, dont les deux qui portent tout le reste — la correction est **livrée**
(texte et opération d'`EditScript` intacts), et activer les règles ne change
**aucun octet** du fichier, vérifié en comparant les deux runs plutôt qu'en
l'écrivant ici.

**Le vocabulaire des renvois est clos dès l'écriture**, ce que celui des
replis n'a pas été : `core.decide.REVIEW_REASON_CODES`, six codes, gardés
dans les deux sens par `tests/test_the_review_reasons_are_a_closed_set.py`
— et gardés en **exerçant** les règles plutôt qu'en scannant des littéraux,
donc « ce code est déclaré » y veut dire « une règle l'a rendu sur une
entrée ».

**Ce qui reste explicitement non promis, et c'est le point.** Trois règles du
programme d'origine n'existent pas, chacune parce que le moteur n'a pas de
quoi l'alimenter : la ligne propre modifiée (mesurée, puis retirée — sans
lexique elle renvoyait 30 des 47 lignes modifiées du corpus de vérité
terrain, en attrapant de simples corrections `f` → `ſ`), le désaccord entre
producteur texte et producteur vision (aucun run n'interroge les deux), et
la confiance non calibrée sous seuil. Elles sont écrites dans
`src/saknussemm/core/review.py` et dans `docs/la-vie-d-une-ligne.md` §3 bis
plutôt que déclarées et inertes — un code de renvoi qu'aucun run ne rend est
une promesse qu'aucun consommateur ne collecte.

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
