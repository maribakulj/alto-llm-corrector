# La vie d'une ligne

À quoi sert cette page : répondre à *« pourquoi cette ligne n'a-t-elle pas été
corrigée ? »* sans ouvrir le code. C'est la question de diagnostic la plus
fréquente, et la réponse traversait dix-sept modules sans qu'aucun document ne
la rassemble.

Trois choses à savoir d'abord :

- l'identité d'une ligne est **toujours** `(page_id, line_id)` ; un `line_id`
  nu se répète légitimement d'un fichier à l'autre (`ADR-001`, `ADR-007`) ;
- **les lignes ne fusionnent jamais** et **aucun texte ne migre** d'une ligne à
  l'autre : c'est l'invariant que tout le reste protège ;
- au moindre doute, la ligne **retombe sur son texte source**. Un repli n'est
  pas un échec du système : c'est le système qui refuse de deviner.

---

## 1. Le trajet

```
CorrectionPipeline.run
│
├─ preflight            refuse ce qui ne peut pas démarrer (6 contrôles)
├─ indexing             une passe : traces, index page-qualifié, nb d'unités
│
├─ POUR CHAQUE PAGE ─── PageDriver.process_page
│  │
│  ├─ planner.plan_page          PAGE → BLOCK → WINDOW → LINE
│  │                             une unité de césure n'est jamais coupée
│  ├─ (routing)                  hors chemin par défaut — voir §5
│  ├─ (batching)                 hors chemin par défaut — voir §5
│  │
│  └─ POUR CHAQUE CHUNK ─── driver._run_chunk
│     │
│     ├─ attempt._attempt_chunk         jusqu'à 3 essais, rampe de température
│     │  ├─ hyphenation.enrich_chunk_lines   ce que le producteur voit
│     │  ├─ producer.produce                 ← le seul appel sortant
│     │  ├─ editing.apply_edit_script        E1–E5, protocole d'édition
│     │  └─ validator.validate_llm_response  ÉTAGE A, avant tout retry
│     │
│     ├─ succès → outcome._finish_successful_chunk
│     │  ├─ reconcile._reconcile_chunk_hyphens   ÉTAGE B
│     │  ├─ acceptance._apply_line_acceptance    ÉTAGE C
│     │  └─ traces._finalize_chunk_traces
│     │
│     └─ échec → descente d'un cran de granularité, ou repli sur la source
│
├─ finalize._finalize_document    trois passes, dans CET ordre
│  ├─ 1. doublons adjacents + migration de frontière (document entier)
│  ├─ 2. préservation du caractère de coupure
│  └─ 3. politique de perte (strict / token_realign)
│
├─ decisions.derive_decision_set  la décision devient immuable
├─ rendering._render_outputs      réécriture + invariant de projection
└─ report / result                ce que l'appelant reçoit
```

Où lire la réponse, côté appelant :

```python
d = result.decisions.by_ref[LineRef(page_id="P1", line_id="TL7")]
d.status          # CORRECTED ou FALLBACK
d.fallback_reason # le code ci-dessous, suivi éventuellement de ": détail"
result.fallback_reasons           # agrégat par code, pour tout le run
result.report.edit_rejections     # les ops refusées par le protocole d'édition
```

---

## 2. Les trois étages de garde

Ils sont **délibérément trois**, à trois moments, et ils se règlent ensemble
(`GuardConfig`). Resserrer un seul étage peut ouvrir un trou entre deux.

| étage | quand | où | ce qu'il juge | ce qu'il fait en cas de refus |
|---|---|---|---|---|
| **A** | avant tout retry | `validator._check_pair_drift` | la dérive d'une paire de césure dans la réponse brute | lève → **nouvel essai** |
| **B** | après la réponse validée | `hyphenation.reconcile_hyphen_pair` | la cohérence des deux moitiés d'un mot coupé | **repli des deux membres** |
| **C** | après la réconciliation | `guards.check_line` | la ligne seule et ses voisines | **repli de la ligne** |

Les jumeaux entre A et B (`pair_drift_part1_word_growth` = 2 contre
`part1_max_word_growth` = 1) ne sont pas une duplication : A est plus permissif
parce qu'un retry est moins cher qu'un repli.

---

## 3. Toutes les raisons de repli

La liste est close, et pas seulement en prose :
`saknussemm.core.decide.FALLBACK_REASON_CODES` la porte, et
`tests/test_the_fallback_reasons_are_a_closed_set.py` refuse un code que le
moteur émettrait sans qu'il y figure — comme il refuse un code déclaré ici et
absent de cette page. Un code inconnu dans un rapport est donc un défaut de
la bibliothèque, pas une raison inédite.

### Étage C — la ligne et ses voisines (`guards.check_line`)

| code | ce qu'il veut dire |
|---|---|
| `too_different_from_source` | la correction ne ressemble plus assez à la ligne OCR |
| `closer_to_previous_line` | la correction ressemble plus à la ligne du dessus qu'à la sienne |
| `closer_to_next_line` | idem, ligne du dessous |
| `absorbs_previous_line` | la correction est « ligne précédente + cette ligne » concaténées |
| `absorbs_next_line` | idem vers l'aval |

Les trois derniers détectent la même faute — du texte a migré — sous trois
formes que le modèle produit réellement.

### Étage B et césure — l'unité, jamais un membre seul (`ADR-010`)

| code | ce qu'il veut dire |
|---|---|
| `hyphen_pair_fallback` | la réconciliation a refusé la paire : les deux moitiés reviennent à la source |
| `hyphen_partner_fell_back` | le partenaire direct est déjà tombé ; une paire mixte ne peut pas survivre |
| `hyphen_unit_fallback` | un membre est tombé pour sa propre raison, celui-ci est tiré avec lui |
| `orphan_hyphen_completed` | la ligne annonce une coupure sans partenaire visible, et la correction l'a complétée |

