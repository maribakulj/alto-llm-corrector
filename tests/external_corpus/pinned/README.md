# Pinned offline corpus (blocking tier)

Real Gallica ALTO pages committed to the repository so a small,
immutable slice of the external corpus runs in the DEFAULT test suite —
offline, on every merge, with no `external_corpus` marker and no
self-skip. The fetched `.cache/` tier stays non-blocking; this tier is
the guarantee that at least some never-seen-in-development OCR output
gates every change.

## Populating (maintainer, deliberate act)

1. Run `python tests/external_corpus/fetch.py` on a machine with
   Gallica access and let it print/verify the SHA-256 pins.
2. Copy 2–3 representative pages from `.cache/` into this directory —
   at least one multi-column periodical page and one monography page.
   Keep the `<ark>_p<NNNN>.alto.xml` names.
3. Record each file below (ark, page, sha256, fetch date). Source:
   gallica.bnf.fr / Bibliothèque nationale de France — public-domain
   documents; keep this attribution.
4. Never replace a pinned file silently: a re-pin is a reviewed change
   explaining why (e.g. legitimate Gallica re-OCR).

The dev corpus (`examples/`, ark bpt6k3265015q) must NEVER appear here —
this tier only means something if the code was written blind to it.

## Contents

Peuplé le **2026-08-16**, par les étapes ci-dessus. Les trois empreintes
étaient déjà épinglées dans `manifest.json` et le téléchargement les a
vérifiées sans dérive — ces octets sont ceux que Gallica servait quand le
manifeste a été écrit.

| file | sha256 | fetched | ce qu'il apporte |
|---|---|---|---|
| `bpt6k2324031_p0002.alto.xml` | `a160be6df2b99ed276d99d84ab27ad6c58b67c66b084d4d7c8b1ee3f9385c60a` | 2026-08-16 | *Le Temps*, 1ᵉʳ janvier 1890 — **quotidien multi-colonnes**, 1,7 Mo : la mise en page la plus dure du lot |
| `bpt6k6478860m_p0009.alto.xml` | `b94bee2447dbf8a4e364710ba129d67630192e786fbba3715a4e539d9964c8f4` | 2026-08-16 | Daremberg, *Périodes de l'histoire de la médecine*, 1850 — monographie en **mode texte** |
| `bpt6k2206225_p0015.alto.xml` | `5d8b0173e38366e941490a99186bd50c9b414ac835c6614f632f930420b37951` | 2026-08-16 | Teulières, *Histoire naturelle*, 1850 — monographie, bloc de texte plein |

**1,89 Mo au total**, pour trois pages, deux époques et deux mises en page.
C'est le prix d'une porte qui bloque réellement — avant ce peuplement,
`continue-on-error` sur le tier téléchargé faisait qu'**aucune page externe
ne bloquait un merge**, ce que le plan comptait comme un critère de la
`1.0` non tenu.

Le tier téléchargé **reste non bloquant**, et c'est délibéré : il dépend de
la disponibilité de gallica.bnf.fr, et une panne de réseau ne doit pas
arrêter un merge. Les deux tiers ne jouent pas le même rôle — celui-ci
garantit un plancher hors ligne, celui-là élargit la couverture quand il
peut.
