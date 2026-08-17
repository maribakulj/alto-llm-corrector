"""Hypothesis strategy for RICH generated ALTO documents.

``test_properties_hypothesis.alto_documents`` generates single-page
documents with non-overlapping simple pairs — deliberately minimal.
This strategy covers the structures the hyphenation machinery actually
has to survive (the plan's P3.2 gate):

- **chains**: PART1 → BOTH → PART2 across three consecutive lines (the
  middle line completes the previous word AND starts the next one);
- **multi-page files** with an optional explicit **cross-page pair** at
  each page seam (last line of page N is PART1, first line of page N+1
  is PART2, both sides carrying the SAME SUBS_CONTENT);
- ordinary pairs and plain lines interleaved with the above.

All hyphenation is EXPLICIT (SUBS_TYPE/SUBS_CONTENT + HYP): the words
are random letters, so heuristic trailing-dash detection — which is
geometry-vetted — would fire nondeterministically and hide structural
bugs behind pairing noise.
"""

from __future__ import annotations

from hypothesis import strategies as st

from saknussemm.core.pairing import HYPHEN_CHARS

#: An alphabet weighted like the text this library actually corrects, rather
#: than uniform over 442 codepoints. Measured 2026-08-17 on the uniform
#: version: **1,7 % of generated characters were ``e``, ``a`` or ``o``** and
#: only 18,6 % were ASCII at all — so ``test_metamorphic``'s producer, whose
#: rules are exactly those three letters, corrected nothing in **65 % of
#: generated documents**. The invariance property it carries then compared an
#: identity run to an identity run across three partitions: it held because
#: nothing was produced, not because the seam handling was right.
#:
#: French letter frequency, with the frequent half repeated so it dominates;
#: the accents a heritage corpus carries; and a few exotics so the fuzz value
#: of a wide alphabet survives. Still no ``-``: the trailing-mark heuristic
#: must not fire by accident, explicit ``SUBS_*`` marks every pair.
_ALPHABET = (
    "esaitnrulodcpmvqfbghjxyzwk"
    "esaitnrulodcpm"
    "ESAITNRULODCPMVQFBGHJXYZWK"
    "\u00e9\u00e8\u00ea\u00e0\u00e7\u00f9\u00f4\u00ee\u00e2\u00fb\u00eb\u00ef"
    "\u00fc\u00f6\u00e4\u00f1\u00e3\u00f5\u00e5\u00f8\u00e6\u0153\u00df\u00ff"
    "\u0183\u0140\u017f\u0111\u0133"
)
_WORD = st.text(alphabet=st.sampled_from(_ALPHABET), min_size=1, max_size=8)

#: Per-line hyphen role within a generated structure.
PLAIN = "plain"
PART1 = "part1"
BOTH = "both"
PART2 = "part2"


@st.composite
def _page_roles(draw: st.DrawFn, n_lines: int) -> list[str]:
    """Assign non-overlapping structures (plain / pair / chain) to lines."""
    roles = [PLAIN] * n_lines
    i = 0
    while i < n_lines:
        if i + 2 < n_lines and draw(st.booleans()) and draw(st.booleans()):
            roles[i], roles[i + 1], roles[i + 2] = PART1, BOTH, PART2
            i += 3
        elif i + 1 < n_lines and draw(st.booleans()):
            roles[i], roles[i + 1] = PART1, PART2
            i += 2
        else:
            i += 1
    return roles


