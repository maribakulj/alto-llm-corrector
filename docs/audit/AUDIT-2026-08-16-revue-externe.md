# Saknussemm — Audit 2026-08-16 : la première revue externe

**Ce document est un relevé de constats, pas un plan.** Il ne renumérote aucune
exigence et n'ajoute aucune feuille de route ; les documents de planification
restent `SPECS_LIB_V2.md` (le contrat) et `docs/PLAN.md` (ce qui reste à faire).

Il consigne une revue conduite le 2026-08-16 par un lecteur **extérieur à la
construction du dépôt**, sur la base du code, des specs et de la CI. C'est la
première du genre, et elle vaut d'être archivée pour une raison précise : le
critère de sortie `V10` exige exactement cela, et jusqu'ici tout — code, specs,
tests, audits et leur interprétation — était produit dans la même boucle.

Chaque constat est reporté avec **le verdict de sa vérification**, faite avant
toute correction. Une revue externe n'est pas plus dispensée de preuve qu'une
revue interne ; deux de ses affirmations étaient inexactes, et un point où je
l'ai d'abord crue mal informée s'est révélé juste.

## Confirmés par la mesure

### 1. Une configuration mal orthographiée est acceptée en silence

`FrozenPolicy` fixe `model_config = ConfigDict(frozen=True)`. Pydantic v2
**ignore les champs inconnus par défaut**. Vérifié :

```python
>>> GuardConfig(min_source_similarty=0.20)   # faute de frappe volontaire
>>> g.min_source_similarity
0.35
```

L'objet est valide, la valeur appliquée est la valeur par défaut, et le
`policy_fingerprint()` de cette configuration part ensuite dans le
`processingStep` du XML corrigé. Le système certifie donc avec soin une
configuration qu'il n'a pas comprise.

C'est le constat le plus lourd de la revue : conséquence silencieuse, correctif
trivial (`extra="forbid"`), et contradiction directe avec l'argument central du
dépôt. Le correctif est un **changement de surface publique** — une
configuration qui passait lèverait désormais une erreur — et attend un
arbitrage.

### 2. Des identifiants aléatoires atteignent le stimulus du modèle

`DocumentManifest.document_id` et `ChunkRequest.chunk_id` sont tous deux des
`uuid4()` par défaut. `ChunkRequest` porte les deux, et
`producers/llm_edit.py:122` envoie `payload.model_dump(exclude_none=True)` au
fournisseur. Deux chargements du même fichier produisent donc deux prompts
différents.

La revue ne relevait que `document_id` ; `chunk_id` a le même défaut.

### 3. `CorrectionResult.write()` peut écraser un fichier

`core/result.py:103` fait `path = target / Path(source_name).name`. La
protection contre la traversée de chemin est correcte, mais `volume1/page.xml`
et `volume2/page.xml` atterrissent tous deux sur `page.xml`. La façade `load()`
refuse déjà les doublons de nom de base ; l'API basse couche ne défend pas son
propre contrat.

### 4. Le job de publication exécute du code non verrouillé sous `id-token: write`

`publish-saknussemm.yml` déclare `id-token: write` (ligne 25) et exécute
`pip install cyclonedx-bom` sans version épinglée (ligne 165) dans le même job.
La roue publiée est déjà immuable, donc il ne s'agit pas d'altérer le paquet,
mais de la surface de confiance du job qui détient le pouvoir de publier.

### 5. `formats/loader.py` avertissait au présent d'un piège à moitié refermé

Corrigé — voir la PR « Deux affirmations que le code a dépassées ». Le refus
existe dans `alto.parser.build_document_manifest` ; `parse_alto_file` rend
toujours zéro page sans erreur.

### 6. `docs/PLAN.md` se contredisait sur la surface publique

Corrigé dans la même PR. Le plan réclamait en tête une coupe de 95 symboles
close depuis le 2026-08-01, que le même document constatait faite quinze pages
plus bas et dans son tableau `V5`. Mesuré : `len(saknussemm.__all__) == 66`.

## Constats non vérifiés, retenus comme hypothèses

Reportés sans mesure de ma part, et donc à traiter comme des pistes :

- **Provenance du routage** — `config_fingerprint()` couvre le planificateur,
  les gardes, les pertes, l'appariement et les reprises, mais pas la
  `RoutingPolicy` ni le scorer QE, qui décident pourtant si une ligne va au
  modèle, à la vision, ou nulle part.
- **`ModelCapabilities.max_images`** modifie le découpage des requêtes vision
  sans entrer dans `prompt_schema_fingerprint()`.
- **TOCTOU vision** — `build_image_asset()` hache les octets, `crop_region()`
  rouvre le chemin plus tard. Le rapport peut déclarer une empreinte pour une
  image que le modèle n'a pas vue.
- **Lectures disque répétées** du même XML le long du chemin de chargement.
- **Réentrance survendue** — l'absence d'état mutable par run sur le pipeline
  est vraie ; la réentrance effective dépend aussi du producteur et de
  l'observateur injectés, et les événements ne portent pas de `run_id`.
- **Concurrence** — le traitement des pages puis des chunks est séquentiel.

## Ce que la revue note à tort

**« Passage à l'échelle corpus : 4,5/10 »** est une erreur de catégorie. La
revue reproche à la bibliothèque de ne pas faire une chose qu'elle refuse
délibérément de faire, puis conclut elle-même que ce refus est le bon choix et
qu'il suffirait de le déclarer. Le défaut réel est documentaire : la
bibliothèque devrait dire explicitement que son unité de traitement est un
document de taille bornée. Ce n'est pas une note d'ingénierie.

**« Le prochain outil nécessaire est du mutation testing »** enfonce en partie
une porte ouverte : la preuve par mutation est déjà la condition d'entrée de
toute nouvelle propriété. La part juste est qu'elle est artisanale et ciblée sur
le neuf ; un outil balayant l'existant chercherait ailleurs.

## Le constat central, et pourquoi il est archivé ici

La revue soutient que le risque dominant du dépôt n'est plus la couverture mais
la **boucle auto-validante** : la même boucle comprend la spécification, modifie
le code, écrit le test, rédige la documentation du test, puis audite la
cohérence de l'ensemble. Si l'hypothèse de départ est fausse, tout concorde
quand même.

Le dépôt en fournit lui-même les preuves : trois tests découverts le
2026-08-16 épinglaient une affirmation fausse comme comportement attendu, dont
un qui faisait tourner des propriétés PAGE sur un manifeste vide.

Deux observations à verser au même dossier, du même jour :

- En construisant `test_hyphen_roles_agree_across_formats.py`, une mutation
  censée prouver que le test mordait est passée verte. La mutation était
  **inerte** — le code visé est redérivé par le linker partagé. La conclusion
  spontanée (« mon test est faible ») aurait été fausse dans les deux sens.
- Dans le même test, les seuils anti-vacuité avaient été calculés sur le total
  de deux corpus puis appliqués à chacun. Rattrapé uniquement parce que ces
  gardes existaient.

La nuance qui mérite d'être conservée : ce qui a débusqué les trois tests
mensongers est `docs/promises.md`, une liste bâtie depuis **ce que le contrat
promet** et jamais depuis ce que les tests couvrent. Changer de point de départ
casse une partie de la boucle. Cela ne la remplace pas par un regard extérieur.
