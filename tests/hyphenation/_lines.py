"""The line builder every hyphenation test needs.

One ``LineManifest`` with plausible geometry and the hyphen fields
exposed as keywords. This is the copy that sat — character for character,
twice — at the top of two of the three wave-named files, all three of
which are now dissolved into the invariants they were about.
"""

from __future__ import annotations

from saknussemm.core.schemas import Coords, HyphenRole, LineManifest


def _line(
    line_id: str,
    ocr: str,
    *,
    page_id: str = "p1",
    block_id: str = "b1",
    role: HyphenRole = HyphenRole.NONE,
    subs: str | None = None,
    explicit: bool = False,
) -> LineManifest:
    return LineManifest(
        line_id=line_id,
        page_id=page_id,
        block_id=block_id,
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=100, height=20),
        ocr_text=ocr,
        hyphen_role=role,
        hyphen_subs_content=subs,
        hyphen_source_explicit=explicit,
    )
