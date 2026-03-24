# SPECS 
---

## Vue d'ensemble

Construire `alto-llm-corrector` : une application web de post-correction OCR text-only pour fichiers ALTO XML.

**Ce que fait l'app :**
1. L'utilisateur uploade des fichiers ALTO XML (ou un ZIP)
2. Il choisit un fournisseur LLM (OpenAI / Anthropic / Mistral / Google)
3. Il saisit sa clé API
4. Il charge la liste réelle des modèles disponibles
5. Il choisit un modèle et lance le traitement
6. Le backend orchestre la correction page par page
7. L'ALTO corrigé est téléchargeable

**Ce que l'app ne fait PAS :**
- Pas d'OCR image
- Pas de resegmentation
- Pas de fusion/scission de lignes
- Pas de traduction
- Pas de modernisation du texte

**Contrainte de déploiement :** fonctionne en local (docker-compose) ET sur Hugging Face Spaces (Dockerfile racine, port 7860, un seul conteneur servant le frontend buildé comme fichiers statiques via FastAPI).

---

## Stack technique

```
Backend    : Python 3.11+, FastAPI, Pydantic v2, httpx, lxml, uvicorn, sse-starlette
Frontend   : React + TypeScript + Vite + Tailwind CSS
Conteneurs : Dockerfile backend, Dockerfile frontend, docker-compose.yml
             + Dockerfile racine pour HF Spaces (build frontend → sert via FastAPI)
Storage    : /tmp/app-jobs/{job_id}/ sur disque local, état jobs en mémoire
DB         : aucune
```

---

## Arborescence cible

```
alto-llm-corrector/
├── Dockerfile                    ← HF Spaces (build tout-en-un, port 7860)
├── docker-compose.yml            ← dev local (backend:8000 + frontend:5173)
├── .env.example
├── README.md
├── SPECS.md                      ← ce fichier
├── CLAUDE.md                     ← généré par /init
├── examples/
│   └── sample.xml                ← ALTO v3 minimal avec césures pour tests
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── schemas/
│   │   │   └── __init__.py       ← tous les modèles Pydantic
│   │   ├── alto/
│   │   │   ├── __init__.py
│   │   │   ├── parser.py         ← parsing ALTO v2/v3/v4 + détection césures
│   │   │   ├── hyphenation.py    ← Hyphenation Reconciler
│   │   │   └── rewriter.py       ← réécriture ALTO avec HYP/SUBS_*
│   │   ├── providers/
│   │   │   ├── __init__.py       ← registry + get_provider()
│   │   │   ├── base.py           ← Protocol + SYSTEM_PROMPT + JSON_SCHEMA
│   │   │   ├── openai_provider.py
│   │   │   ├── anthropic_provider.py
│   │   │   ├── mistral_provider.py
│   │   │   └── google_provider.py
│   │   ├── jobs/
│   │   │   ├── __init__.py
│   │   │   ├── store.py          ← JobStore en mémoire + queues SSE
│   │   │   ├── chunk_planner.py  ← planificateur adaptatif (hyphen-aware)
│   │   │   ├── validator.py      ← validation réponses LLM
│   │   │   └── orchestrator.py   ← moteur principal + intégration reconciler
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── providers.py      ← POST /api/providers/models
│   │   │   └── jobs.py           ← POST/GET /api/jobs + SSE + download
│   │   └── storage/
│   │       └── __init__.py       ← gestion fichiers disque
│   └── tests/
│       ├── test_parser.py
│       ├── test_hyphenation.py   ← tests du reconciler
│       ├── test_rewriter.py
│       ├── test_chunk_planner.py
│       ├── test_validator.py
│       └── test_integration.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── types/
        │   └── index.ts
        ├── api/
        │   └── client.ts
        ├── hooks/
        │   ├── useJobStream.ts
        │   └── useModels.ts
        └── components/
            ├── FileUpload.tsx
            ├── ProviderSelector.tsx
            ├── ModelSelector.tsx
            ├── ApiKeyInput.tsx
            ├── JobProgress.tsx
            ├── LogPanel.tsx
            └── DownloadButton.tsx
```

---

## Modèles Pydantic (schemas/__init__.py)

### Enums