`hyphen_unit_fallback` est une **conséquence**, pas une décision : c'est ce qui
permet au rapport de distinguer la ligne fautive de celles qu'elle entraîne.

### Passes document-wide (`core/finalize.py`)

| code | ce qu'il veut dire |
|---|---|
| `adjacent_duplicate_detected` | deux lignes voisines, sources distinctes, corrections quasi identiques |
| `adjacent_duplicate_pair_atomicity` | membre d'unité tiré par un doublon |
| `boundary_migration_forward` | un mot entier a traversé la couture vers l'aval |
| `boundary_migration_backward` | idem vers l'amont |
| `format_loss: …` | `LossPolicy.strict` : la correction ne peut pas se projeter sans perdre la granularité `Word` |
| `rejected` | le défaut de `check_line` si une branche de refus ne nommait pas sa raison — aucune ne le fait aujourd'hui |
| `format_loss_pair_atomicity` | membre d'unité tiré par une perte de format |
| `token_realign: …` | `min_alignment_score` : les tokens ne s'alignent pas assez, ou un déplacement de mot est suspecté |
| `token_realign_pair_atomicity` | membre d'unité tiré par un refus d'alignement |

Sous `LossPolicy` par défaut (`REPORT`), les quatre derniers ne se produisent
jamais : la perte se projette, est comptée et attribuée ligne à ligne.
`token_realign` préserve la correction refusée dans `report.sidecar`.

### Niveau chunk (`core/outcome.py`)

| code | ce qu'il veut dire |
|---|---|
| `all_attempts_exhausted: …` | les essais sont épuisés, et aucune granularité plus fine n'aurait aidé |
| `chunk_error_absorbed: …` | une erreur de domaine récupérable a été absorbée pour laisser le run continuer |

Le détail qui suit `: ` porte la famille de l'échec, et la distinction est
utile : **`transport`** veut dire que le modèle n'a jamais été interrogé (429,
réseau) et que réessayer plus tard marcherait ; **`producer_output`** veut dire
qu'il a répondu sans tenir le contrat. Confondre les deux fait changer de
modèle quand il fallait arrêter de saturer son propre quota.

### Ce qui n'est pas un repli — les éditions refusées

Le protocole d'édition (`core/editing.py`) refuse des **opérations**, pas des
lignes : la ligne garde sa source et la refus apparaît sur
`report.edit_rejections`, pas sur `fallback_reason`.

`e1_unknown_line`, `e1_context_line`, `conflict`, `e2_overlap`, `e3_empty`,
`e3_newline`, `e4_span_growth`, `e4_line_budget`, `e5_hyphen`,
`e5_boundary_word`, `anchor_not_found`, `anchor_ambiguous`,
`anchor_out_of_range`, `anchor_empty_match`, `precondition_source_digest`.

---

## 4. Lire un cas concret

**« Cette ligne est `FALLBACK` avec `hyphen_unit_fallback` et je ne vois rien
d'anormal dessus. »** C'est normal : elle n'a rien fait. Cherchez l'autre
membre de son unité — `report.lines` donne le `hyphen_role` — il porte la
vraie raison.

**« `all_attempts_exhausted: transport: …` sur un tiers de la page. »** Le
modèle n'a pas été interrogé. Regardez `result.producer_calls` et le quota du
compte, pas la qualité du modèle.

**« Le rapport dit `corrected` mais le fichier n'a pas bougé. »** Une
correction peut aboutir à un texte identique à la source. L'autorité est le
`DecisionSet`, pas une comparaison d'octets — c'est écrit dans
`docs/promises.md`.

**« `format_loss` sur toutes mes lignes PAGE. »** Vous tournez en
`LossPolicy(strict=True)` sur un fichier dont les lignes portent des `Word` :
toute correction qui change le compte de mots est refusée par conception. La
politique par défaut projette et compte.

---

## 5. Ce qui n'est pas sur le chemin par défaut

Trois mécanismes traversent le code sans qu'aucun run par défaut ne les
exécute. Si vous lisez le chemin d'un chunk et butez dessus, vous pouvez les
sauter :

- **le routage QE** (`core/routing.py`, `core/quality.py`) — sans `qe_scorer`,
  chaque ligne va au producteur ;
- **l'escalade vers un producteur vision** (`escalation_producer`) — `None` par
  défaut ;
- **le plafond d'images par appel** (`core/batching.py`) — sans producteur qui
  déclare `max_images`, aucune découpe.

Les trois sont derrière une couture, `core.routing.ChunkRouter`, à laquelle
`PageDriver` demande son plan. Le pilote ne les connaît pas — une assertion
de `tests/test_routing_pipeline.py` le tient — donc lire la boucle interne du
moteur n'oblige pas à les comprendre. Ils sont court-circuités, pas seulement
inactifs : leur coût est cognitif, pas en temps d'exécution.

---

## 6. Où lire la suite

- `SPECS_LIB_V2.md` — le contrat : ce que la bibliothèque doit être.
- `docs/reading-a-report.md` — la structure du rapport §9.
- `docs/edit-protocol.md` — `E1`–`E6` en détail.
- `docs/adr/010-atomic-hyphen-groups.md` — pourquoi une unité de césure ne se
  divise jamais.
- `docs/adr/013-fallback-reason-precedence.md` — pourquoi c'est la **première**
  passe qui a retiré la correction qui garde l'attribution.
