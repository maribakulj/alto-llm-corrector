from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from lxml import etree

from app.schemas import HyphenRole, LineManifest, PageManifest

# ---------------------------------------------------------------------------
# Namespace helpers (mirrors parser)
# ---------------------------------------------------------------------------

def _detect_namespace(root: etree._Element) -> str:
    tag = root.tag
    if tag.startswith("{"):
        return tag[1: tag.index("}")]
    return ""


def _tag(local: str, ns: str) -> str:
    return f"{{{ns}}}{local}" if ns else local


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Split text into alternating word/space tokens, dropping empty strings."""
    return [t for t in re.split(r"(\s+)", text) if t]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _compute_geometry(
    hpos: int,
    width: int,
    tokens: list[str],
) -> list[tuple[str, int, int]]:
    """
    Return list of (token, token_hpos, token_width) for every token.

    Space tokens get proportional width; word tokens get proportional width.
    The last token is adjusted so sum(widths) == width exactly.
    """
    if not tokens:
        return []

    # First pass: compute raw weights
    # unit will be refined after we know total weight
    total_chars = sum(len(t) for t in tokens)
    if total_chars == 0:
        # Edge case: all tokens are empty — distribute evenly
        per = width // len(tokens) if tokens else 0
        result = [(t, hpos + i * per, per) for i, t in enumerate(tokens)]
        return result

    unit = width / total_chars  # pixels per character (float)

    raw_widths: list[int] = []
    for t in tokens:
        if t.strip() == "":
            # space token
            w = max(1, round(len(t) * 0.6 * unit))
        else:
            w = max(1, round(len(t) * unit))
        raw_widths.append(w)

    # Correct rounding on last token
    correction = width - sum(raw_widths)
    raw_widths[-1] = max(1, raw_widths[-1] + correction)

    # Build (token, hpos, width) triples
    result: list[tuple[str, int, int]] = []
    cursor = hpos
    for t, w in zip(tokens, raw_widths):
        result.append((t, cursor, w))
        cursor += w

    return result


# ---------------------------------------------------------------------------
# Internal: clear existing String/SP/HYP children and WC/CC attributes
# ---------------------------------------------------------------------------

def _clear_line(line_el: etree._Element, ns: str) -> None:
    string_tag = _tag("String", ns)
    sp_tag = _tag("SP", ns)
    hyp_tag = _tag("HYP", ns)
    to_remove = [
        c for c in line_el
        if c.tag in (string_tag, sp_tag, hyp_tag)
    ]
    for c in to_remove:
        line_el.remove(c)
    for attr in ("WC", "CC"):
        if attr in line_el.attrib:
            del line_el.attrib[attr]


# ---------------------------------------------------------------------------
# Internal: collect original String attributes before clearing
# ---------------------------------------------------------------------------

def _collect_original_strings(
    line_el: etree._Element,
    ns: str,
) -> list[dict[str, str | None]]:
    """
    Return [{id, wc}, ...] for each original String child, in document order.

    Called before _clear_line so that original IDs and WC confidence scores
    can be re-applied to the rebuilt String nodes at the same position.
    """
    string_tag = _tag("String", ns)
    return [
        {"id": child.get("ID"), "wc": child.get("WC")}
        for child in line_el
        if child.tag == string_tag
    ]


# ---------------------------------------------------------------------------
# Rebuild helpers
# ---------------------------------------------------------------------------

def _rebuild_normal_line(
    line_el: etree._Element,
    corrected_text: str,
    manifest: LineManifest,
    ns: str,
) -> None:
    """Rebuild a non-hyphenated TextLine with corrected text."""
    orig = _collect_original_strings(line_el, ns)

    # Preserve any HYP nodes that exist on this line: the parser may have
    # missed PART1 detection (e.g. heuristic miss), so we must not silently
    # drop the hyphen element.  They are re-appended at the end.
    hyp_tag = _tag("HYP", ns)
    saved_hyp = [c for c in line_el if c.tag == hyp_tag]

    _clear_line(line_el, ns)

    hpos = int(line_el.get("HPOS", 0))
    vpos = int(line_el.get("VPOS", 0))
    width = int(line_el.get("WIDTH", 0))
    height = int(line_el.get("HEIGHT", 0))

    tokens = _tokenize(corrected_text)
    if not tokens:
        for hyp_el in saved_hyp:
            line_el.append(hyp_el)
        return

    geo = _compute_geometry(hpos, width, tokens)
    str_n = 0

    for token, tok_hpos, tok_width in geo:
        if token.strip() == "":
            sp = etree.SubElement(line_el, _tag("SP", ns))
            sp.set("WIDTH", str(tok_width))
            sp.set("HPOS", str(tok_hpos))
            sp.set("VPOS", str(vpos))
        else:
            s = etree.SubElement(line_el, _tag("String", ns))
            orig_id = orig[str_n]["id"] if str_n < len(orig) else None
            s.set("ID", orig_id or f"{manifest.line_id}_STR_{str_n:04d}")
            s.set("CONTENT", token.replace("\u00ad", ""))
            s.set("HPOS", str(tok_hpos))
            s.set("VPOS", str(vpos))
            s.set("WIDTH", str(tok_width))
            s.set("HEIGHT", str(height))
            if str_n < len(orig) and orig[str_n]["wc"] is not None:
                s.set("WC", orig[str_n]["wc"])
            str_n += 1

    for hyp_el in saved_hyp:
        line_el.append(hyp_el)


def _rebuild_hyp_part1(
    line_el: etree._Element,
    corrected_text: str,
    manifest: LineManifest,
    ns: str,
) -> None:
    """Rebuild a PART1 (hyphen-left) TextLine."""
    orig = _collect_original_strings(line_el, ns)
    _clear_line(line_el, ns)

    hpos = int(line_el.get("HPOS", 0))
    vpos = int(line_el.get("VPOS", 0))
    width = int(line_el.get("WIDTH", 0))
    height = int(line_el.get("HEIGHT", 0))

    # Reserve ~4% of width for the HYP element
    hyp_width = max(1, round(width * 0.04))
    text_width = max(1, width - hyp_width)

    tokens = _tokenize(corrected_text)
    if not tokens:
        # No text content, but the HYP node must still be present.
        hyp = etree.SubElement(line_el, _tag("HYP", ns))
        hyp.set("CONTENT", "-")
        hyp.set("HPOS", str(hpos + text_width))
        hyp.set("VPOS", str(vpos))
        hyp.set("WIDTH", str(hyp_width))
        hyp.set("HEIGHT", str(height))
        return

    geo = _compute_geometry(hpos, text_width, tokens)
    words = [t for t in tokens if t.strip() != ""]

    # Determine which geo entry is the last word token
    last_word_token = words[-1] if words else None
    str_n = 0
    last_word_hpos = hpos
    last_word_width = hyp_width  # fallback

    for token, tok_hpos, tok_width in geo:
        if token.strip() == "":
            sp = etree.SubElement(line_el, _tag("SP", ns))
            sp.set("WIDTH", str(tok_width))
            sp.set("HPOS", str(tok_hpos))
            sp.set("VPOS", str(vpos))
        else:
            is_last_word = (token == last_word_token and str_n == len(words) - 1)
            s = etree.SubElement(line_el, _tag("String", ns))
            orig_id = orig[str_n]["id"] if str_n < len(orig) else None
            s.set("ID", orig_id or f"{manifest.line_id}_STR_{str_n:04d}")
            s.set("CONTENT", token.replace("\u00ad", ""))
            s.set("HPOS", str(tok_hpos))
            s.set("VPOS", str(vpos))
            s.set("WIDTH", str(tok_width))
            s.set("HEIGHT", str(height))
            if str_n < len(orig) and orig[str_n]["wc"] is not None:
                s.set("WC", orig[str_n]["wc"])

            if is_last_word:
                last_word_hpos = tok_hpos
                last_word_width = tok_width
                # Add SUBS_TYPE/SUBS_CONTENT only for explicit source
                if (
                    manifest.hyphen_source_explicit
                    and manifest.hyphen_subs_content
                ):
                    s.set("SUBS_TYPE", "HypPart1")
                    s.set("SUBS_CONTENT", manifest.hyphen_subs_content)

            str_n += 1

    # Append HYP element
    hyp_hpos = last_word_hpos + last_word_width
    hyp = etree.SubElement(line_el, _tag("HYP", ns))
    hyp.set("CONTENT", "-")
    hyp.set("HPOS", str(hyp_hpos))
    hyp.set("VPOS", str(vpos))
    hyp.set("WIDTH", str(hyp_width))
    hyp.set("HEIGHT", str(height))


def _rebuild_hyp_part2(
    line_el: etree._Element,
    corrected_text: str,
    manifest: LineManifest,
    ns: str,
) -> None:
    """Rebuild a PART2 (hyphen-right) TextLine."""
    orig = _collect_original_strings(line_el, ns)
    _clear_line(line_el, ns)

    hpos = int(line_el.get("HPOS", 0))
    vpos = int(line_el.get("VPOS", 0))
    width = int(line_el.get("WIDTH", 0))
    height = int(line_el.get("HEIGHT", 0))

    tokens = _tokenize(corrected_text)
    if not tokens:
        return

    geo = _compute_geometry(hpos, width, tokens)
    words = [t for t in tokens if t.strip() != ""]
    str_n = 0

    for token, tok_hpos, tok_width in geo:
        if token.strip() == "":
            sp = etree.SubElement(line_el, _tag("SP", ns))
            sp.set("WIDTH", str(tok_width))
            sp.set("HPOS", str(tok_hpos))
            sp.set("VPOS", str(vpos))
        else:
            s = etree.SubElement(line_el, _tag("String", ns))
            orig_id = orig[str_n]["id"] if str_n < len(orig) else None
            s.set("ID", orig_id or f"{manifest.line_id}_STR_{str_n:04d}")
            s.set("CONTENT", token.replace("\u00ad", ""))
            s.set("HPOS", str(tok_hpos))
            s.set("VPOS", str(vpos))
            s.set("WIDTH", str(tok_width))
            s.set("HEIGHT", str(height))
            if str_n < len(orig) and orig[str_n]["wc"] is not None:
                s.set("WC", orig[str_n]["wc"])

            if str_n == 0:
                # First word: SUBS_TYPE="HypPart2" if explicit
                if (
                    manifest.hyphen_source_explicit
                    and manifest.hyphen_subs_content
                ):
                    s.set("SUBS_TYPE", "HypPart2")
                    s.set("SUBS_CONTENT", manifest.hyphen_subs_content)

            str_n += 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def rewrite_alto_file(
    xml_path: Path,
    page_manifests: list[PageManifest],
    provider: str,
    model: str,
) -> bytes:
    """
    Rewrite an ALTO XML file with corrected text from page_manifests.

    Returns the rewritten XML as UTF-8 bytes.
    """
    tree = etree.parse(str(xml_path))
    root = tree.getroot()
    ns = _detect_namespace(root)

    # Build lookup: line_id → LineManifest
    line_by_id: dict[str, LineManifest] = {}
    for page in page_manifests:
        for lm in page.lines:
            line_by_id[lm.line_id] = lm

    # Walk all TextLine elements
    textline_tag = _tag("TextLine", ns)
    for tl_el in root.iter(textline_tag):
        line_id = tl_el.get("ID")
        if line_id not in line_by_id:
            continue
        lm = line_by_id[line_id]

        # Use corrected_text if available, otherwise keep OCR source
        corrected = lm.corrected_text if lm.corrected_text is not None else lm.ocr_text

        if lm.hyphen_role == HyphenRole.PART1:
            _rebuild_hyp_part1(tl_el, corrected, lm, ns)
        elif lm.hyphen_role == HyphenRole.PART2:
            _rebuild_hyp_part2(tl_el, corrected, lm, ns)
        else:
            _rebuild_normal_line(tl_el, corrected, lm, ns)

    # Add processing entry if Description/Processing exists
    _add_processing_entry(root, ns, provider, model)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _add_processing_entry(
    root: etree._Element,
    ns: str,
    provider: str,
    model: str,
) -> None:
    desc = root.find(_tag("Description", ns))
    if desc is None:
        return
    processing = desc.find(_tag("Processing", ns))
    if processing is None:
        return
    step = etree.SubElement(processing, _tag("processingStep", ns))
    step.set("type", "contentModification")
    step.set("description", f"Post-OCR correction via {provider}/{model} (alto-llm-corrector)")