```python
class JobStatus(str, Enum): QUEUED / STARTED / RUNNING / COMPLETED / FAILED
class LineStatus(str, Enum): PENDING / CORRECTED / FALLBACK / FAILED
class ChunkGranularity(str, Enum): PAGE / BLOCK / WINDOW / LINE
class Provider(str, Enum): OPENAI / ANTHROPIC / MISTRAL / GOOGLE
class HyphenRole(str, Enum):
    NONE = "none"
    PART1 = "HypPart1"    # dernière ligne de la paire : porte le fragment gauche
    PART2 = "HypPart2"    # première ligne de la paire : porte le fragment droit
```

### Coords

```python
class Coords(BaseModel):
    hpos: int; vpos: int; width: int; height: int
```

### LineManifest — champs de césure ajoutés

```python
class LineManifest(BaseModel):
    line_id: str
    page_id: str
    block_id: str
    line_order_global: int
    line_order_in_block: int
    coords: Coords
    ocr_text: str
    prev_line_id: Optional[str] = None
    next_line_id: Optional[str] = None
    expected: bool = True
    received: bool = False
    corrected_text: Optional[str] = None
    status: LineStatus = LineStatus.PENDING

    # ── Champs de césure ─────────────────────────────────────────────
    hyphen_role: HyphenRole = HyphenRole.NONE
    # PART1 : cette ligne se termine par la première partie d'un mot coupé
    # PART2 : cette ligne commence par la deuxième partie d'un mot coupé

    hyphen_pair_line_id: Optional[str] = None
    # ID de la ligne jumelle dans la paire (PART1 → pointe vers PART2 et vice-versa)

    hyphen_subs_content: Optional[str] = None
    # Mot logique complet si présent dans SUBS_CONTENT de l'ALTO source
    # Exemple : "porte" pour une paire (por- / te)

    hyphen_source_explicit: bool = False
    # True si la césure provient de SUBS_TYPE ou HYP dans l'ALTO source
    # False si elle a été détectée heuristiquement (dernier token finissant par -)
```

### Autres modèles (inchangés)

```python
class BlockManifest(BaseModel):
    block_id: str; page_id: str; block_order: int
    coords: Coords; line_ids: list[str]

class PageManifest(BaseModel):
    page_id: str; source_file: str; page_index: int
    page_width: int; page_height: int
    blocks: list[BlockManifest]; lines: list[LineManifest]
    status: JobStatus = JobStatus.QUEUED

class DocumentManifest(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_files: list[str]; pages: list[PageManifest]
    total_pages: int; total_blocks: int; total_lines: int
    status: JobStatus = JobStatus.QUEUED

class ChunkPlannerConfig(BaseModel):
    max_input_chars_per_request: int = 12000
    max_lines_per_request: int = 80
    line_window_size: int = 12
    line_window_overlap: int = 1

class ChunkRequest(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str; page_id: str; block_id: Optional[str]
    granularity: ChunkGranularity; line_ids: list[str]; attempt: int = 0

class ChunkPlan(BaseModel):
    page_id: str; chunks: list[ChunkRequest]; granularity: ChunkGranularity

class JobManifest(BaseModel):
    job_id: str; provider: Provider; model: str
    status: JobStatus = JobStatus.QUEUED
    document_manifest: Optional[DocumentManifest] = None
    total_lines: int = 0; lines_modified: int = 0
    chunks_total: int = 0; retries: int = 0; fallbacks: int = 0
    duration_seconds: Optional[float] = None; error: Optional[str] = None
```

### Payload LLM enrichi

```python
class LLMLineInput(BaseModel):
    line_id: str
    prev_text: Optional[str] = None
    ocr_text: str
    next_text: Optional[str] = None

    # Champs de césure — absents si hyphen_role == NONE
    hyphenation_role: Optional[str] = None          # "HypPart1" | "HypPart2"
    hyphen_candidate: Optional[bool] = None
    hyphen_join_with_next: Optional[bool] = None    # présent sur PART1
    hyphen_join_with_prev: Optional[bool] = None    # présent sur PART2
    logical_join_candidate: Optional[str] = None    # mot logique si connu

class LLMUserPayload(BaseModel):
    task: str = "correct_ocr_lines"
    granularity: ChunkGranularity
    document_id: str; page_id: str; block_id: Optional[str]
    lines: list[LLMLineInput]
```

---

