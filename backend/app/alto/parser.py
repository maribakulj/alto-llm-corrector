from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Optional

from lxml import etree

from app.schemas import (
    BlockManifest,
    Coords,
    DocumentManifest,
    HyphenRole,
    LineManifest,
    PageManifest,
)

# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------

_KNOWN_NS = {
    "v2": "http://schema.ccs-gmbh.com/ALTO",
    "v3": "http://www.loc.gov/standards/alto/ns-v3#",
    "v4": "http://www.loc.gov/standards/alto/ns-v4#",
}


def _detect_namespace(root: etree._Element) -> str:
    """Return the namespace URI found in the root tag, or '' if none."""
    tag = root.tag
    if tag.startswith("{"):
        return tag[1: tag.index("}")]
    return ""


def _tag(local: str, ns: str) -> str:
    return f"{{{ns}}}{local}" if ns else local


# ---------------------------------------------------------------------------
# ocr_text reconstruction
# ---------------------------------------------------------------------------

def _build_ocr_text(textline: etree._Element, ns: str) -> str:
    parts: list[str] = []
    for child in textline:
        local = etree.QName(child.tag).localname
        if local == "String":
            parts.append(child.get("CONTENT", ""))
        elif local == "SP":
            parts.append(" ")
        elif local == "HYP":
            parts.append(child.get("CONTENT", "-"))
    text = "".join(parts)
    text = text.replace("\r", "")
    text = unicodedata.normalize("NFC", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Hyphenation detection (mutates lines in-place)
# ---------------------------------------------------------------------------

def _detect_hyphenation(lines: list[LineManifest]) -> None:
    """
    First pass: annotate each line individually based on its XML content.
    Second pass: link PART1 → PART2 pairs and propagate SUBS_CONTENT.

    This function works with a list of LineManifest whose `ocr_text` is
    already built. The raw XML scan results are stored as temporary
    attributes on the objects so that the second pass can use them.
    """
    # Nothing to do for empty lists
    if not lines:
        return

    # We need the raw XML elements to inspect attributes — but LineManifest
    # is a pure data object. Strategy: re-annotate using the ocr_text and
    # flags that the parsing loop already stored on the manifest objects via
    # _parse_textline_hyphen_info. We call that helper during parse_alto_file
    # so by the time we reach _detect_hyphenation the hyphen fields may already
    # be partially filled. Here we only do the second-pass linking.
    _link_hyphen_pairs(lines)


def _link_hyphen_pairs(lines: list[LineManifest]) -> None:
    """
    Second pass: for every line already marked PART1, link to the next line
    as PART2, and propagate SUBS_CONTENT bidirectionally.
    """
    for i, line in enumerate(lines):
        if line.hyphen_role != HyphenRole.PART1:
            continue
        if i + 1 >= len(lines):
            continue

        candidate = lines[i + 1]

        # Accept explicit PART2 or heuristic candidate (NONE with trailing dash
        # already cleared to PART2 in first pass, or still NONE for heuristic
        # cases where the next line is a plain continuation).
        if candidate.hyphen_role not in (HyphenRole.PART2, HyphenRole.NONE):
            continue

        # Mark the candidate as PART2 if it isn't already
        if candidate.hyphen_role == HyphenRole.NONE:
            candidate.hyphen_role = HyphenRole.PART2
            candidate.hyphen_source_explicit = line.hyphen_source_explicit

        # Bidirectional link
        line.hyphen_pair_line_id = candidate.line_id
        candidate.hyphen_pair_line_id = line.line_id

        # Propagate SUBS_CONTENT
        subs = line.hyphen_subs_content or candidate.hyphen_subs_content
        if subs:
            line.hyphen_subs_content = subs
            candidate.hyphen_subs_content = subs


def _parse_textline_hyphen_info(
    textline: etree._Element,
    ns: str,
    line: LineManifest,
) -> None:
    """
    First-pass hyphenation scan for a single TextLine.
    Fills hyphen_role / hyphen_source_explicit / hyphen_subs_content
    directly on the LineManifest.
    """
    children = list(textline)
    if not children:
        return

    string_tag = _tag("String", ns)
    hyp_tag = _tag("HYP", ns)

    # --- Detect PART2: first String has SUBS_TYPE="HypPart2" ---
    first_string = next(
        (c for c in children if c.tag == string_tag), None
    )
    if first_string is not None:
        subs_type = first_string.get("SUBS_TYPE", "")
        if subs_type == "HypPart2":
            line.hyphen_role = HyphenRole.PART2
            line.hyphen_source_explicit = True
            subs_content = first_string.get("SUBS_CONTENT")
            if subs_content:
                line.hyphen_subs_content = subs_content
            return  # done for PART2

    # --- Detect PART1: last meaningful element is HYP, or last String has
    #     SUBS_TYPE="HypPart1" ---

    # Check for trailing HYP element
    last_child = children[-1]
    if etree.QName(last_child.tag).localname == "HYP":
        line.hyphen_role = HyphenRole.PART1
        line.hyphen_source_explicit = True
        # Try to get SUBS_CONTENT from the String just before HYP
        prev_strings = [c for c in children if c.tag == string_tag]
        if prev_strings:
            subs_content = prev_strings[-1].get("SUBS_CONTENT")
            if subs_content:
                line.hyphen_subs_content = subs_content
        return

    # Check last String for SUBS_TYPE="HypPart1"
    last_string = next(
        (c for c in reversed(children) if c.tag == string_tag), None
    )
    if last_string is not None:
        subs_type = last_string.get("SUBS_TYPE", "")
        if subs_type == "HypPart1":
            line.hyphen_role = HyphenRole.PART1
            line.hyphen_source_explicit = True
            subs_content = last_string.get("SUBS_CONTENT")
            if subs_content:
                line.hyphen_subs_content = subs_content
            return

    # --- Heuristic: last non-space token ends with "-" ---
    tokens = line.ocr_text.split()
    if tokens and tokens[-1].endswith("-"):
        line.hyphen_role = HyphenRole.PART1
        line.hyphen_source_explicit = False


# ---------------------------------------------------------------------------
# Core parsing
# ---------------------------------------------------------------------------

def parse_alto_file(
    xml_path: Path,
    source_name: str,
    page_index_offset: int = 0,
    global_line_offset: int = 0,
) -> tuple[list[PageManifest], etree._Element]:
    """
    Parse one ALTO XML file and return (list_of_PageManifest, root_element).
    """
    tree = etree.parse(str(xml_path))
    root = tree.getroot()
    ns = _detect_namespace(root)

    pages: list[PageManifest] = []
    global_line_idx = global_line_offset

    layout = root.find(_tag("Layout", ns))
    if layout is None:
        return pages, root

    for page_idx, page_el in enumerate(layout.findall(_tag("Page", ns))):
        page_id = page_el.get("ID", f"PAGE_{page_index_offset + page_idx}")
        page_width = int(page_el.get("WIDTH", 0))
        page_height = int(page_el.get("HEIGHT", 0))

        blocks: list[BlockManifest] = []
        lines: list[LineManifest] = []

        printspace = page_el.find(_tag("PrintSpace", ns))
        container = printspace if printspace is not None else page_el

        block_order = 0
        for tb in container.findall(_tag("TextBlock", ns)):
            block_id = tb.get("ID", f"TB_{page_id}_{block_order}")
            block_coords = Coords(
                hpos=int(tb.get("HPOS", 0)),
                vpos=int(tb.get("VPOS", 0)),
                width=int(tb.get("WIDTH", 0)),
                height=int(tb.get("HEIGHT", 0)),
            )
            line_ids: list[str] = []
            line_order_in_block = 0

            for tl in tb.findall(_tag("TextLine", ns)):
                line_id = tl.get("ID", f"TL_{block_id}_{line_order_in_block}")
                coords = Coords(
                    hpos=int(tl.get("HPOS", 0)),
                    vpos=int(tl.get("VPOS", 0)),
                    width=int(tl.get("WIDTH", 0)),
                    height=int(tl.get("HEIGHT", 0)),
                )
                ocr_text = _build_ocr_text(tl, ns)

                lm = LineManifest(
                    line_id=line_id,
                    page_id=page_id,
                    block_id=block_id,
                    line_order_global=global_line_idx,
                    line_order_in_block=line_order_in_block,
                    coords=coords,
                    ocr_text=ocr_text,
                )

                # First-pass hyphenation scan
                _parse_textline_hyphen_info(tl, ns, lm)

                lines.append(lm)
                line_ids.append(line_id)
                line_order_in_block += 1
                global_line_idx += 1

            blocks.append(
                BlockManifest(
                    block_id=block_id,
                    page_id=page_id,
                    block_order=block_order,
                    coords=block_coords,
                    line_ids=line_ids,
                )
            )
            block_order += 1

        # Link prev/next
        for i, lm in enumerate(lines):
            if i > 0:
                lm.prev_line_id = lines[i - 1].line_id
            if i < len(lines) - 1:
                lm.next_line_id = lines[i + 1].line_id

        # Second-pass: link hyphen pairs
        _link_hyphen_pairs(lines)

        pages.append(
            PageManifest(
                page_id=page_id,
                source_file=source_name,
                page_index=page_index_offset + page_idx,
                page_width=page_width,
                page_height=page_height,
                blocks=blocks,
                lines=lines,
            )
        )

    return pages, root


def build_document_manifest(
    files: list[tuple[Path, str]],
) -> DocumentManifest:
    """
    Build a DocumentManifest from a list of (xml_path, source_name) tuples.
    Files are processed in order; page/line indices are continuous.
    """
    all_pages: list[PageManifest] = []
    source_files: list[str] = []
    page_offset = 0
    line_offset = 0

    for xml_path, source_name in files:
        source_files.append(source_name)
        pages, _ = parse_alto_file(xml_path, source_name, page_offset, line_offset)
        all_pages.extend(pages)
        page_offset += len(pages)
        for p in pages:
            line_offset += len(p.lines)

    total_blocks = sum(len(p.blocks) for p in all_pages)
    total_lines = sum(len(p.lines) for p in all_pages)

    return DocumentManifest(
        source_files=source_files,
        pages=all_pages,
        total_pages=len(all_pages),
        total_blocks=total_blocks,
        total_lines=total_lines,
    )
