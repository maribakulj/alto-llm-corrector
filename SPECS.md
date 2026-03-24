# SPECS

## Table des matières

| Fichier | Contenu |
|---------|---------|
| [SPECS.md](SPECS.md) | Vue d'ensemble, stack, arborescence, invariants |
| [SPECS_SCHEMAS.md](SPECS_SCHEMAS.md) | Modèles Pydantic (`schemas/__init__.py`) |
| [SPECS_ALTO.md](SPECS_ALTO.md) | Parser ALTO, Hyphenation Reconciler, Rewriter |
| [SPECS_PROVIDERS.md](SPECS_PROVIDERS.md) | Les 4 fournisseurs LLM + prompt système |
| [SPECS_JOBS.md](SPECS_JOBS.md) | Chunk Planner, Validateur, Orchestrateur |
| [SPECS_API.md](SPECS_API.md) | Routes FastAPI, SSE events, stockage |
| [SPECS_FRONTEND.md](SPECS_FRONTEND.md) | Composants React, règles UX |
| [SPECS_INFRA.md](SPECS_INFRA.md) | Docker, HF Spaces, sécurité |
| [SPECS_SPRINTS.md](SPECS_SPRINTS.md) | Sprints de développement, décisions d'architecture |

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
├── SPECS.md                      ← ce fichier (index)
├── CLAUDE.md
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
│       ├── test_hyphenation.py
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

## Invariants non négociables

1. **Le LLM informe, l'app décide** : pour les césures, le LLM reçoit des métadonnées de contexte mais ne reconstruit jamais les frontières physiques lui-même.

2. **Trois niveaux de confiance pour SUBS_CONTENT** :
   - Source ALTO explicite (SUBS_TYPE + SUBS_CONTENT dans l'original) → confiance totale → écrire
   - Source ALTO partielle (HYP présent, SUBS_CONTENT absent) → confiance partielle → écrire si reconciler confirme
   - Heuristique (tiret terminal, sans marquage SUBS) → pas de confiance → ne pas écrire

3. **Les paires sont atomiques** : du parsing au chunk planner à l'orchestrateur au rewriter, une paire PART1/PART2 est toujours traitée ensemble. Jamais séparée.

4. **En cas de doute, conserver la source** : à chaque étape (reconciler, validator, orchestrator), le fallback ultime est de garder les textes OCR source. Un ALTO source intact vaut mieux qu'un ALTO inventé.
