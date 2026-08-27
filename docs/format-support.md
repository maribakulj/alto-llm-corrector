# ALTO / PAGE version support matrix

What saknussemm accepts, what it writes back, and what it can check
against an official schema. "Parse/rewrite" is
namespace-tolerant: the parsers accept any root namespace matching the
format marker (`loc.gov/standards/alto` / `primaresearch.org/PAGE`) and
the rewriter re-emits the document in its ORIGINAL namespace. "XSD
bundled" means `saknussemm.formats.validation` can validate that
namespace offline (schemas + provenance: `../src/saknussemm/formats/xsd/`).

| Format | Root namespace | Parse / rewrite | XSD bundled |
|---|---|---|---|
| ALTO v2 | `http://www.loc.gov/standards/alto/ns-v2#` | yes | `alto-2-1.xsd` |
| ALTO v3 | `http://www.loc.gov/standards/alto/ns-v3#` | yes | `alto-3-1.xsd` |
| ALTO v4 | `http://www.loc.gov/standards/alto/ns-v4#` | yes | `alto-4-4.xsd` |
| PAGE 2013 | `…/PAGE/gts/pagecontent/2013-07-15` | yes | `pagecontent_2013-07-15.xsd` |
| PAGE 2019 | `…/PAGE/gts/pagecontent/2019-07-15` | yes | `pagecontent_2019-07-15.xsd` |
| PAGE 2024 | `…/PAGE/gts/pagecontent/2024-07-15` | yes | `pagecontent_2024-07-15.xsd` |
| PAGE, other dates | any other `pagecontent/…` namespace | yes (tolerant) | no — validation raises `ParseError` |

## Validation roles

- **Input — diagnostic.** Real-world exports carry dialect extensions:
  Transkribus writes a `TranskribusMetadata` element that the official
  2013-07-15 schema does not know (pinned by
  `tests/test_xsd_validation.py`). A host should SURFACE input
  violations, not refuse the document — the manifest builds fine.
- **Output — gate.** A rewrite must never *introduce* a violation:
  zero violations when the source was clean, no new messages when the
  source carried a dialect. Enforced in the default test suite (the
  identity and slow-path/rebuild cases), fully offline — the xlink
  import inside ALTO schemas resolves to the bundled copy, never the
  network.

## API

```python
from saknussemm.formats.validation import validate_file, validate_bytes

violations = validate_file(Path("scan.xml"))   # [] == valid
violations = validate_bytes(xml_bytes, source_name="scan.xml")
```

Both raise `ParseError` (classified, §8.4) for malformed XML or a root
namespace with no bundled schema.

## Ce que les schémas embarqués coûtent, et pourquoi ils restent

Les sept XSD pèsent **380 Ko décompressés, soit 32 % du contenu du wheel** —
qui fait 363 Ko compressés au total. Ils sont dans l'installation de BASE, pas
derrière un extra, et c'est une décision plutôt qu'un oubli :

- la validation hors-ligne n'a de sens que si elle est hors-ligne. Un extra
  qui téléchargerait les schémas au premier appel rendrait le module
  dépendant du réseau exactement là où son intérêt est de ne pas l'être ;
- un extra `pip` ajoute des DÉPENDANCES, pas des fichiers. Sortir les schémas
  du wheel demanderait une seconde distribution, soit une unité de
  publication de plus à versionner et à garder cohérente, pour 380 Ko ;
- `saknussemm.formats.validation` n'est pas réexporté au niveau du paquet
  (la surface publique est close, cf. `versioning.md`), mais il est
  documenté ici et importable par son chemin de module, ce que
  `versioning.md` décrit comme une porte supportée.

`tests/test_packaging_excludes_corpora.py` vérifie que le wheel CONSTRUIT
porte bien les sept schémas : `test_xsd_validation.py` s'exécute depuis
l'arbre source et passerait à l'identique sur un wheel qui les aurait
perdus.
