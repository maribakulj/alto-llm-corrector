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
            # Normalize: HYP contributes a single "-" to the logical text.
            # Avoid double-dash when preceding String CONTENT already ends
            # with a hyphen, and normalize soft-hyphen (\xad) to "-".
            hyp_char = child.get("CONTENT", "-")
            if hyp_char == "\u00ad":
                hyp_char = "-"
            # Skip if the accumulated text already ends with a dash
            current = "".join(parts)
            if current.endswith("-"):
                continue
            parts.append(hyp_char)
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
    Second pass: link PART1/BOTH lines to their forward partners.

    A line with role PART1 or BOTH has a forward PART1 relationship.
    The next line is linked as PART2/BOTH (backward side).

    For PART1:  pair_line_id = forward partner, subs_content = pair subs
    For BOTH:   forward_pair_id = forward partner, forward_subs_content = pair subs
                (backward fields were already set by a previous iteration)
    """
    for i, line in enumerate(lines):
        # Skip lines that don't have a forward (PART1) role
        if line.hyphen_role not in (HyphenRole.PART1, HyphenRole.BOTH):
            continue
        if i + 1 >= len(lines):
            continue

        candidate = lines[i + 1]

        # Accept PART2, BOTH, or NONE as forward partner
        if candidate.hyphen_role not in (
            HyphenRole.PART2, HyphenRole.BOTH, HyphenRole.NONE,
        ):
            continue

        # Mark NONE candidate as PART2
        if candidate.hyphen_role == HyphenRole.NONE:
            if line.hyphen_role == HyphenRole.BOTH:
                candidate.hyphen_role = HyphenRole.PART2
                candidate.hyphen_source_explicit = line.hyphen_forward_explicit
            else:
                candidate.hyphen_role = HyphenRole.PART2
                candidate.hyphen_source_explicit = line.hyphen_source_explicit

        # Determine subs_content for this pair
        if line.hyphen_role == HyphenRole.BOTH:
            # Forward side of a BOTH line
            subs = line.hyphen_forward_subs_content
            if not subs and candidate.hyphen_role == HyphenRole.PART2:
                subs = candidate.hyphen_subs_content
            elif not subs and candidate.hyphen_role == HyphenRole.BOTH:
                subs = candidate.hyphen_subs_content  # backward subs of candidate

            # Set forward link on the BOTH line
            line.hyphen_forward_pair_id = candidate.line_id
            if subs:
                line.hyphen_forward_subs_content = subs

            # Set backward link on the candidate
            if candidate.hyphen_role == HyphenRole.BOTH:
                candidate.hyphen_pair_line_id = line.line_id
                if subs:
                    candidate.hyphen_subs_content = subs
            else:
                candidate.hyphen_pair_line_id = line.line_id
                if subs:
                    candidate.hyphen_subs_content = subs
        else:
            # Regular PART1 line
            subs = line.hyphen_subs_content or candidate.hyphen_subs_content
            if candidate.hyphen_role == HyphenRole.BOTH:
                subs = subs or candidate.hyphen_subs_content

            # Bidirectional link
            line.hyphen_pair_line_id = candidate.line_id
            if candidate.hyphen_role == HyphenRole.BOTH:
                candidate.hyphen_pair_line_id = line.line_id
            else:
                candidate.hyphen_pair_line_id = line.line_id

            if subs:
                line.hyphen_subs_content = subs
                if candidate.hyphen_role == HyphenRole.BOTH:
                    candidate.hyphen_subs_content = subs
                else:
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

    A line can be both PART2 (first String has SUBS_TYPE="HypPart2") AND
    PART1 (trailing HYP element or last String has SUBS_TYPE="HypPart1").
    In that case, role is set to BOTH with forward fields for the PART1 side.
    """
    children = list(textline)
    if not children:
        return

    string_tag = _tag("String", ns)
    hyp_tag = _tag("HYP", ns)

    # --- Detect PART2: first String has SUBS_TYPE="HypPart2" ---
    is_part2 = False
    backward_subs: Optional[str] = None

    first_string = next(
        (c for c in children if c.tag == string_tag), None
    )
    if first_string is not None:
        subs_type = first_string.get("SUBS_TYPE", "")
        if subs_type == "HypPart2":
            is_part2 = True
            backward_subs = first_string.get("SUBS_CONTENT")

    # --- Detect PART1: trailing HYP, or last String SUBS_TYPE="HypPart1",
    #     or heuristic trailing dash ---
    is_part1 = False
    forward_subs: Optional[str] = None
    forward_explicit = False

    last_child = children[-1]
    if etree.QName(last_child.tag).localname == "HYP":
        is_part1 = True
        forward_explicit = True
        prev_strings = [c for c in children if c.tag == string_tag]
        if prev_strings:
            sc = prev_strings[-1].get("SUBS_CONTENT")
            if sc:
                forward_subs = sc
    else:
        last_string = next(
            (c for c in reversed(children) if c.tag == string_tag), None
        )
        if last_string is not None:
            if last_string.get("SUBS_TYPE", "") == "HypPart1":
                is_part1 = True
                forward_explicit = True
                sc = last_string.get("SUBS_CONTENT")
                if sc:
                    forward_subs = sc

    # Heuristic: last non-space token ends with "-"
    if not is_part1:
        tokens = line.ocr_text.split()
        if tokens and tokens[-1].endswith("-"):
            is_part1 = True
            forward_explicit = False

    # --- Set role based on detection ---
    if is_part2 and is_part1:
        line.hyphen_role = HyphenRole.BOTH
        # Backward (PART2 side) in existing fields
        line.hyphen_source_explicit = True  # PART2 from SUBS_TYPE is always explicit
        if backward_subs:
            line.hyphen_subs_content = backward_subs
        # Forward (PART1 side) in new fields
        line.hyphen_forward_explicit = forward_explicit
        if forward_subs:
            line.hyphen_forward_subs_content = forward_subs
    elif is_part2:
        line.hyphen_role = HyphenRole.PART2
        line.hyphen_source_explicit = True
        if backward_subs:
            line.hyphen_subs_content = backward_subs
    elif is_part1:
        line.hyphen_role = HyphenRole.PART1
        line.hyphen_source_explicit = forward_explicit
        if forward_subs:
            line.hyphen_subs_content = forward_subs


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
