"""A deterministic multi-page ALTO builder, for structures nothing else builds.

``_alto_gen.py`` draws documents for the property suite; this builds one
exactly. It exists because two test files needed the same three-page and
empty-page fixtures and the hyphen-unit net (`tests/hyphenation/`) correctly
keeps them in separate directories — the chain test is about the hyphen unit,
the empty-page tests are not.

Nothing here imports ``saknussemm``: it is string construction, so a caller's
subject stays whatever the caller says it is.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v3#"'


def page(
    page_id: str,
    words: list[str],
    *,
    continues_from_previous: bool = False,
    continues_onto_next: bool = False,
) -> str:
    """One ``<Page>``, one block, one ``TextLine`` per word.

    ``continues_onto_next`` marks the last line ``HypPart1`` and appends the
    break mark to its text; ``continues_from_previous`` marks the first line
    ``HypPart2``. Set both on a middle page and it becomes the ``HypBoth``
    that links two seams.
    """
    lines = []
    for index, word in enumerate(words):
        subs, content = "", word
        if continues_onto_next and index == len(words) - 1:
            subs = f' SUBS_TYPE="HypPart1" SUBS_CONTENT="{word}suite"'
            content = f"{word}-"
        if continues_from_previous and index == 0:
            subs = ' SUBS_TYPE="HypPart2" SUBS_CONTENT="motsuite"'
        top = 10 + 50 * index
        lines.append(
            f'<TextLine ID="{page_id}_L{index}" HPOS="10" VPOS="{top}" '
            f'WIDTH="900" HEIGHT="40">'
            f'<String ID="{page_id}_S{index}" CONTENT="{content}" HPOS="10" '
            f'VPOS="{top}" WIDTH="300" HEIGHT="40"{subs}/></TextLine>'
        )
    return (
        f'<Page ID="{page_id}" WIDTH="1000" HEIGHT="1400"><PrintSpace>'
        f'<TextBlock ID="{page_id}_B" HPOS="0" VPOS="0" WIDTH="900" '
        f'HEIGHT="900">' + "".join(lines) + "</TextBlock></PrintSpace></Page>"
    )


def empty_page(page_id: str) -> str:
    """A page whose ``PrintSpace`` holds nothing — a blank verso."""
    return f'<Page ID="{page_id}" WIDTH="1000" HEIGHT="1400"><PrintSpace/></Page>'


def document(pages: list[str]) -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><alto {_NS}><Layout>'
        + "".join(pages)
        + "</Layout></alto>"
    ).encode()


def written(payload: bytes, name: str = "s.xml") -> Path:
    """*payload* on disk in a fresh directory, so a run can read it back."""
    path = Path(tempfile.mkdtemp()) / name
    path.write_bytes(payload)
    return path


#: Pages 1→2→3 linked by two seams, so the chain has three members on three
#: pages — the structure the whole suite never built (`max pages = 2`).
THREE_PAGE_CHAIN = document(
    [
        page("P1", ["alpha", "beta"], continues_onto_next=True),
        page("P2", ["gamma"], continues_from_previous=True, continues_onto_next=True),
        page("P3", ["delta", "epsilon"], continues_from_previous=True),
    ]
)