## Parser ALTO (alto/parser.py)

**Responsabilité :** lire un fichier ALTO XML, extraire pages/blocs/lignes, retourner des PageManifest. Détecter et annoter les césures interlignes.

### Règles générales

- Détecter automatiquement le namespace depuis le tag racine
- Supporter ALTO v2, v3, v4, et sans namespace
- Pour chaque `TextLine`, extraire : ID, HPOS, VPOS, WIDTH, HEIGHT
- Reconstruire `ocr_text` :
  - `String` → append `CONTENT`
  - `SP` → append `" "`
  - `HYP` → append `CONTENT` si présent, sinon `"-"`
- Normaliser en Unicode NFC, supprimer `\r`, strip bords
- Lier `prev_line_id` / `next_line_id` entre lignes consécutives

### Détection des césures — règles de priorité

**Cas 1 — Césure explicite (source_explicit = True) :**

Lors du parcours des enfants d'une TextLine, détecter :
- Un élément `HYP` présent en dernière position (= PART1)
- Un attribut `SUBS_TYPE="HypPart1"` sur le dernier `String` (= PART1)
- Un attribut `SUBS_TYPE="HypPart2"` sur le premier `String` (= PART2)
- Extraire `SUBS_CONTENT` s'il est présent sur l'un ou l'autre

**Cas 2 — Césure heuristique (source_explicit = False) :**

Si aucun marquage SUBS_TYPE/HYP n'est présent mais que le dernier token non-espace de la ligne se termine par `-` : marquer comme candidate heuristique. Mode conservateur : ne pas inventer de `SUBS_CONTENT`.

**Liaison des paires :**

Après avoir parcouru toutes les lignes de la page, faire un second pass :
- Pour chaque ligne marquée PART1, la ligne suivante dans l'ordre global est candidate PART2
- Si la ligne suivante porte déjà PART2 ou est une candidate heuristique cohérente → créer le lien bidirectionnel via `hyphen_pair_line_id`
- Si `SUBS_CONTENT` est présent sur PART1 et absent sur PART2 (ou vice-versa), propager la valeur sur les deux

**Signatures principales :**

```python
def build_document_manifest(files: list[tuple[Path, str]]) -> DocumentManifest
def parse_alto_file(xml_path, source_name, page_index_offset, global_line_offset)
    -> tuple[list[PageManifest], etree._Element]
def _detect_hyphenation(lines: list[LineManifest]) -> None
    # Mutates lines in-place : remplit hyphen_role, hyphen_pair_line_id, hyphen_subs_content
```

---

## Hyphenation Reconciler (alto/hyphenation.py)

C'est le module central ajouté par rapport à la V1. Son rôle est d'orchestrer la gestion des mots cassés entre deux lignes : **l'application décide, le LLM informe**.

**Principe fondamental :**

> Les césures interlignes ne doivent pas être laissées à la seule initiative du LLM. L'application détecte les paires de lignes liées par césure, transmet cette information au modèle, puis réinscrit la sortie sur les deux lignes physiques. En cas d'ambiguïté, la forme source est préservée.

### Responsabilités du module

1. **`enrich_chunk_lines()`** — préparer les `LLMLineInput` enrichis avec métadonnées de césure
2. **`reconcile_hyphen_pair()`** — après réponse LLM, réinscrire la correction sur la paire physique
3. **`should_stay_in_same_chunk()`** — prédicat pour le chunk planner

### Fonction `enrich_chunk_lines()`

```python
def enrich_chunk_lines(
    line_manifests: list[LineManifest],
    all_lines_by_id: dict[str, LineManifest],
) -> list[LLMLineInput]:
```

Pour chaque ligne, construire le `LLMLineInput` avec :
- `prev_text` / `next_text` comme d'habitude
- Si `hyphen_role != NONE` :
  - Renseigner `hyphenation_role`, `hyphen_candidate = True`
  - Sur PART1 : `hyphen_join_with_next = True`
  - Sur PART2 : `hyphen_join_with_prev = True`
  - Si `hyphen_subs_content` connu : `logical_join_candidate = hyphen_subs_content`

### Fonction `reconcile_hyphen_pair()`

