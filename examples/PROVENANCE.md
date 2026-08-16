# `examples/` — provenance et rôle des fixtures ALTO

Les fixtures PAGE ont leur propre note : `examples/page/PROVENANCE.md`.
Celle-ci couvre les fichiers ALTO à la racine d'`examples/`.

Toutes sont lues par la suite de tests via `tests/_paths.EXAMPLES`. Aucune
ne part dans la wheel ni dans la sdist : `sdist.include` est une allowlist
de quatre entrées ancrées, vérifiée sur les artefacts **construits** par
`tests/test_packaging_excludes_corpora.py`.

## `X0000002.xml`

Presse du 19ᵉ siècle, **BnF / Gallica**, ark `bpt6k3265015q`, feuillet 2.
**Domaine public.** ALTO en namespace standard LoC. 566 lignes, dont 115
portent leur signe de coupure en U+00AD dans le `<HYP>` seul — c'est le
corpus sur lequel `L8` a mesuré la classe `source_spelling`.

## `sample.xml`

Petit ALTO déterministe, 2 pages, construit pour la suite.

## `bnf-alto-prod-bpt6k5406037v-f40.xml`

**BnF / Gallica**, ark `bpt6k5406037v`, feuillet 40, monographie du 19ᵉ.
**Domaine public.** Récupéré le 2026-08-16 via
`RequestDigitalElement?E=ALTO` (le service refuse le User-Agent par défaut
de `curl` : il faut celui du projet).

Cette page est là pour **deux** propriétés qu'aucune autre fixture ne porte,
et elles sont indépendantes :

1. **Un namespace d'éditeur.** La racine est `alto` sous
   `http://bibnum.bnf.fr/ns/alto_prod`, la famille sous laquelle Gallica
   sert une grande partie de son ALTO. Le contenu est de l'ALTO ordinaire —
   `Description`, `Layout`, `Page`, `PrintSpace`, `TextBlock`, `TextLine`,
   `String`, `SP`, `HYP` — avec de la césure **explicite** (`SUBS_TYPE`,
   `SUBS_CONTENT`), c'est-à-dire la meilleure entrée possible pour cette
   bibliothèque. Elle était refusée à la porte.

2. **Une déclaration d'encodage fausse.** Le fichier déclare
   `ISO-8859-1` et contient de l'UTF-8 : 57 caractères non-ASCII, et le
   flux entier décode en UTF-8 strict. Lu comme il se déclare, `cléricales`
   devient `clÃ©ricales` sur 21 de ses 27 lignes.

**Les octets sont ceux de Gallica, non retouchés** — y compris la
déclaration fausse. Une fixture qu'on répare cesse de tester ce pour quoi
on l'a prise.

## `bnf-alto-prod-latin1-control.xml`

**Contrôle négatif, synthétique et assumé comme tel.** C'est le document
ci-dessus, ré-encodé en latin-1 réel : il déclare `ISO-8859-1` et l'est
vraiment, donc son flux **échoue** au décodage UTF-8 strict.

Il existe parce que la règle qui rattrape une déclaration fausse doit
prouver qu'elle sait **ne pas** se déclencher. Un contrôle trouvé plutôt
que fabriqué serait meilleur ; la première tentative en a d'ailleurs
produit un faux — un fichier qui n'était pas de l'UTF-8 mais qui n'était
pas non plus de l'ALTO : une page d'erreur HTML rendue par Gallica avec un
code 500. D'où le choix d'un contrôle dont on connaît exactement la
construction.
