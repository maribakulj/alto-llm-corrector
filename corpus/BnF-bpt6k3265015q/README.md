# BnF `bpt6k3265015q` f2 — page ALTO + scan

Une page appariée `X0000002.xml` (ALTO) + `X0000002.jpg` (scan), déposée pour
valider la chaîne vision sur de la **vraie OCR brute**, contre du matériau
structurellement différent du corpus BNL.

> **Poids.** Le JPEG fait 9,2 Mo et il est dans l'historique git de façon
> **définitive** : `git rm` le retirerait du répertoire de travail, pas des
> objets git. Une purge réelle demanderait `git filter-repo`. Même
> avertissement que `corpus/37-GT-BNL/README.md`, même arbitrage assumé.

## Ce que cette page apporte que le corpus BNL n'a pas

| | 37-GT-BNL | cette page |
|---|---|---|
| ALTO | v4 | **v3, dialecte BnF** (`alto_bnf-v2_0`) |
| `MeasurementUnit` | `mm10` (scale `dpi/254` ≈ 1.1811) | **`pixel`** (scale 1.0) |
| Lignes par page | ~14 | **566** |
| Césure | paires simples | **115 paires, 26 chaînes (`BOTH`), 1 inter-pages** |
| Texte | transcription humaine (référence) | **OCR brute ABBYY** (entrée) |

Le `MeasurementUnit pixel` exerce la branche `transform = 1.0` que le corpus
mm10 ne touche jamais. Les 566 lignes sur une seule page sont ce qui a rendu
visible le plafond d'images par appel (Phase 4).

**Il n'y a PAS de vérité terrain ici.** Le `CONTENT` est de l'OCR ABBYY
(`ACCURACY="87.14"`, `[001_OCR_BRUT]`), pas une transcription vérifiée. On peut
donc mesurer robustesse, coût et latence, et lire les corrections — **jamais un
CER**. Pour du chiffré, c'est `corpus/37-GT-BNL/` qui fait référence.

## Géométrie

- `<Page WIDTH="6436" HEIGHT="9257">`, en pixels.
- Le scan IIIF pleine résolution fait exactement 6436 × 9257 : correspondance
  **1:1**, aucun `ImageTransform` nécessaire.
- La dernière ligne (`TL000566`) est un `PART1` dont le partenaire est sur la
  page suivante (`f3`, absente ici) : cas de **césure inter-pages**, laissé à
  `cross_page_partners` — utile comme cas limite, pas comme régression.

## Provenance et licence — **domaine public** (avec une nuance)

- Source : Gallica / BnF, `ark:/12148/bpt6k3265015q/f2`
  (`sourceImageInformation/fileIdentifier` de l'ALTO), librement téléchargeable
  depuis Gallica.
- ALTO fourni par le mainteneur du dépôt ; scan récupéré via l'API IIIF de la
  BnF (`openapi.bnf.fr`, `full/max/0/default.jpg`), sha256 du JPEG estampillé
  dans les rapports de run (`RunProvenance.image_digests`).

**Le document** — presse du 19e siècle — est dans le **domaine public**.

**La nuance, à connaître plutôt qu'à ignorer** : les conditions d'utilisation
de la BnF portent sur la *reproduction numérique*, pas sur l'œuvre, et
distinguent la réutilisation non commerciale (libre) de la réutilisation
commerciale des reproductions (soumise à licence). Un usage comme fixture de
test relève de la première ; un rediffuseur commercial en aval doit le savoir.
C'est écrit ici pour qu'il l'apprenne d'ici et pas d'un courrier.

Ce corpus **ne part pas dans le paquet distribué** : il vit à la racine du
dépôt, hors de `packages/lidenbrock/`, et `pyproject.toml` déclare un allowlist
`sdist.include` explicite de quatre entrées qui ne le contient pas. Épinglé par
`tests/test_packaging_excludes_corpora.py`.

## Utilisation

```bash
# run vision réel (pas de --dpi : les coordonnées sont déjà en pixels)
python scripts/run_vision.py --provider mistral --model mistral-medium-2604 \
    --xml corpus/BnF-bpt6k3265015q/X0000002.xml \
    --image corpus/BnF-bpt6k3265015q/X0000002.jpg \
    --out ./vision_out_bnf
```

Mesuré (2026-07-25, `mistral-medium-2604`, mode vision, plafond 8 images) :
566 lignes, **101 appels**, 194 285 / 24 465 tokens in/out, 10 min 35 s,
**0 fallback, 0 erreur**, 170 lignes modifiées, sortie XSD-valide.