```python
def reconcile_hyphen_pair(
    part1: LineManifest,
    part2: LineManifest,
    corrected_part1: str,
    corrected_part2: str,
) -> tuple[str, str, Optional[str]]:
    """
    Retourne (final_text_part1, final_text_part2, resolved_subs_content).
    
    Garantit :
    - Les deux lignes physiques restent distinctes
    - Aucun texte ne migre d'une ligne à l'autre
    - Si la correction est ambiguë, retourner les textes source
    """
```

**Algorithme :**

```
1. Isoler le dernier token non-espace de corrected_part1 (candidat fragment gauche)
2. Isoler le premier token non-espace de corrected_part2 (candidat fragment droit)
3. Si source_explicit == True (césure encodée dans l'ALTO source) :
   a. Si hyphen_subs_content connu → utiliser comme référence pour valider
   b. Vérifier que la concaténation (fragment_gauche + fragment_droit) est cohérente
      avec le mot logique attendu (si connu)
   c. Conserver les frontières physiques : part1 garde son texte, part2 garde le sien
   d. resolved_subs_content = mot logique déterminé avec confiance
4. Si source_explicit == False (heuristique) :
   a. Mode conservateur : ne rien reconstruire agressivement
   b. Retourner corrected_part1, corrected_part2 tels quels
   c. resolved_subs_content = None
5. En cas de doute à n'importe quelle étape : retourner les textes OCR source
```

**Ce que cette fonction ne fait JAMAIS :**
- Fusionner les deux lignes en une
- Déplacer "porte" sur la ligne 1 et vider la ligne 2
- Inventer un SUBS_CONTENT sans base dans la source

### Fonction `should_stay_in_same_chunk()`

```python
def should_stay_in_same_chunk(
    line_a: LineManifest,
    line_b: LineManifest,
) -> bool:
    """
    Retourne True si line_a et line_b doivent impérativement être
    dans le même chunk LLM (paire liée par césure).
    """
    return (
        line_a.hyphen_role == HyphenRole.PART1
        and line_a.hyphen_pair_line_id == line_b.line_id
    ) or (
        line_b.hyphen_role == HyphenRole.PART1
        and line_b.hyphen_pair_line_id == line_a.line_id
    )
```

---

## Rewriter ALTO (alto/rewriter.py)

**Responsabilité :** réécrire un fichier ALTO en remplaçant les enfants textuels des TextLine, en reconstituant HYP et SUBS_* pour les paires de césure.

### Invariants absolus à respecter

- Ne jamais modifier `TextLine/@ID`, `/@HPOS`, `/@VPOS`, `/@WIDTH`, `/@HEIGHT`
- Ne jamais changer l'ordre XML des `TextLine`
- Ne jamais fusionner deux TextLine

### Algorithme par TextLine — cas sans césure

1. Supprimer tous les enfants `String`, `SP`, `HYP` existants
2. Supprimer attributs `WC`, `CC` de la TextLine
3. Tokeniser `corrected_text` avec `re.split(r'(\s+)', text)`
4. Segments espace → élément `SP`
5. Segments non-espace → élément `String` avec ID `{line_id}_STR_{n:04d}`
6. Géométrie heuristique : redistribuer `TextLine.WIDTH` proportionnellement à `len(token)`
7. Tous les nouveaux `String` héritent de `VPOS` et `HEIGHT` de la TextLine

**Géométrie proportionnelle :**
- Poids mot = `len(mot)`
- Poids espace = `max(1, round(len(espace) * 0.6 * unit))`
- `unit = TextLine.WIDTH / total_poids`
- Corriger l'arrondi sur le dernier token pour que la somme = `TextLine.WIDTH` exact

### Algorithme par TextLine — cas PART1 (ligne terminée par césure)

Condition : `line_manifest.hyphen_role == HyphenRole.PART1`

1. Supprimer les enfants existants
2. Construire les `String` pour tous les tokens jusqu'à l'avant-dernier mot inclus
3. Pour le dernier mot (fragment gauche) :
   - Créer un `String` avec son `CONTENT` (ex: `"por"`)
   - Si `hyphen_subs_content` est connu : ajouter `SUBS_TYPE="HypPart1"` et `SUBS_CONTENT=hyphen_subs_content`
4. Créer un élément `HYP` après ce dernier `String` :
   - `CONTENT="-"`, `HPOS/VPOS/WIDTH/HEIGHT` heuristiques en fin de ligne