@st.composite
def rich_alto_documents(draw: st.DrawFn) -> tuple[str, dict[str, str]]:
    """A 1–2 page explicit-hyphenation ALTO v3 document with chains and
    optional cross-page pairs.

    Returns ``(xml, expected_roles)`` where ``expected_roles`` maps each
    generated ``TextLine`` id to its intended role (``plain`` / ``part1``
    / ``both`` / ``part2`` / ``seam1`` / ``seam2``) so a property can
    verify the parser recognises exactly what the generator encoded —
    a silent encoding drift would otherwise turn every downstream
    property vacuous."""
    # One mark per document, because one OCR engine has one convention —
    # and because the generators emitted the ASCII hyphen and nothing else.
    # Measured 2026-08-17 over 200 draws: 166 documents carried `-`, zero
    # carried any of the other five. Every property that touches
    # hyphenation therefore ran on one sixth of the repertoire, while the
    # repository's own corpus marks EVERY break with `¬` and the bench's
    # Fraktur ground truth uses `⸗`.
    break_mark = draw(st.sampled_from(HYPHEN_CHARS))
    n_pages = draw(st.integers(1, 2))
    seam_pair = n_pages == 2 and draw(st.booleans())

    # ---- pass 1: draw every page's roles and words --------------------
    # When a seam pair was drawn, the seam positions (page 1's last line,
    # page 2's first line) are RESERVED: intra-page structures are drawn
    # over the remaining lines only, so the seam is never silently
    # cancelled by a colliding chain — cross-page coverage stays dense
    # instead of the ~3% a collision-tolerant draw yields.
    page_roles: list[list[str]] = []
    page_words: list[list[list[str]]] = []
    for page_idx in range(n_pages):
        n_lines = draw(st.integers(2, 5))
        reserve_tail = seam_pair and page_idx == 0
        reserve_head = seam_pair and page_idx == 1
        free = n_lines - int(reserve_tail) - int(reserve_head)
        roles = draw(_page_roles(free))
        if reserve_head:
            roles.insert(0, "seam2")
        if reserve_tail:
            roles.append("seam1")
        words = [
            draw(st.lists(_WORD, min_size=2 if r == BOTH else 1, max_size=4))
            for r in roles
        ]
        page_roles.append(roles)
        page_words.append(words)

    seam_subs = page_words[0][-1][-1] + page_words[1][0][0] if seam_pair else ""

    # ---- pass 2: render ------------------------------------------------
    pages_xml: list[str] = []
    expected_roles: dict[str, str] = {}
    line_no = 0
    string_no = 0
    for page_idx in range(n_pages):
        roles, words_per_line = page_roles[page_idx], page_words[page_idx]
        lines_xml: list[str] = []
        for li, (role, words) in enumerate(zip(roles, words_per_line)):
            expected_roles[f"L{line_no}"] = role
            vpos = 10 + 30 * li
            strings: list[str] = []
            hyp = ""
            for wi, w in enumerate(words):
                attrs = (
                    f'ID="S{string_no}" CONTENT="{w}" '
                    f'HPOS="{10 + 90 * wi}" VPOS="{vpos}" WIDTH="80" HEIGHT="20"'
                )
                string_no += 1
                is_first, is_last = wi == 0, wi == len(words) - 1

                if is_last and role in (PART1, BOTH, "seam1"):
                    joined = (
                        seam_subs if role == "seam1" else w + words_per_line[li + 1][0]
                    )
                    attrs += f' SUBS_TYPE="HypPart1" SUBS_CONTENT="{joined}"'
                    hyp = f'<HYP CONTENT="{break_mark}"/>'
                if is_first and role in (PART2, BOTH, "seam2"):
                    joined = (
                        seam_subs if role == "seam2" else words_per_line[li - 1][-1] + w
                    )
                    attrs += f' SUBS_TYPE="HypPart2" SUBS_CONTENT="{joined}"'
                strings.append(f"<String {attrs}/>")
            lines_xml.append(
                f'<TextLine ID="L{line_no}" HPOS="10" VPOS="{vpos}" '
                f'WIDTH="900" HEIGHT="20">{"".join(strings)}{hyp}</TextLine>'
            )
            line_no += 1

        pages_xml.append(
            f'<Page ID="P{page_idx + 1}" WIDTH="1000" HEIGHT="1000">'
            f'<PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">'
            f'<TextBlock ID="B{page_idx + 1}" HPOS="0" VPOS="0" WIDTH="1000" '
            f'HEIGHT="900">{"".join(lines_xml)}</TextBlock>'
            f"</PrintSpace></Page>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"><Layout>'
        f"{''.join(pages_xml)}"
        "</Layout></alto>"
    )
    return xml, expected_roles
