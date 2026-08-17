# Saknussemm — Audit 2026-08-17 : huit axes, mesurés

**Ce document est un relevé de constats, pas un plan.** Le tri et l'ordre de traitement vivent dans
`docs/PLAN.md`, seul plan du dépôt. Les constats sont ici pour être vérifiables, pas pour être suivis.

## Comment il a été produit, et pourquoi

Le 2026-08-16, une revue externe (`AUDIT-2026-08-16-revue-externe.md`) a soutenu que le risque
dominant du dépôt n'était plus la couverture mais la **boucle auto-validante** : la même boucle
comprend la spécification, modifie le code, écrit le test, rédige la documentation du test, puis
audite la cohérence de l'ensemble. Si l'hypothèse de départ est fausse, tout concorde quand même.

Cet audit est la réponse. Huit axes disjoints, conduits en parallèle, chacun avec deux consignes :
**vérifier empiriquement plutôt que relayer**, et **marquer chaque constat CONFIRMÉ (exécuté) ou
HYPOTHÈSE (lu)**. La suite complète tourne en 78 s, ce qui a permis de la lancer **entière sous chaque
mutation** — c'est ce qui rend les constats de l'axe 4 falsifiables.

Axes : configuration et API publique · provenance et reproductibilité · chaîne
source→manifeste→artefact · épistémologie des tests · modèle d'état · trous d'implémentation des
invariants · complexité et concurrence · chaîne d'approvisionnement.

Trois audits ont dû être relancés (limite de session, coupure réseau). Deux agents signalent que le
dépôt a bougé sous eux — mes propres commits, et les mutants d'un autre agent — et ont rejoué leurs
mesures décisives contre une copie pristine de `HEAD`. C'est la bonne réaction et elle est notée ici
parce qu'elle conditionne la confiance dans leurs chiffres.

---

# I. Un fichier livré peut être faux, en silence

C'est la seule famille qui compte vraiment : tout le reste échoue bruyamment, perd des données de
façon repérable, ou ne coûte que du temps. Six chemins, tous CONFIRMÉS par exécution.

## I.1 — Le manifeste écrit l'artefact ; le registre de décisions ne fait que l'auditer

`core/protocols.py:404-414` — la signature du seam public d'écriture ne connaît pas le `DecisionSet`.
`formats/alto/rewriter.py:962`, `formats/page/rewriter.py:388` lisent `lm.corrected_text`.
`core/rendering.py:154-160` compare **ensuite** le résultat aux décisions.

Le `DecisionSet` n'est donc pas l'autorité terminale : c'est un auditeur. Et `_verify_projection` est
la preuve permanente que deux vérités racontent la même histoire — elle tourne à chaque run, sur
chaque ligne.

## I.2 — Un appelant peut contourner tous les gardes en pré-remplissant un champ public

`core/acceptance.py:131` : `if lm.corrected_text is not None: continue`. Le champ fait double emploi —
le texte de la décision **et** le drapeau « le réconciliateur a déjà traité cette ligne ».
`LineManifest` est public et inscriptible, et `run()` prend le manifeste en entrée.

Mesuré : un manifeste pré-tamponné `corrected_text = "TOTALEMENT INVENTE PAR L APPELANT"` +
`status = CORRECTED` produit un ALTO qui porte cette chaîne, un rapport qui dit `corrected`, et
**trois gardes sautés** — orphelin de césure, atomicité de partenaire tombé, `check_line`. Le texte du
producteur est jeté. L'invariant de projection ne voit rien : les deux vérités mentent de concert.

## I.3 — Deux sentinelles rivales pour « cette ligne est décidée »

`core/acceptance.py:131` lit `corrected_text is not None` ; `core/outcome.py:218-220` lit
`status is PENDING`. Un manifeste où un seul des deux est rempli reçoit deux réponses opposées.

- Cas A (`corrected_text` seul) : le run **plante** — `RuntimeError: … no terminal decision (PENDING)`.
  Et `core/decisions.py:12-15` affirme qu'une ligne PENDING ici « est un bug moteur — jamais un
  problème d'entrée ». Le message accuse le moteur d'un problème d'entrée.