### Algorithme par TextLine — cas PART2 (ligne commençant par suite de césure)

Condition : `line_manifest.hyphen_role == HyphenRole.PART2`

1. Supprimer les enfants existants
2. Pour le premier mot (fragment droit) :
   - Créer un `String` avec son `CONTENT` (ex: `"te"`)
   - Si `hyphen_subs_content` est connu : ajouter `SUBS_TYPE="HypPart2"` et `SUBS_CONTENT=hyphen_subs_content`
3. Construire les `String` + `SP` pour les tokens suivants normalement

### Politique de confiance pour SUBS_CONTENT

| Condition | Action |
|-----------|--------|
| `source_explicit=True` et `hyphen_subs_content` fourni par source | Écrire SUBS_CONTENT tel quel |
| `source_explicit=True` et SUBS_CONTENT résolu par reconciler avec confiance | Écrire SUBS_CONTENT résolu |
| `source_explicit=False` (heuristique) | Ne pas écrire SUBS_CONTENT |
| Ambiguïté ou incertitude | Ne pas écrire SUBS_CONTENT |

Ajouter une entrée de processing dans `Description/Processing` si la section existe.

---

## Chunk Planner (jobs/chunk_planner.py)

**Règle additionnelle : les paires de césure ne peuvent pas être séparées.**

Le planner doit intégrer la contrainte `should_stay_in_same_chunk()` du Hyphenation Reconciler à chaque niveau de découpage.

### Hiérarchie de décision

```
1. PAGE ENTIÈRE
   Condition : total chars ≤ 12000 ET total lignes ≤ 80
   → 1 seul chunk contenant toutes les lignes de la page

2. BLOC PAR BLOC
   Condition : chaque bloc tient dans les budgets
   MAIS : si une paire de césure est à cheval sur deux blocs,
          les deux blocs concernés doivent être regroupés dans un seul chunk.
   → Si un regroupement dépasse le budget → invalide, passer à WINDOW

3. FENÊTRES DE LIGNES
   window_size=12, overlap=1, step=11
   MAIS : aucune fenêtre ne peut couper une paire de césure en deux.
   Règle : si la ligne N est PART1 et que la ligne N+1 est sa PART2,
           et que N est le dernier index d'une fenêtre,
           étendre la fenêtre d'une ligne pour inclure N+1.
   → Chevauchement possible : ajuster le step pour ne pas laisser de paire orpheline.

4. LIGNE PAR LIGNE (dernier recours)
   Si une ligne fait partie d'une paire de césure,
   traiter la paire comme un bloc atomique inséparable :
   → le "chunk ligne" contient en réalité 2 lignes liées.
```

**Fonction `downgrade_granularity(current)` :** inchangée — retourne le niveau suivant ou None.

---

## Prompt système (providers/base.py)

Le prompt système est enrichi avec une règle explicite sur les césures :

```
Tu es un moteur de correction post-OCR spécialisé dans les documents patrimoniaux.

Règles absolues :
1. Corrige uniquement les erreurs manifestes d'OCR.
2. Conserve la langue source.
3. Conserve l'orthographe historique quand elle semble intentionnelle.
4. Ne traduis rien.
5. Ne modernise pas volontairement le texte.
6. Ne fusionne jamais deux lignes.
7. Ne scinde jamais une ligne.
8. Ne déplace jamais du texte d'une ligne à l'autre.
9. Chaque entrée line_id doit produire exactement une sortie avec le même line_id.
10. corrected_text doit contenir une seule ligne, sans caractère de saut de ligne.
11. Retourne uniquement un JSON valide conforme au schéma fourni.
12. En cas d'incertitude, fais la correction minimale.
13. Quand une ligne porte hyphenation_role="HypPart1" ou "HypPart2",
    tu dois corriger chaque ligne individuellement sans déplacer de texte
    entre elles. Le mot logique (logical_join_candidate) t'est fourni
    à titre indicatif uniquement pour le contexte.
```

### Payload user enrichi — exemple avec césure

