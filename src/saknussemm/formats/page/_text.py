"""Canonical text reconstruction for PAGE ``TextLine`` / ``Word`` elements.

Implements the P2/P3 rules of spec 6.2:

  - **P3** — the *canonical* ``TextEquiv`` of an element is the one with the
    smallest ``@index`` (an absent ``@index`` counts as 0). Alternatives
    describe competing readings and are not the line's text.
  - **P2** — a line's canonical text is its canonical ``TextEquiv/Unicode``
    (NFC + strip). When the line carries no direct ``TextEquiv`` (the
    Transkribus "corrected" export puts the whole line in a single Word),
    fall back to the space-joined canonical ``Unicode`` of its ``Word``
    children.

Both parser and rewriter reconstruct through these helpers so the text
they compare is derived identically.
"""

from __future__ import annotations

from lxml import etree

from saknussemm.core._norm import nfc
from saknussemm.core._parse import parse_int_tolerant
from saknussemm.formats.page._ns import _tag


def _index_of(te: etree._Element) -> int:
    """The ``@index`` of a TextEquiv, defaulting to 0 when absent/blank.

    A blank, float-shaped, or non-integer index defaults to 0 rather than
    aborting the file — the shared tolerant policy the ALTO backend applies
    to malformed attributes (previously this used ``int(raw)`` and so
    aborted a float-valued ``@index`` to 0 where ALTO truncated it).
    """
    return parse_int_tolerant(te.get("index"), 0)


def _direct_children(el: etree._Element, local: str, ns: str) -> list[etree._Element]:
    """Direct element children of ``el`` with the given local tag.

    Restricted to DIRECT children so selecting a line's ``TextEquiv`` never
    reaches into a nested ``Word``'s ``TextEquiv``. Comments/PIs (callable
    ``.tag``) are skipped.
    """
    want = _tag(local, ns)
    return [c for c in el if c.tag == want]


def canonical_textequiv(el: etree._Element, ns: str) -> etree._Element | None:
    """Return ``el``'s canonical (minimal ``@index``) direct TextEquiv (P3)."""
    equivs = _direct_children(el, "TextEquiv", ns)
    if not equivs:
        return None
    return min(equivs, key=_index_of)


def _unicode_text(te: etree._Element | None, ns: str, *, verbatim: bool = False) -> str:
    """The ``Unicode`` text of a TextEquiv (NFC), or '' when missing.

    ``verbatim=True`` returns the codepoints the FILE carries, without the
    NFC pass — see :func:`canonical_line_text`.
    """
    if te is None:
        return ""
    uni = te.find(_tag("Unicode", ns))
    if uni is None or uni.text is None:
        return ""
    return uni.text if verbatim else nfc(uni.text)


def word_text(word: etree._Element, ns: str, *, verbatim: bool = False) -> str:
    """Canonical text of a single ``Word`` (NFC, not stripped)."""
    return _unicode_text(canonical_textequiv(word, ns), ns, verbatim=verbatim)


def word_texts(
    textline: etree._Element, ns: str, *, verbatim: bool = False
) -> list[str]:
    """Canonical text of each ``Word`` child, in document order."""
    return [
        word_text(w, ns, verbatim=verbatim)
        for w in _direct_children(textline, "Word", ns)
    ]


def canonical_line_text(
    textline: etree._Element, ns: str, *, verbatim: bool = False
) -> str:
    """Build a line's logical text (P2): NFC + strip.

        Line-level canonical ``TextEquiv`` wins; otherwise the space-joined
        canonical ``Unicode`` of the ``Word`` children.

        ``verbatim=True`` is the same walk with the NFC pass OFF: what the
        file's codepoints say, rather than the logical reading of them. The two
        differ whenever the source is decomposed — ``e`` + U+0301 in the file
        against U+00E9 in the decision — and the fidelity scale needs both to
        tell ``exact`` from ``source_spelling``.

    It was long held that PAGE substituted nothing on read, so a second
        reading would be pointless. NFC *is* a substitution: a run over a
        decomposed document reported every line as ``exact`` while the file
        spelled several of them otherwise. ALTO carries the same second
        reading, for the same reason and since longer.
    """
    line_equiv = canonical_textequiv(textline, ns)
    if line_equiv is not None:
        return (
            _unicode_text(line_equiv, ns, verbatim=verbatim).replace("\r", "").strip()
        )
    words = [w for w in word_texts(textline, ns, verbatim=verbatim) if w]
    joined = " ".join(words)
    return (joined if verbatim else nfc(joined)).replace("\r", "").strip()


def line_has_direct_textequiv(textline: etree._Element, ns: str) -> bool:
    """True when the line carries its own (line-level) TextEquiv."""
    return bool(_direct_children(textline, "TextEquiv", ns))


def word_concat_text(textline: etree._Element, ns: str) -> str:
    """Space-joined canonical Word text (NFC + strip) — the P2 fallback form.

    Exposed so the rewriter/report can detect a line-vs-words disagreement
    (P2: the line text wins, the divergence is counted).
    """
    words = [w for w in word_texts(textline, ns) if w]
    return nfc(" ".join(words)).replace("\r", "").strip()


__all__ = [
    "canonical_textequiv",
    "canonical_line_text",
    "line_has_direct_textequiv",
    "word_text",
    "word_texts",
    "word_concat_text",
]
