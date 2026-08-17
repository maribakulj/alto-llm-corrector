# Où sont vraiment les seuils — mesure du 2026-08-17

Ce document répond à une question posée pendant la session : *comment régler
les seuils d'acceptation, et faut-il aller chercher des ALTO très dégradés
pour ça ?* Il ne porte aucun plan. Ce qu'il faut en faire est une décision.

La réponse mesurée est que **le seuil que tout le monde réglerait n'est
presque jamais celui qui décide**.

## 1. Le signal de qualité existe, et rien ne s'en sert pour décider

Chaque `LineManifest` porte `ocr_confidence`, la moyenne des `String/@WC` de
la ligne, parsée depuis la source. Ses lecteurs, dans tout `src/` :
`core/confidence.py` (qui *rapporte* une confiance) et `core/report.py`.
**Jamais `core/guards.py`.** Donc `min_source_similarity = 0.35` s'applique
identiquement à une ligne que l'OCR note 0,99 et à une ligne qu'il note 0,20.

Aucun `CC` (confiance par caractère) dans aucun corpus : seul le niveau mot
est disponible.

Distribution mesurée sur les six corpora locaux :

| fichier | lignes | médiane WC | forme |
|---|---|---|---|
| `X0000002.xml` | 566 | **0,58** (min 0,00) | dégradé partout — 253 mots sous 0,3 |
| `bpt6k2324031_p0002` | 1145 | 0,99 (min 0,01) | excellent, avec une plaque : 94 mots à 0,00 |
| `bnf-alto-prod-…-f40` | 27 | 1,00 | propre |
| `sample.xml` | 10 | 0,92 | propre |
| `bpt6k2206225_p0015` | 31 | 0,99 | propre |
| `bpt6k6478860m_p0009` | 43 | 1,00 | propre |

**Il n'y a donc rien à télécharger pour commencer.** Les deux formes de
dégradation qui se règlent différemment — uniforme et localisée — sont déjà
là. Un corpus externe reste nécessaire pour *calibrer* (il faut une vérité
terrain), pas pour établir la forme du problème.

## 2. Le seuil de similarité est presque inerte

Balayage de la violence du producteur sur `X0000002.xml` plus les trois pages
Gallica épinglées — 1781 lignes. Chaque niveau ajoute une classe d'erreur OCR
plausible, les derniers ne sont plausibles que pour trouver le point de
fonctionnement du seuil :

| producteur | refus par **garde** | repli de **couple** | médiane de similarité | min |
|---|---|---|---|---|
| 1 règle `s→f` | **0** | 407 | 0,943 | 0,667 |
| 2 règles `+e→c` | **0** | 669 | 0,827 | 0,500 |
| 4 règles `+a→o,n→u` | **0** | 721 | 0,706 | 0,417 |
| 7 règles | **32** | 731 | 0,543 | 0,140 |
| voyelles → `x` | **0** | 730 | 0,674 | 0,400 |

`min_source_similarity = 0.35` mord **32 fois sur 1781**, et seulement sous un
producteur qui réécrit sept classes de lettres à la fois. À quatre règles, avec
une médiane de similarité de 0,71, il ne mord **pas une seule fois**.

Une mesure antérieure de cette même question était confondue et vaut d'être
notée : elle comptait tous les refus ensemble, voyait le taux de refus monter
avec la confiance déclarée, et concluait à une corrélation. Les 688 refus
étaient **tous** des `hyphen_pair_fallback` — elle mesurait la réconciliation
des couples et l'appelait acceptation. Une mesure vaut la méthode qui l'a
produite.

## 3. Ce qui décide réellement : la réconciliation des couples

Sur les mêmes 1781 lignes, sous le producteur le plus **doux** (`s→f` seul) :

| les deux moitiés du couple | verdict |
|---|---|
| aucune ne change | **gardé**, 5 sur 5 |
| au moins une change | **refusé 406 fois sur 703 — 58 %** |

Et le contrôle qui rend ça lisible : un producteur qui ne correspond à rien
refuse **zéro** couple. Le mécanisme n'invente pas de refus ; il refuse quand
le texte change.

Le déclencheur est que la correction touche le **mot de la couture** — le
dernier mot de la tête ou le premier mot de la queue — et contredise donc le
`SUBS_CONTENT` que le fichier déclare. Une correction qui change la ligne
ailleurs laisse le couple intact : c'est la différence entre les 360 refusés et
les 221 gardés parmi les couples dont les deux moitiés ont changé.

**L'ampleur.** 705 des 1781 lignes — **40 %** — sont dans un couple explicite.
Dans l'imprimé historique français, la césure est dense. Donc sous un
producteur doux, environ un quart de toutes les lignes perd sa correction pour
cette seule raison.

## 4. Le comportement est défendable, et son coût n'a jamais été publié

Refuser est cohérent avec la règle fondatrice — en cas d'ambiguïté, revenir au
texte source plutôt que deviner. Le fichier déclare que le mot coupé est
`fondamentaux` ; la correction dit autre chose ; les deux ne peuvent pas être
vrais. Le repli est le choix conservateur.

Mais **rien dans le contrat, le README ou les promesses ne dit que corriger un
mot coupé coûte la correction de ses deux lignes**, et c'est le premier chiffre
qu'un consommateur voudrait connaître. C'est aussi le vrai levier de réglage :
pas le seuil de similarité, mais ce que le réconciliateur fait d'un couple
corrigé qui diverge de sa jointure déclarée.

## 5. L'option qui n'est pas prise, et ce qui la rendrait sûre

Au lieu de jeter la correction, le réconciliateur pourrait **réécrire
`SUBS_CONTENT` avec la nouvelle jointure**. La bibliothèque écrit déjà cet
attribut — 70 occurrences livrées dans `X0000002.xml` — donc la capacité
existe ; la question est quand l'utiliser.

Ce qui la rendrait sûre a été établi le même jour, par accident :
`tests/hyphenation/test_the_joined_word_agrees_with_the_pair.py` a mesuré
l'invariant exact — le mot joint est le dernier mot de la tête, marque de
coupure retirée, suivi du premier mot de la queue — sur **413 couples réels,
zéro divergence**. C'est précisément la précondition dont on a besoin pour
recalculer une jointure au lieu d'abandonner la correction.

Trois réserves, qui sont la raison pour laquelle ce document ne propose rien :

- ça change les octets livrés, donc c'est un changement de contrat ;
- `RM-01` a exempté `SUBS_CONTENT` du writer unique de décision **exprès**, et
  la raison est écrite sur place ;
- et rien ne dit qu'une jointure recalculée est *meilleure* que la déclarée.
  Le savoir demande une vérité terrain, c'est-à-dire le banc (`cinoc`), pas ce
  dépôt.

## Ce qui suivrait, si on le décidait

1. Rendre le seuil fonction de `ocr_confidence` plutôt qu'une constante : sur
   une ligne notée 0,2 une grosse correction est attendue, sur une ligne notée
   0,99 la même est suspecte. Aujourd'hui les deux passent la même porte.
2. Publier le coût de la césure — un compteur existe déjà côté repli, il
   manque de le dire dans le contrat.
3. Mesurer au banc si une jointure recalculée bat la déclarée, avant d'y
   toucher.

Le premier point est une extension de surface publique (une politique
injectée). Le troisième demande une campagne, donc `M2`/`M3`. Aucun des trois
n'est un geste que ce dépôt peut décider seul.
