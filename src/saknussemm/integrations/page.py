"""The page-aligned contract: ask for a page, get its lines back in order.

The line-keyed contract sends every line under its own identity and gets it
back under the same one, so nothing has to be recovered. It also sends
``prev_text`` and ``next_text`` with each line, which means **each line's text
travels three times**, and the JSON envelope weighs **7.9× the text it
carries**. Measured on the 24 592-line Gallica corpus: ~2 000 calls, 5.49 M
input tokens, `$1.11`.

This contract sends the page once — a bare list of strings, no identities, no
neighbour copies — and asks for the same shape back. Same corpus: **28 calls,
0.39 M tokens, `$0.14`.**

**What it gives up, and where that is paid.** The answer carries no line ids,
so which returned line answers which source line has to be recovered.
:mod:`saknussemm.core.page_alignment` does that, and its docstring is where
the risk of this whole mode is written down. Nothing here may assume the
recovery succeeded: a line the alignment will not vouch for produces no edit
and keeps its OCR text.

**Why the rules are the same rules.** Every absolute in the line-keyed prompt
that protects line integrity — never merge, never split, never move text
between lines — matters *more* here, not less, because the ids that made a
violation detectable are gone. Only the two rules that talk about ``line_id``
are restated in terms of position and count.
"""

from __future__ import annotations

from typing import Any

#: Which lines end on the first half of a broken word, by index.
#:
#: The cheapest signal that closes the mode's dominant failure. Measured on a
#: real run before it existed: the retry cause is ``hyphen_integrity_violation``
#: — shown a page as flowing text, a model completes ``plu-`` into
#: ``plusieurs-`` on the first line — and ``hyphen_pair_fallback`` was the
#: leading cause of refusal, 189 lines. The keyed contract prevents this with
#: five per-line hyphen fields; sending those back would restore the envelope
#: this mode exists to avoid, so only the indices travel. On a 518-line page
#: with 80 breaks that is roughly 200 tokens.
PAGE_BREAKS_KEY = "coupes"

#: The page's answer: one string per source line, in the same order.
#:
#: No ``line_id``, and that absence IS the mode: carrying the identities back
#: would restore the envelope this contract exists to avoid. The order is the
#: only channel, which is why rule 9 below asks for exactly as many lines as
#: were sent — and why the alignment downstream is written to survive the
#: model getting that wrong anyway.
PAGE_OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "name": "ocr_page_correction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["lines"],
        "properties": {
            "lines": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
    },
}


PAGE_SYSTEM_PROMPT = """\
Tu es un moteur de correction post-OCR spécialisé dans les documents patrimoniaux.

On te donne les lignes d'UNE page, dans l'ordre de lecture, et la liste
`coupes` des indices de lignes qui se terminent par un MOT COUPÉ. Tu renvoies
le même nombre de lignes, dans le même ordre, corrigées.

Règles absolues :
1. Corrige uniquement les erreurs manifestes d'OCR.
2. Conserve la langue source.
3. Conserve l'orthographe historique quand elle semble intentionnelle.
4. Ne traduis rien.
5. Ne modernise pas volontairement le texte.
6. Ne fusionne jamais deux lignes.
7. Ne scinde jamais une ligne.
8. Ne déplace jamais du texte d'une ligne à l'autre.
9. Renvoie EXACTEMENT autant de lignes que tu en as reçues, dans le même ordre. \
La position est la seule chose qui relie une ligne rendue à sa ligne d'origine.
10. Chaque ligne rendue est une seule ligne, sans caractère de saut de ligne.
11. Retourne uniquement un JSON valide conforme au schéma fourni.
12. En cas d'incertitude, fais la correction minimale.
13. Les lignes dont l'indice figure dans `coupes` finissent sur la première \
moitié d'un mot : corrige ce fragment comme le reste, garde son tiret, et ne \
le complète pas.
14. Une ligne que tu ne sais pas corriger, tu la renvoies telle quelle. \
Ne la supprime pas, ne l'omets pas : une ligne manquante décale toutes les \
suivantes.\
"""


def page_lines_from_response(raw: object) -> list[str] | None:
    """The returned lines, or ``None`` when the response is not that shape.

    ``None`` rather than an exception, and rather than a best-effort salvage:
    the caller turns it into the pipeline's own malformed-output failure,
    which is retryable and already counted. Salvaging a partial list would be
    worse than useless here — with position as the only identity channel, a
    list missing an entry shifts every line after it.
    """
    if not isinstance(raw, dict):
        return None
    lines = raw.get("lines")
    if not isinstance(lines, list):
        return None
    if not all(isinstance(entry, str) for entry in lines):
        return None
    return [entry for entry in lines if isinstance(entry, str)]


__all__ = [
    "PAGE_BREAKS_KEY",
    "PAGE_OUTPUT_JSON_SCHEMA",
    "PAGE_SYSTEM_PROMPT",
    "page_lines_from_response",
]