- Cas B (`status` seul, avec une `ValidationError` absorbée) : **la famille `L9` reproduite à
  l'identique**. Mesuré : `status=CORRECTED`, texte final = le texte source, proposition du producteur
  différente, `fallback_reason=None`, ligne comptée nulle part.

`derive_decision_set` ne vérifie que PENDING, jamais la cohérence du couple : il blanchit
l'incohérence en décision terminale.

## I.4 — Le chemin rapide du réécriveur ALTO apparie par position, et le rapport dit `exact`

`formats/alto/rewriter.py:507-517` promet que tous les autres attributs restent intacts ; `:603`
promet que « l'identité suit le mot, jamais ce qui était à la même position ». **Tenu par le chemin
lent seulement** : le rapide teste `len(words) != len(orig_strings)` puis fait un `zip`.

Mesuré avec une règle de scission `"au jourd" → "aujourd "` : `CONTENT="aujourd"` dans la boîte de
`au`, `STYLEREFS` déplacés, `losses` vide, `fidelity = EXACT`. **Le contrôle de fidélité est aveugle à
la mise en correspondance mot↔boîte.** Un consommateur qui recadre les images depuis cette géométrie —
le producteur vision de §5.2 bis — lit la mauvaise portion de l'image.

Correctif : exiger que chaque mot corrigé partage au moins un caractère avec le `CONTENT` d'origine à
la même position, sinon retomber sur le chemin lent, qui aligne déjà correctement. **Aucune correction
n'est refusée, seulement re-routée.**

## I.5 — Contamination croisée entre deux fichiers d'un même document

`core/rendering.py:70-93`, `formats/alto/rewriter.py:938-947`. Le réécriveur indexe par `line_id` nu,
alors qu'`ADR-007` dit que ces identifiants ne sont uniques **que par fichier**.

