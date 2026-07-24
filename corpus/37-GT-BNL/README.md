# 37 GT BNL — corpus image+ALTO temporaire

**Statut : TEMPORAIRE.** Déposé ici pour dérouler la chaîne vision (Phase 4)
et refitter la calibration QE presse 19e sur du réel, depuis n'importe quelle
machine. À supprimer une fois ces mesures faites.

> Note : `git rm` retirera les fichiers du répertoire de travail mais **pas de
> l'historique** — les 34 Mo resteront dans les objets git. Une purge réelle
> demanderait une réécriture d'historique (`git filter-repo`), à décider
> séparément.

## Contenu

37 pages appariées `NNNN.xml` + `NNNN.png` (~34 Mo) — presse luxembourgeoise
du 19e siècle, ground truth de la Bibliothèque nationale du Luxembourg.

- **ALTO v4**, `MeasurementUnit` = `mm10` (dixièmes de mm, **pas** des pixels).
- Scans **300 DPI**, donc la transformation XML→pixels est un scale uniforme
  `dpi/254` ≈ **1.1811** — vérifié sur les 37 pages.
- Le `CONTENT` ALTO est la **transcription humaine** (`CC="00"`) : c'est la
  RÉFÉRENCE, pas de l'OCR brut. L'entrée OCR se fabrique avec
  `scripts/ocr_corpus.py` (Tesseract sur les crops de ligne).
- **Corpus BILINGUE** : 312 lignes françaises / 140 allemandes / 70 indécises.
  Filtrer par langue avant toute calibration monolingue
  (`scripts/extract_press19_corpus.py --lang fr|de`).
- 522 lignes au total, dont 127 membres d'unités de césure.

## Utilisation

```bash
# OCR réelle appariée à la GT (deux qualités)
python scripts/ocr_corpus.py --corpus corpus/37-GT-BNL --lang fra --out ocr_fra.json
python scripts/ocr_corpus.py --corpus corpus/37-GT-BNL --lang spa --out ocr_spa.json

# benchmark texte / vision / hybride sur OCR réelle
python scripts/vision_benchmark.py --corpus corpus/37-GT-BNL --ocr ocr_fra.json

# texte propre 19e pour refitter la calibration QE
python scripts/extract_press19_corpus.py --corpus corpus/37-GT-BNL --lang fr \
    --out scripts/data/press19_real.txt
```

## Provenance et licence — À VÉRIFIER

Fourni par le mainteneur du dépôt ; l'archive d'origine ne contenait **ni
fichier de licence ni métadonnées de droits**, et les ALTO n'en portent pas
non plus. Les jeux GT de la BnL sont couramment diffusés en domaine public /
CC0, **mais ce n'est pas documenté ici** — à confirmer auprès de la BnL avant
toute rediffusion, et à consigner dans ce fichier. Le reste du dépôt trace ses
corpus (OCR17+ en CC-BY) ; celui-ci ne l'est pas encore.