```json
{
  "task": "correct_ocr_lines",
  "granularity": "window",
  "document_id": "DOC_001",
  "page_id": "P_001",
  "lines": [
    {
      "line_id": "TL_101",
      "prev_text": "Il marchait vite.",
      "ocr_text": "Il s'approcha de la por-",
      "next_text": "te du palais",
      "hyphenation_role": "HypPart1",
      "hyphen_candidate": true,
      "hyphen_join_with_next": true,
      "logical_join_candidate": "porte"
    },
    {
      "line_id": "TL_102",
      "prev_text": "Il s'approcha de la por-",
      "ocr_text": "te du palais",
      "next_text": "La garde était présente.",
      "hyphenation_role": "HypPart2",
      "hyphen_candidate": true,
      "hyphen_join_with_prev": true,
      "logical_join_candidate": "porte"
    }
  ]
}
```

Le LLM corrige chaque ligne pour ses erreurs OCR éventuelles, mais ne déplace aucun fragment d'une ligne à l'autre. C'est le Hyphenation Reconciler qui gère ensuite la reconstruction ALTO.

### Schéma JSON de sortie (inchangé)

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["lines"],
  "properties": {
    "lines": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["line_id", "corrected_text"],
        "properties": {
          "line_id": {"type": "string"},
          "corrected_text": {"type": "string"}
        }
      }
    }
  }
}
```

---

## Validateur (jobs/validator.py)

Après chaque réponse LLM, valider :
1. Présence de la clé `"lines"`
2. Nombre d'entrées = nombre attendu
3. Tous les `line_id` attendus présents
4. Aucun `line_id` doublon ou inconnu
5. Chaque `corrected_text` : string non vide, sans `\n` ni `\r`

**Validation additionnelle pour les paires de césure :**

Si le chunk contient une paire PART1/PART2, vérifier que :
- `corrected_text` de PART1 ne contient pas le texte logique entier du mot coupé (ce serait une fusion interdite)
- `corrected_text` de PART2 n'est pas vide (la suite de la césure ne doit pas avoir disparu)

En cas de violation sur une paire de césure : lever `ValueError` avec motif `"hyphen_integrity_violation"`.

---

## Orchestrateur (jobs/orchestrator.py)

L'orchestrateur intègre le Hyphenation Reconciler **avant** et **après** chaque appel LLM.

### Pipeline par chunk

```
AVANT l'appel LLM :
  1. Récupérer les LineManifest du chunk
  2. Appeler enrich_chunk_lines() → LLMLineInput enrichis avec métadonnées césure
  3. Construire le payload user

APPEL LLM (inchangé)

APRÈS l'appel LLM :
  4. Valider la réponse (validator.py)
  5. Pour chaque paire PART1/PART2 présente dans le chunk :
     a. Extraire corrected_part1 et corrected_part2 depuis la réponse
     b. Appeler reconcile_hyphen_pair(part1, part2, corrected_part1, corrected_part2)
     c. Remplacer les corrected_text dans le résultat par les textes réconciliés
     d. Stocker resolved_subs_content sur les deux LineManifest
  6. Appliquer les corrections finales aux LineManifest
```

### Politique de retry — cas spécifique aux paires de césure

Si la validation échoue avec `"hyphen_integrity_violation"` :
- Ne pas downgrader la granularité
- Retry immédiat avec temperature=0 et prompt plus explicite sur la règle 13
- Si second échec : conserver les textes OCR source pour les deux lignes de la paire

### Politique générale de retry (inchangée)

| Tentative | Action |
|-----------|--------|
| 1 | Appel normal |
| 2 | Retry même chunk, temperature=0 |
| 3 | Retry encore |
| Après 3 échecs | Downgrade granularité |
| Plus de granularité | Conserver texte OCR source, logger warning |

---

## Fournisseurs LLM (providers/)

**Protocole commun :**
```python
class BaseProvider(Protocol):
    async def list_models(self, api_key: str) -> list[ModelInfo]: ...
    async def complete_structured(
        self, api_key, model, system_prompt, user_payload, json_schema, temperature=0.0
    ) -> dict: ...