Mesuré : document à deux fichiers, `page_id` distincts (le garde d'unicité est satisfait), `line_id`
identiques, liaisons nom→chemin interverties. Le run **réussit**. L'artefact livré sous le nom du
premier porte **l'arbre, la géométrie et les `page_id` du second**, avec **le texte décidé pour le
premier**. Le texte propre du second est détruit.

L'invariant de projection ne peut structurellement pas le voir : il compare la sortie aux décisions,
or la sortie a été fabriquée en écrivant ces décisions.

## I.6 — Le mot-frontière d'une paire de césure peut disparaître, des deux côtés

`core/editing.py:299-302`. La docstring affirme que le mot-frontière est « garanti par le contrôle de
non-vacuité ». Il ne l'est pas.

- Côté PART2, le garde heuristique de l'étage B rattrape le cas littéral, mais il compare le *premier
  mot* corrigé au *premier mot* source : il suffit que le mot suivant partage deux caractères
  initiaux. Mesuré : `plu-` / `sieurs siecles ont passe`, span `[0,7)→""` → accepté, `<String
  CONTENT="sieurs">` **disparaît du fichier**, la paire se relit `plu-`+`siecles`, rapport `exact`.
- Côté PART1, rien du tout : `_e5_hyphen_ok` ne teste que la présence du tiret final. Mesuré : un span
  qui efface `att` en gardant le tiret produit `<String CONTENT="-">`, un `String` de tiret nu.
  **`_part1_text_migrated` ne borne que la croissance ; il n'existe aucune borne de rétrécissement.**

Déclencheur : `producers/rules.py` avec n'importe quelle règle à `replacement=""` — le cas d'usage le
plus banal du moteur.

## I.7 — Le texte peut migrer d'une ligne à l'autre, avec deux ops non structurelles

`SPECS_LIB_V2.md:229-231` promet qu'une édition structurelle est « garantie par le type, pas par une
validation ». Vrai au sens syntaxique — le discriminateur pydantic refuse un `merge_lines` — et
**faux au sens sémantique**.

Mesuré : un span ajoute `longtemps` à la fin de TL1, un autre l'efface au début de TL2. Le mot a
changé de ligne. Aucun fallback, aucun événement, aucun compteur. Cela contredit `CLAUDE.md:67`
(« Lines never merge: No text migrates between lines ») et `core/guards.py:296-304`.

Pourquoi les gardes ratent : `check_boundary_migration` modélise un mot qui **se complète** à travers
la couture (fragment + fragment) — la similarité calculée est 0,69 ≤ 0,8 — et le garde d'absorption ne
déclenche qu'au-delà de `1,2 × len(source)`, seuil qu'un mot ajouté ne franchit jamais sur une ligne
longue.

## I.8 — L'ordre des pages change les octets livrés

`core/pipeline.py:487`. Mesuré sur six pages avec des unités de césure inter-pages : texte final et
statut toujours identiques, mais **sha256 différent** — sur une unité inter-pages dont les deux
moitiés tombent, `SUBS_TYPE`/`SUBS_CONTENT` sont préservés en ordre séquentiel et **supprimés** en
ordre inversé (diff de 22 lignes). `fallback_reason` change sur 2 à 8 lignes.

Le code énonce l'hypothèse lui-même : `core/reconcile.py:238-244` — « It is what a CROSS-PAGE tail
carries: **its page ran earlier** » — et `:331-339`. **La réconciliation inter-pages est écrite pour un
ordre de pages séquentiel**, ce qui interdit structurellement toute concurrence au-dessus de la page.

## I.9 — Le fichier source peut changer entre la décision et l'écriture

`core/pipeline.py:407-453`. Le manifeste est bâti sur V1 ; le rendu rouvre le *chemin* et trouve V2 ;
le condensat est calculé **après** le rendu, donc sur V2.

Mesuré : chaque ligne où V2 diffère est silencieusement ramenée au texte V1, dans le markup de V2 ; les
lignes présentes dans V2 mais inconnues du manifeste sont laissées intactes → artefact chimère. Le
même `EditScript` porte le condensat de V2 et des préconditions calculées sur V1 : **rejoué contre le
fichier qu'il désigne, il échoue sur ses propres préconditions.** `core/provenance.py:45-55` promet
pourtant l'accord « by construction, not by coincidence ».

Le même défaut existe dans la chaîne vision : `integrations/vision.py:140` hache les octets,
`:241` rouvre `asset.uri` sans vérifier. Mesuré : condensat gravé `e8b4…`, fichier réellement
ouvert `ec62…`, crops différents.

---

# II. Des promesses écrites que le code ne tient pas

## II.1 — Les deux gardes les plus mises en avant ne s'appliquent pas au producteur par défaut

`core/editing.py:329` le dit en clair :
`# --- replace_line: whole-line path (E1/E3/conflict only; NO E4/E5) ---`.

Donc **E4 (budget de dérive) et E5 (césure) ne concernent que les producteurs à spans.** Le producteur
LLM par défaut (§5.2) n'est jamais soumis au budget de caractères modifiés. Le filet aval
(`min_source_similarity=0.35`) est d'un ordre de grandeur plus lâche que
`edit_line_max_changed_chars=200`.

Mesuré : même texte final visé, span refusé / `replace_line` accepté ; et une variante où les verdicts
**rapportés** sont opposés (`CORRECTED reason=None` contre `FALLBACK reason=absorbs_next_line`).

## II.2 — « Rejouer le script rendu reproduit le fichier » est faux, et était marqué fermé

`core/report.py:48-57` promet que le script ne porte jamais d'op pour une ligne revenue à l'OCR.
`docs/promises.md` l'a marquée **fermée le 2026-08-16**.

Mesuré : livré `'Le peuple att-'`, script publié = l'op refusée, rejeu consommateur =
`'Le peuple att'`. Deux causes composées : `core/attempt.py:119-127` jette `span_result.rejected` ; et
E5 n'est **pas rejouable**, l'`EditScript` ne transportant pas les rôles de césure (§287-294 l'assume).

Le test reste vert parce qu'il pilote un `DictProvider`, producteur `replace_line` pur : le chemin
« op de span rejetée » n'est jamais emprunté. C'est le mécanisme exact que la revue externe décrivait,
sur une promesse fermée le jour même.

## II.3 — Un rejet de garde est totalement invisible

`EditRejection` et ses treize codes de raison n'ont **aucun consommateur hors des tests**. Une ligne
dont l'unique op est refusée ressort `status=CORRECTED`, `reason=None`, `fallback_chunks=0`. Le rapport
ne distingue pas « le producteur n'a rien proposé » de « il a proposé quelque chose que les gardes ont
refusé ».

Conséquence : **le taux de refus des gardes est structurellement non mesurable.** Un consommateur qui
règle son `GuardConfig` — et le banc `cinoc` — pilote à l'aveugle.

## II.4 — La provenance ne distingue pas deux runs qui ne font pas la même chose

`config_fingerprint()` (`core/pipeline.py:277-305`) couvre cinq objets. Ni la `RoutingPolicy`, ni le
scorer QE, ni les `ModelCapabilities` n'y entrent.

Mesuré, routage désactivé puis activé sur le même document : **empreintes égales, `RunProvenance`
identique bit à bit, octets corrigés différents**, `lines_skipped` 0 contre 4.
`RoutingPolicy.policy_fingerprint()` existe et n'est **jamais appelé** par la bibliothèque.
Idem pour `max_images` : cap 2 contre 8 → même empreinte, un appel contre trois.

Cinq autres angles morts de la même famille : le tampon XML nomme le producteur **primaire** même
quand l'escalade a écrit la totalité des lignes (mesuré : 24 lignes escaladées, un seul appel, celui du
VLM, et le fichier dit l'autre) ; l'empreinte du prompt n'entre pas dans le XML ; la `PairingPolicy`
gravée n'est pas celle qui a apparié et rien ne le vérifie ; `source_encodings` — une décision qui
change le texte — n'atteint aucun livrable ; les compteurs qui prouveraient ce qui s'est passé
(`retry_count`, `lines_skipped`, `producer_calls`) ne sont pas dans le rapport persisté, donc **on ne
peut pas savoir si une température ≠ 0 a servi**.

## II.5 — La « signature auditable » d'une ligne non envoyée n'existe pas

`core/routing.py:61-70` promet qu'une ligne SKIP « never reaches a producer, so its trace's
`model_input_text` stays `None` ». Mais la ligne reste dans `chunk.line_ids` (par conception, comme
contexte) et `core/attempt.py:156-166` pose le champ pour **toutes** les lignes du chunk.

Mesuré : `TL1 skip?=True model_input_text='HISTOIRE DE LA RÉVOLUTIOM'`. Trois conséquences : la
signature annoncée est fausse ; **le texte de la ligne « non envoyée » part quand même chez le
fournisseur** — l'argument tient sur le nombre d'appels, pas sur la confidentialité ; et au rapport
elle est indiscernable d'une ligne rendue à l'identique.

## II.6 — Une configuration mal orthographiée est acceptée, appliquée par défaut, puis certifiée

Les 35 modèles Pydantic de `__all__` ont `extra=None`, donc Pydantic v2 **ignore** le champ inconnu.
Mesuré : `GuardConfig(min_source_similarty=0.20)` et `GuardConfig()` gravent tous deux
`config 15dc07cba9122106` dans le XML ; la version correcte grave autre chose.

Le pire cas n'est pas une politique mais l'`EditScript` : écrire `precondition` au lieu de
`preconditions` **éteint la garde anti-sosie**. Mesuré : l'op s'applique sur une ligne dont le contenu
source est différent, sans une entrée dans `rejected`. Celui-là ne fausse pas une métadonnée, il fausse
le texte livré.

Trois autres de la même famille : un manifeste construit à la main où `hyphen_rôle=` est absorbé
désactive silencieusement l'atomicité, la réconciliation et les gardes de dérive de paire ;
`ImageAsset(sha_256=…)` vide la provenance des images de façon indiscernable du cas légitime ;
`producer_confidence` — champ rempli par un producteur **tiers**, docstring `[0,1]`, aucune borne —
accepte `-2.0` et l'agrégat `min` le propage devant tout le corpus.

## II.7 — Autres promesses non tenues, vérifiées

- **Aucune validation XSD en sortie**, alors que `formats/validation.py:6` dit « On OUTPUT it is a
  **gate** ». Aucun appelant hors tests : la porte ne s'applique qu'aux corpora du dépôt.
- **`SUBS_TYPE="Abbreviation"` détruit et déclaré non-perdable.** `formats/alto/losses.py:54-55` le
  classe `REWRITTEN` au motif que `_apply_subs` réécrit depuis l'état de césure — mais l'énumération
  ALTO a trois valeurs et `Abbreviation` n'en est pas une. Mesuré : attributs disparus, perte non
  comptée. `R*` est violée dans le sens le plus gênant : le compte dit zéro là où le fichier a perdu.
- **`hyphen_subs_content` est une quatrième décision par ligne**, écrite pendant le run, livrée dans le
  XML, absente de `LineDecision` donc de `_verify_projection`. Mesuré : un `SUBS_CONTENT` empoisonné est
  livré pendant que l'invariant note l'artefact `EXACT`. `RM-01` a exempté ce champ de l'écrivain
  unique ; personne n'a mis un invariant à la place.
- **`LineTrace.projected_text` diverge de `final_text`** exactement sur le caractère que la passe P5
  existe pour préserver. Mesuré : `'pratica¬'` contre `'pratica-'`. `tests/test_decisions.py:58`
  assert leur égalité et n'est **vert que par chance de corpus**. `docs/PLAN.md` connaît le bug et le
  classe inerte au motif que le champ n'est lu nulle part — le plan ne sait pas qu'un test assert la
  synchronisation qu'il déclare cassée.
- **La règle permanente de `CLAUDE.md` sur les pointeurs de césure est fausse au HEAD.** Elle dit
  `core/pairing.py` « seul lecteur » ; le compte réel est pairing 10, `reconcile` 6, `units` 4,
  `indexing` 4 — **14 lectures sur 24 hors de `pairing.py`**. Et `core/reconcile.py:72-83` est un
  **troisième encodage** de la résolution de partenaire, de portée différente des deux autres.
- **La docstring de `LineManifest`** (`core/schemas/manifest.py:154-157`) décrit un contrat abrogé
  depuis `ADR-011` slice E, et un test du dépôt assert le contraire. C'est cette invitation qui rend
  I.2 et I.3 atteignables par un appelant de bonne foi.
- **La borne basse `pydantic>=2.0` est fausse** : à cette version exacte, `import saknussemm` lève
  `NameError` sur le namespace protégé `model_`. `docs/versioning.md:139` promet « pydantic 2.x ».
  Un consommateur qui a `pydantic==2.0` épinglé installe un paquet inimportable.

---

# III. La suite de tests détecte moins qu'elle ne le paraît

Seize constats, la plupart CONFIRMÉS par mutation **avec la suite entière** lancée sous chaque
mutation. Voici les cinq qui portent.

## III.1 — La famille `L3`/`L9` est structurellement infalsifiable

`tests/test_status_truthfulness.py:54` calcule `discarded = proposed != source and final == source`
avec `proposed = line.proposal.output_text`. Mutation réaliste dans `core/decisions.py:167-170` — un
constructeur de rapport qui reporte le texte final comme la proposition — et `discarded` devient
structurellement `False`.

**Résultat : 1485 passed. Toute la suite verte.** Le défaut qui a frappé deux fois n'a plus aucun
garde.

## III.2 — Le corpus Gallica externe compare une expression à elle-même

`tests/test_external_corpus.py:76` : `assert doc.total_lines == sum(len(p.lines) for p in doc.pages)`,
et `total_lines` est un `@computed_field` dont le corps **est littéralement cette expression**. Vrai
aussi sur un manifeste vide.

Mutation : le parseur laisse tomber la dernière `TextLine` de chaque `TextBlock` — 1144 lignes → 997.
**Les 18 tests du corpus externe passent.** Le reste de la suite tombe à 142 échecs : le palier
« corpus réel », qui existe pour être l'antidote au « même personne écrit le code et les générateurs »,
ne contribue rien à la détection.

## III.3 — Deux recensements qui ne peuvent pas voir ce qu'ils comptent

- `tests/decision/test_fallback_reason_precedence.py:492` balaye `(SRC / "core").glob("*.py")` —
  **non récursif**. `core/schemas/`, `formats/`, `producers/`, `integrations/` sont invisibles. Un
  troisième écrivain de `fallback_reason` placé dans `core/schemas/report.py` et appelé sur chaque
  ligne : suite verte.
- `tests/test_paths_are_not_counted_in_parents.py:110` ne reconnaît que la forme décorateur du skip.
  Deux évadés vivants sur des fixtures **committées**. Mutation : déplacer `examples/X0000002.xml` →
  un test **SKIPPE** et les quatre tests du garde **PASSENT**. C'est mot pour mot le mode de
  défaillance que ce fichier a été écrit pour empêcher.

## III.4 — Un test qui se désarme quand le garde qu'il surveille tombe

`tests/decision/test_acceptance_translation.py:98` :
`if result.accepted: pytest.skip("this pair is accepted — it says nothing about rejection")`.
Le verdict est conditionné à ce que le garde rejette encore. Mutation qui fait accepter le garde 1 :
les trois paramètres **skippent** au lieu d'échouer.

## III.5 — La deuxième direction du comptage de pertes n'exécute jamais sa comparaison

`tests/test_loss_accounting_is_real.py` existe pour « rejeter les deux directions ; le dépôt n'avait
jamais testé que la première ». Son unique site d'appel est une réécriture **identité**, donc la boucle
`continue` avant la comparaison. Sentinelle posée juste avant : **20/20 verts.**

## Le signal le plus parlant

Sous une mutation comportementale du parseur ALTO, le **seul** test devenu rouge fut
`test_orchestrator_budget.py::test_known_oversized_functions_only_shrink` — un cliquet de **nombre de
lignes**. La suite détecte plus fiablement la taille du code que son sens.

## Et les générateurs de propriétés n'atteignent pas les phénomènes qu'ils annoncent

Mesuré sur 400 tirages : **aucun générateur n'émet d'autre marque de césure que le `-` ASCII** — zéro
`¬`, zéro `⸗` — alors que le corpus du dépôt marque **toutes** ses césures avec `¬` et que le corpus
Fraktur du banc utilise `⸗`. Les dix propriétés qui touchent la césure tournent donc exclusivement sur
des paires explicites au tiret ASCII, et le détecteur heuristique — celui que la doc du parseur appelle
le risqué, et où le défaut `⸗` s'est réellement produit — a **zéro couverture par propriété**.

Le producteur métamorphique ne mord que sur **1,6 % des caractères engendrés** : 65 % des documents
obtiennent zéro correction, et la propriété d'invariance sous partition compare une identité à une
identité dans les deux tiers de ses exemples. `hostile_alto` se tue sur les coordonnées avant
d'atteindre la sémantique qu'il annonce : **1,0 % d'exemples utiles**. Deux tests `st.binary`
n'atteignent jamais la couche ALTO/PAGE et n'assertent rien.

---

# IV. Ce que la revue externe a mal évalué

L'audit lui donne raison sur l'essentiel, et la corrige sur quatre points. Ils sont notés parce
qu'une revue crue sur parole aurait fait travailler dans la mauvaise direction.

- **« Passage à l'échelle : 4,5/10 »** — erreur de catégorie, et le chiffre est faux.
  Mesuré de 100 à 20 000 lignes : exposant temps **1,00 ± 0,02**, exposant mémoire **1,00**. Rien
  n'est quadratique dans la taille du document. La seule quadratique est en (lignes **par page**) ×
  (chunks en échec), et elle ne se déclenche que sur le chemin dégradé.
- **« `LineManifest` est largement mutable, des centaines de sites d'affectation »** — faux.
  `corrected_text` a **trois** écritures dans `src/`, `status` en a **deux**, toutes dans le même
  fichier. Le chiffre de 246 vient d'un commentaire du dépôt lui-même, et ce commentaire est faux.
  La conclusion de la revue reste juste, mais pour une autre raison : il n'y a pas trois
  représentations mais **cinq**, et c'est le manifeste qui écrit le fichier.
- **« L'objet source immuable ferme quatre problèmes »** — il en ferme **deux**.
  Le coût compté de la version qui ferme vraiment (retirer `Path`) est **~527 lignes d'appel sur ~110
  fichiers**. Une contre-proposition à ~1/10ᵉ du coût ferme les quatre, et son premier étage a été
  vérifié en l'injectant dans le moteur : suite complète, aucun échec.
- **« Les lectures disque répétées sont un problème de performance »** — non.
  Six à huit lectures du même fichier, pour **4 % du temps** sur un fichier réel de 1,79 Mio : le
  parsing domine. Ce qui tient, c'est que chaque relecture est une fenêtre de plus pour I.9.
- **`corrected_files: dict[str, bytes]`** ne représente que **9 %** du pic mémoire ; la copie profonde
  du manifeste **4 % du temps** mais 17 à 21 % du pic. Le grief mémoire est recevable, le grief temps
  non.

Et un point où la revue avait raison contre mon premier réflexe : le passage de `formats/loader.py`
qu'elle jugeait périmé l'était bien. J'avais commencé par la croire mal informée.

---

# V. Ce qui coûte du temps, mesuré

- **Le comparateur de similarité est reconstruit à neuf à chaque appel** (`core/guards.py:95-101`) :
  environ six fois par couture entre lignes, jusqu'à cinq fois par ligne. **43 % du temps** d'un run
  profilé sur le corpus Gallica. Le correctif — réutiliser l'objet, court-circuiter sur la différence
  de longueur — ne change aucun comportement. Détail à corriger au passage : l'ordre des arguments est
  **incohérent** entre deux gardes, ce qui rend l'heuristique interne asymétrique.
- **La seule vraie quadratique** : `units_containing` (`core/units.py:179-192`) redérive les groupes de
  **toute la page** à chaque chunk qui tombe. Mesuré sur une page de 5 000 lignes avec 50 % d'échecs :
  **52 % du run**, et l'exposant passe de 1,04 à 1,77 quand n croît. À 20 000 lignes le run ne termine
  pas en 3 min 29 contre 33 s sans échec. Ironie : `core/reconcile.py:136` documente avoir **déjà**
  corrigé ce motif exact un niveau plus bas — « le parcours par ligne était quadratique dans la densité
  de césures d'une page ».
- **`align_tokens` est payé jusqu'à trois fois par ligne** et sa complexité réelle porte un facteur
  `c²` que sa docstring omet. `source_for_target` (`core/alignment.py:91-97`) est un balayage linéaire
  appelé une fois par token : correctif de cinq lignes.
- **Les temporisations de reprise s'additionnent** : mesuré, une page de 29 lignes et six appels vers
  un producteur local sans entrée/sortie prend **6,04 s de temps réel**, presque entièrement en
  attente.

## L'enveloppe mesurée, qui est ce qu'il faut publier

Aucune de ces lignes n'existe aujourd'hui dans `README.md`, `SPECS_LIB_V2.md` ni `docs/promises.md`.

| grandeur | valeur mesurée |
|---|---|
| empreinte de travail | **≈ 10× la taille du XML source** (×8,3 sur le corpus réel) |
| par ligne | **≈ 11 ko de pic**, **≈ 1,65 ms de CPU** hors réseau |
| document de 20 000 lignes (20,2 Mo) | parse 0,65 s, run 33,4 s, pic 213 Mo |
| corpus Gallica épinglé, 1 215 lignes | 0,394 s, soit 0,32 ms/ligne |
| extrapolation 100 000 lignes | ≈ 1,1 Go et ≈ 165 s de CPU |

Le paramètre d'échelle est le nombre de lignes **par page**, pas le nombre de lignes du document :
au-delà de quelques milliers de lignes sur une seule page, le chemin de fallback devient quadratique.
Les pages OCR réelles font 30 à 1 200 lignes, donc le cas dégradé n'est pas le cas courant — mais il
n'est pas non plus documenté.

---

# VI. La concurrence est possible, à un endroit précis, et c'est mesuré

- **L'ordre des chunks à l'intérieur d'une page n'influence rien.** 39 comparaisons — sha256 des XML,
  chaque décision, tous les compteurs, le script d'édition **en ordre** — sur le corpus Gallica et un
  document synthétique à unités inter-pages, jusqu'à 94 chunks et 277 appels : **différences nulles
  partout**.
- **Un prototype de concurrence bornée intra-page produit une sortie octet pour octet identique** dans
  les dix configurations essayées, pour un gain de **×12 à ×15** à 50 ms de latence par appel.
  L'endroit est `core/driver.py:122-139`, chunks de premier niveau seulement — la descente doit rester
  séquentielle **parce que ses sous-chunks partagent une seule bourse** (`core/driver.py:287`).
- Un seul détail à corriger avant d'activer quoi que ce soit : `report.hyphen_splits` est accumulé dans
  l'ordre d'exécution. Même ensemble, ordre différent après réordonnancement. À trier.
- **Mais le gain dépend de la taille des pages.** Les pages du corpus épinglé font 29, 42 et 1 144
  lignes ; au grain par défaut une page de 29 lignes est **un seul chunk**, donc gain nul. Tout le ×12
  vient de la grande page. Pour un corpus de pages ordinaires, le parallélisme utile est au niveau
  **page** — interdit par I.8 — ou **document**, c'est-à-dire chez l'appelant.
- **Le moteur est réellement réentrant** (deux runs concurrents, décisions et octets identiques aux
  runs séquentiels), mais la promesse est **fausse de la composition** : rien dans le protocole
  `EditProducer` n'interdit un état par run. Mesuré avec un producteur portant un budget : budget final
  −2, deux refus qui n'auraient pas dû arriver, **41 courses sur 42 appels, et les deux runs se
  terminent « avec succès »**. Et les 106 événements de deux runs concurrents ne portent **aucune** clé
  qui nomme un run, tandis que les `page_id` collisionnent entre documents.

---

# VII. Ce qui est confirmé bon

Il faut le dire, parce qu'un relevé de défauts sans cette section se lit comme un verdict global.

- **Reproductibilité de la construction : parfaite.** Trois constructions, deux outils différents,
  mêmes sha256 ; la roue reconstruite depuis le sdist extrait donne le même condensat. Contenu conforme
  à la déclaration : aucun test, aucun corpus, aucune image.
- **Aucun secret nulle part**, et `grep secrets\. .github/workflows/*.yml` ne retourne **rien** : tout
  passe par OIDC. Déclencheurs sains, aucun `pull_request_target`.
- **Déterminisme** : aucune horloge, aucune variable d'environnement, aucun réseau dans `src/`.
  Quatre runs sous `PYTHONHASHSEED` différents donnent des artefacts identiques.
- **`src/` est portable** : zéro `os.path`, `os.sep`, `tempfile`, `locale`, `subprocess`, chemin absolu.
  Le risque plateforme est dans `tests/` et les workflows, pas dans la bibliothèque.
- **Les politiques sont correctement bornées** (`gt`/`ge`/`le`) avec trois validateurs croisés réels ;
  les champs typés `Enum`/`Literal` rejettent correctement. Le problème de II.6 est l'inconstance, pas
  l'absence d'outil.
- **La surface publique est calculée et non accumulée**, épinglée, **sans symbole orphelin** : les 66
  sont utilisés par au moins un test.
- **Une seule copie profonde dans tout le code**, hors boucle. Aucune recherche linéaire sur des
  données de document. Aucune recherche XML par ligne. Aucune récursion dont la profondeur croît avec
  le document. Aucun cache désynchronisable.
- **La doctrine « un nombre dérivable d'un autre finira par le contredire » est déjà énoncée trois
  fois** dans le dépôt. Elle n'a simplement jamais été appliquée au champ le plus important : le texte
  décidé lui-même.
- `tests/external_corpus/fetch.py` est qualifié d'exemplaire par l'auditeur qui cherchait des défauts.

---

# VIII. Le motif, en trois phrases

Les invariants sont écrits pour un producteur qui rend des **lignes entières**, et contrôlés par des
prédicats **positionnels** — premier mot contre premier mot, i-ème `String` contre i-ème mot. Le
protocole d'édition par spans permet de **déplacer une frontière** sans changer ni le compte ni la
position : c'est l'angle mort commun de tous ces prédicats, et c'est pourquoi les défauts de la
section I se ressemblent tous.

Quand ces gardes refusent, ils refusent **en silence** : aucun `EditRejection` n'est consommé nulle
part. Le trou est donc invisible dans le rapport comme dans le banc.

Et le modèle d'état l'aggrave : parce que le manifeste mutable écrit l'artefact et que le registre de
décisions ne fait que l'auditer, il faut **18 % des lignes de la suite de tests** pour prouver en
permanence que les deux racontent la même histoire — un scanner de code, un test du scanner, et un
test attestant que le test qui atteste tient encore.
