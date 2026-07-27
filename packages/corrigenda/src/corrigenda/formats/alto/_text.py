"""Shared text reconstruction for ALTO TextLine elements.

Both the parser (building ``LineManifest.ocr_text``) and the rewriter
(comparing the source XML against corrected text on the UNTOUCHED path)
walk a TextLine's String/SP/HYP children and produce the same logical
string. Centralising the logic prevents the two from drifting apart —
the very bug the rewriter docstring used to document.

The function returned here is the raw, NFC-normalised reconstruction.
Callers that want the "logical" form (parser-side ocr_text) wrap with
``.replace("\\r", "").strip()`` on top.
"""

from __future__ import annotations

from lxml import etree

from corrigenda.core._norm import nfc
from corrigenda.core.pairing import HYPHEN_CHARS
from corrigenda.formats.alto._ns import _tag

#: Marks that count as "the String already rendered the break", so a
#: following ``<HYP>`` must not add a second one.
#:
#: This is :data:`HYPHEN_CHARS` **minus U+00AD**, and the exclusion is
#: deliberate rather than an oversight. A soft hyphen is collapsed to
#: ``"-"`` on the way into the logical text — the same normalisation
#: :func:`corrigenda.core._norm.clean_content` applies on the way out,
#: for the same reason: it is a hyphen *variant* that must not reach an
#: ALTO CONTENT attribute, and the hyphenation layer reconstructs it
#: from manifest state instead. 115 lines of ``examples/X0000002.xml``
#: depend on it: they carry the break mark in the ``<HYP>`` alone, as
#: U+00AD, and the collapse is what makes them pair at all. The bytes
#: keep the source character regardless — the rewrite paths re-emit the
#: original HYP element with its own CONTENT.
#:
#: Admitting U+00AD here would make ``String "Ober­"`` + ``HYP``
#: read back as ``Ober­``, putting a soft hyphen into ``ocr_text``
#: that the round-trip then cannot carry.
_DEDUP_MARKS: tuple[str, ...] = tuple(c for c in HYPHEN_CHARS if c != "­")


def reconstruct_textline(textline: etree._Element, ns: str) -> str:
    """Walk a TextLine's String/SP/HYP children and rebuild its text.

    Rules:
      - ``String`` contributes its CONTENT attribute verbatim.
      - ``SP`` contributes a single space.
      - ``HYP`` contributes its CONTENT (defaulting to ``"-"``), with
        U+00AD collapsed to ``"-"``. It is skipped when the accumulated
        text already ends in a word-break mark: a producer that writes
        the mark into the String CONTENT *and* emits a HYP means one
        mark rendered once, not two.

    That skip used to test ``endswith("-")`` — the ASCII hyphen alone —
    so every other mark in the repertoire doubled: ``Ober⸗`` + ``HYP
    "⸗"`` read back as ``Ober⸗⸗``, ``Ober¬`` as ``Ober¬¬``. Silent,
    because this function feeds BOTH sides of the projection invariant
    (the parser's ``ocr_text`` and the rewriter's UNTOUCHED comparison):
    a mistake here is made identically on both sides and compares equal
    to itself. The Fraktur ``⸗`` is 24 of the 94 break marks in
    ``corpus/37-GT-BNL``, so this was not a corner case.

    The U+00AD collapse is deliberate and stays — see
    :data:`_DEDUP_MARKS`.

    Returns NFC-normalised text. Does NOT strip or remove carriage
    returns — those are parser-specific concerns.
    """
    string_tag = _tag("String", ns)
    sp_tag = _tag("SP", ns)
    hyp_tag = _tag("HYP", ns)
    parts: list[str] = []
    for child in textline:
        if child.tag == string_tag:
            parts.append(child.get("CONTENT", ""))
        elif child.tag == sp_tag:
            parts.append(" ")
        elif child.tag == hyp_tag:
            hyp_char = child.get("CONTENT", "-")
            if hyp_char == "­":
                hyp_char = "-"
            if hyp_char and not "".join(parts).endswith(_DEDUP_MARKS):
                parts.append(hyp_char)
    return nfc("".join(parts))