```

**OpenAI :**
- Lister : `GET /v1/models` + allowlist préfixes (`gpt-4`, `gpt-3.5`, `o1`, `o3`, `o4`)
- Exclure : `instruct`, `embedding`, `whisper`, `tts`, `dall-e`, `moderation`, `realtime`, `audio`
- Générer : `POST /v1/chat/completions` avec `response_format.type = "json_schema"`

**Anthropic :**
- Lister : `GET /v1/models` (headers: `x-api-key`, `anthropic-version: 2023-06-01`)
- Générer : `POST /v1/messages` avec `output_config.format.type = "json_schema"`
- Fallback si 400/422 : plain JSON

**Mistral :**
- Lister : `GET /v1/models`, filtrer `capabilities.completion_chat == true`
- Générer : `POST /v1/chat/completions` avec `response_format.type = "json_schema"`
- Fallback si 400/422 : `response_format.type = "json_object"`

**Google Gemini :**
- Lister : `GET .../v1beta/models?key={api_key}`, filtrer `generateContent` dans `supportedGenerationMethods`
- Exclure : `embed`, `aqa`, `attribute`
- Générer : `POST .../models/{model}:generateContent` avec `responseMimeType: "application/json"` et `responseSchema`

---

### Routes API (api/)

```
POST /api/providers/models
  Body: {provider, api_key}
  Response: {provider, models: [{id, label, supports_structured_output, context_window}]}

POST /api/jobs
  multipart/form-data: files[], provider, api_key, model
  Response: {job_id}

GET /api/jobs/{job_id}
  Response: JobStatusResponse

GET /api/jobs/{job_id}/events
  SSE stream

GET /api/jobs/{job_id}/download
  Response: XML (1 fichier) ou ZIP (plusieurs fichiers)
```

### SSE Events

| Événement | Données clés |
|-----------|-------------|
| `queued` | job_id |
| `started` | job_id |
| `document_parsed` | total_pages, total_blocks, total_lines, hyphen_pairs |
| `page_started` | page_id, page_index, line_count, hyphen_pair_count |
| `chunk_planned` | page_id, granularity, chunk_count |
| `chunk_started` | chunk_id, granularity, line_count, attempt |
| `chunk_completed` | chunk_id, line_count, hyphen_pairs_reconciled, attempt |
| `retry` | chunk_id, attempt, error |
| `warning` | message |
| `page_completed` | page_id, page_index, corrections |
| `completed` | total_lines, lines_modified, hyphen_pairs_total, duration_seconds |
| `failed` | error |
| `keepalive` | {} |

---

## Stockage (storage/__init__.py)

```
/tmp/app-jobs/{job_id}/
  input/          ← fichiers uploadés (XML extraits)
  outputs/        ← fichiers ALTO corrigés (*_corrected.xml)
