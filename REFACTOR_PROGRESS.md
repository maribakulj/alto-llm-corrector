# Journal d'exécution — vague `RS`

**Ce fichier n'est pas un plan.** Le dépôt n'en a qu'un, `docs/PLAN.md`, et la
vague décrite ici y est inscrite sous les lignes `RS-1` à `RS-7`. Le relevé
qui l'a motivée est `docs/audit/AUDIT-2026-08-25-complexite-accidentelle.md`.
Ce fichier ne porte que l'**état d'avancement** : ce qui est fait, ce qui
reste, et ce qui a été délibérément écarté.

Il disparaît quand la vague est close.

## Règle de vérification, à chaque étape

```bash
python -m pytest tests/ -q                    # V1 — la suite (référence : 1780)
python -m mypy --strict src/saknussemm        # V2 — les types
python -m ruff check src tests && python -m ruff format --check src tests
python -m pytest tests/test_byte_parity_corpus.py \
    tests/test_byte_parity_page_corpus.py \
    tests/test_an_identity_run_reserialises_the_source.py \
    tests/test_metamorphic.py -q              # V4 — le différentiel d'octets
```

`mypy` doit être invoqué via `python -m mypy` : un `mypy` isolé peut traîner
sur le `PATH` et ne pas voir `pydantic`, ce qui produit 59 faux positifs.

**Sur les phases 3 à 6, tout digest qui bouge est un échec de l'étape**, jamais
une raison de mettre le golden à jour. Seules les étapes de la phase 2 qui
retirent du code mort peuvent en modifier un, et elles doivent dire pourquoi.

---

## Phase 1 — Sécurisation par tests

- [x] `RS-1.0` inscrire la vague : audit dans `docs/audit/`, lignes `RS-*` et
      arbitrage dans `docs/PLAN.md`, ce journal
- [x] `RS-1.1` élargir le golden byte-parity à tout le corpus ⭐ — 15 documents
      × 4 scénarios, 64 assertions, 8,8 s ; sensibilité mesurée sur 5 mutations
- [x] `RS-1.2` cliquet des lecteurs de champs pointeurs — recensement AST
      lecture/écriture, 4 modules épinglés, 2 à ramener à zéro
- [x] `RS-1.3` caractériser `_build_hyphen_pairs` / `_cross_page_partners` — le
      filet d'octets ne les voit PAS (mesuré) ; 11 assertions différentielles
- [x] `RS-1.4` couvrir directement `core/driver.py` — 8 assertions, la bourse
      partagée bornée sur 5 valeurs, le refus permanent qui ne descend pas
- [x] `RS-1.5` clôture `LineTrace` → `LineOutcome` — 15 champs, 9 projetés,
      6 écartés avec leur raison, recalculée sur l'AST du traducteur
- [x] `RS-1.6` corriger les deux cibles de patch `asyncio.sleep` — remplacées
      par l'injection de `RetryPolicy`, plus aucun patch de module global
- [x] `RS-1.7` rédiger `docs/la-vie-d-une-ligne.md` — fait tôt : la garde
      `test_a_cited_document_exists` refuse une citation vers un document non écrit

## Phase 2 — Code mort et vérité documentaire

- [x] `RS-2.1` les quatre affirmations fausses
- [x] `RS-2.2` supprimer `RewriteResult.__iter__` — 49 sites de test convertis
      en accès par attribut, puis la méthode retirée
- [x] `RS-2.3` trancher le poids des XSD — **gardés dans l'installation de
      base**, décision écrite dans `docs/format-support.md`, et le wheel
      construit est désormais vérifié comme les portant
- [x] `RS-2.4` sortir de `policies.py` les 4 classes qui n'en sont pas —
      `core/schemas/chunking.py` (3) et `report.py` (1), zéro import touché

## Phase 3 — Simplifications locales

- [x] `RS-3.1` router `reconcile._build_hyphen_pairs` sur les primitives — 6 → 0
- [x] `RS-3.2` router `indexing._cross_page_partners` sur les primitives — 4 → 0
- [x] `RS-3.3` fermer le cliquet à zéro hors exemptions justifiées — `_ACCESS`
      ne porte plus que `pairing` et `units`, `_MUST_REACH_ZERO` est vide