```

- Accepter `.xml`, `.alto.xml`, `.zip`
- Si ZIP : extraire tous les XML, flatten les chemins (basename seulement)
- Multi-fichiers : document multi-pages, ordre = ordre d'upload

---

## Interface utilisateur

**Écran unique :**

1. **Header** — titre + sous-titre
2. **Upload** — drag & drop, liste ordonnée des fichiers + nb de paires de césure détectées
3. **Configuration** — sélecteur fournisseur + clé API masquée + bouton "Charger les modèles" + sélecteur modèle
4. **Contrôles** — bouton Play (disabled si config incomplète)
5. **Progression** — barre globale + compteur pages/lignes/paires césure réconciliées
6. **Logs** — panel scrollable SSE en temps réel, code couleur par type
7. **Résultats** — bouton télécharger + stats (lignes modifiées, paires réconciliées, durée)

**Règles UX :**
- Play activé uniquement si : fichier(s) + fournisseur + clé API + modèle
- Clé API jamais loguée, jamais renvoyée au frontend

---

## Déploiement Hugging Face Spaces

**Dockerfile racine :**
- Base : `python:3.11-slim`
- Build frontend React (`npm run build`) dans `/app/static`
- FastAPI sert `/app/static` comme `StaticFiles` sur `/`
- **Port obligatoire : 7860**
- `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]`

**docker-compose.yml (dev local) :**
- `backend` : port 8000
- `frontend` : port 5173 avec proxy vers backend

---

## Sécurité

- Ne jamais logger la clé API
- Ne jamais écrire la clé API sur disque
- Ne jamais renvoyer la clé au frontend
- Whitelist extensions uploadées : `.xml`, `.alto`, `.zip`
- Nettoyer les fichiers temporaires après téléchargement

---

## Tests obligatoires

**Unit tests :**

`test_parser.py` :
- Détection namespace v2/v3/v4/sans ns
- Reconstruction ocr_text (String, SP, HYP)
- Construction PageManifest (nb pages, blocs, lignes)
- Liens prev/next
- Détection césure explicite (SUBS_TYPE + SUBS_CONTENT)
- Détection césure heuristique (dernier token en `-`)
- Liaison bidirectionnelle des paires

`test_hyphenation.py` :
- `enrich_chunk_lines` : PART1 reçoit `hyphen_join_with_next`, PART2 reçoit `hyphen_join_with_prev`
- `enrich_chunk_lines` : `logical_join_candidate` présent si `hyphen_subs_content` connu
- `reconcile_hyphen_pair` : textes non fusionnés, frontière physique préservée
- `reconcile_hyphen_pair` : source_explicit=True + subs_content connu → résolution avec confiance
- `reconcile_hyphen_pair` : source_explicit=False → mode conservateur, pas de SUBS_CONTENT
- `reconcile_hyphen_pair` : cas ambigu → retour des textes source
- `should_stay_in_same_chunk` : vrai pour PART1/PART2 liés, faux pour lignes normales

`test_rewriter.py` :
- Préservation TextLine ID/coords
- Tokenisation et géométrie proportionnelle (sum widths == TextLine.WIDTH)
- Reconstruction HYP sur PART1
- Reconstruction SUBS_TYPE/SUBS_CONTENT sur PART1 et PART2 (quand confiance suffisante)
- Pas de SUBS_CONTENT sur césure heuristique
- Round-trip (parse → rewrite sans correction → re-parse → mêmes IDs)

`test_chunk_planner.py` :
- Cas page, bloc, fenêtre, ligne
- Une paire PART1/PART2 n'est jamais séparée par une frontière de fenêtre
- Downgrade granularité

`test_validator.py` :
- Réponse valide
- Missing/doublon/inconnu line_id
- Newline dans text
- `hyphen_integrity_violation` : PART2 vide ou PART1 contient tout le mot

**Integration tests :**
- Upload XML simple → job → download ALTO valide
- Upload ZIP → extraction → job
- Document avec paires de césure → ALTO de sortie avec HYP/SUBS_* corrects
- Fallback JSON invalide → retry → downgrade

---

## SPRINTS DE DÉVELOPPEMENT

### Vue d'ensemble des sprints

| Sprint | Nom | Durée est. | Dépend de |
|--------|-----|-----------|-----------|
| 0 | Bootstrap & infrastructure | 1-2h | — |
| 1 | Schemas + Parser ALTO (avec détection césures) | 2-3h | Sprint 0 |
| 2 | Hyphenation Reconciler | 2-3h | Sprint 1 |
| 3 | Rewriter ALTO (avec HYP/SUBS_* ) | 2h | Sprint 1, 2 |
| 4 | Providers LLM | 2-3h | Sprint 1 |
| 5 | Chunk Planner + Validateur (hyphen-aware) | 2h | Sprint 1, 2 |
| 6 | Orchestrateur + Job Store | 2-3h | Sprint 2, 3, 4, 5 |
| 7 | Routes API FastAPI | 2h | Sprint 6 |
| 8 | Frontend React | 3-4h | Sprint 7 |
| 9 | Docker + HF Spaces | 1-2h | Sprint 8 |
| 10 | Tests d'intégration + polish | 2h | Sprint 9 |

```

## Décisions d'architecture clés à retenir

1. **Le LLM informe, l'app décide** : pour les césures, le LLM reçoit des métadonnées de contexte mais ne reconstruit jamais les frontières physiques lui-même.

2. **Trois niveaux de confiance pour SUBS_CONTENT** :
   - Source ALTO explicite (SUBS_TYPE + SUBS_CONTENT dans l'original) → confiance totale → écrire
   - Source ALTO partielle (HYP présent, SUBS_CONTENT absent) → confiance partielle → écrire si reconciler confirme
   - Heuristique (tiret terminal, sans marquage SUBS) → pas de confiance → ne pas écrire

3. **Les paires sont atomiques** : du parsing au chunk planner à l'orchestrateur au rewriter, une paire PART1/PART2 est toujours traitée ensemble. Jamais séparée.

4. **En cas de doute, conserver la source** : à chaque étape (reconciler, validator, orchestrator), le fallback ultime est de garder les textes OCR source. Un ALTO source intact vaut mieux qu'un ALTO inventé.