- [x] `RS-3.4` retirer le sentinel à trois états de `reconcile_hyphen_pair` —
      classe `_Unset` typée, le `type: ignore[assignment]` disparaît

## Phase 4 — Réduction des abstractions

- [x] `RS-4.2` recalibrer les cliquets — chaque entrée porte sa raison (≥40
      car.), les 6 entrées `formats/` quittent la table des dettes, 6
      plafonds descendent à leur valeur mesurée
- [x] `RS-4.3` décision écrite : `PageWorkspace` / `RunContext` restent —
      docstring ramenée de 36 à 27 lignes, décision dans `docs/PLAN.md`
- [x] `RS-4.4` décision écrite : les quatre représentations par ligne restent
- [x] `RS-4.1` `_FinalizeOrder` — **écarté, pas reporté.** Le jeton garde
      l'ordre des passes que `S1` va traverser ; `S1` n'est pas dans cette
      vague, donc la condition de retrait n'est pas remplie et ne le sera pas
      ici. Inscrit au § « Ce que cette vague ne fait pas » de `docs/PLAN.md`.

## Phase 5 — Découplage architectural

- [x] `RS-5.0` arbitrage écrit (`docs/PLAN.md`, Décisions déléguées 2026-08-25)
- [x] `RS-5.2` casser le cycle `formats.loader` ↔ `formats.alto.parser` —
      `sniff_format` descend dans `formats/_xml.py`, dont les deux dépendent
      déjà ; l'import différé disparaît
- [x] `RS-5.1` sortir routage / QE / confiance du chemin chaud — `ChunkRouter`,
      `core/driver.py` n'importe plus `core.quality` ni `core.batching`.
      **Cible « ≤ 9 paramètres » retirée** : les cinq restants sont des
      coutures publiques, les retirer serait un changement de surface que
      l'arbitrage du 2026-08-25 interdit à cette vague (raison écrite dans
      `docs/PLAN.md`)
- [x] `RS-5.3` trancher la frontière `integrations/` ↔ `producers/`, et la garder
      — `VisionEditProducer` rejoint `producers/`, deux assertions tiennent
      la règle (ce qu'un producteur importe, et où vit un producteur)

## Phase 6 — Nettoyage final

- [ ] `RS-6.1` trier la prose, un module par commit (0,84 → ≤ 0,45)
- [ ] `RS-6.2` fermer l'ensemble des raisons de repli
- [ ] `RS-6.3` profils `GuardConfig` et vérité SemVer
- [ ] `RS-6.4` finaliser `docs/la-vie-d-une-ligne.md`

## Phase 7 — Vérification globale

- [ ] `RS-7.1` différentiel complet, digests comparés à l'entrée
- [ ] `RS-7.2` re-mesurer les six métriques
- [ ] `RS-7.3` refermer `docs/PLAN.md`, `docs/promises.md`, `CHANGELOG.md`
- [ ] `RS-7.4` relire `README.md` et `docs/la-vie-d-une-ligne.md` en externe

---

## Les six mesures

| mesure | entrée (2026-08-25) | courant | cible |
|---|---|---|---|
| lignes de code effectif `src/` | 9 207 | 9 207 | ~9 000 |
| ratio prose/code | 0,84 | 0,84 | ≤ 0,45 |
| modules dans `core/` | 42 | 42 | ≤ 42 |
| paramètres `CorrectionPipeline.__init__` | 14 | 14 | cible retirée¹ |
| lecteurs de pointeurs hors `pairing`/`units` | 3 | **0** | 0 |
| affirmations fausses recensées | 4 | 0 | 0 |

¹ La cible reposait sur une hypothèse que `RS-5.1` a vérifiée et
invalidée — voir `docs/PLAN.md`, § « La cible ≤ 9 paramètres était fausse ».

Base de référence, 2026-08-25 : **1780 tests verts** ; après la phase 1,
**1871**, `mypy --strict` propre
sur 76 fichiers, `ruff` propre sur 273 fichiers.
