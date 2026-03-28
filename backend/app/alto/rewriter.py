from __future__ import annotations

import copy
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

    total_chars = sum(len(t) for t in tokens)
    if total_chars == 0:
        per = width // len(tokens) if tokens else 0
        result = [(t, hpos + i * per, per) for i, t in enumerate(tokens)]
        return result

    unit = width / total_chars

    raw_widths: list[int] = []
    for t in tokens:
        if t.strip() == "":
            w = max(1, round(len(t) * 0.6 * unit))
        else:
            w = max(1, round(len(t) * unit))
        raw_widths.append(w)

    correction = width - sum(raw_widths)
    raw_widths[-1] = max(1, raw_widths[-1] + correction)

    result: list[tuple[str, int, int]] = []
    cursor = hpos
    for t, w in zip(tokens, raw_widths):
        result.append((t, cursor, w))
        cursor += w

    return result


# ---------------------------------------------------------------------------
# Conservative helpers: read original children without destroying them
# ---------------------------------------------------------------------------

def _get_string_children(
    line_el: etree._Element,
    ns: str,
) -> list[etree._Element]:
    """Return original String children in document order."""
    string_tag = _tag("String", ns)
    return [c for c in line_el if c.tag == string_tag]


def _get_sp_children(
    line_el: etree._Element,
    ns: str,
) -> list[etree._Element]:
    """Return original SP children in document order."""
    sp_tag = _tag("SP", ns)
    return [c for c in line_el if c.tag == sp_tag]


def _get_hyp_children(
    line_el: etree._Element,
    ns: str,
) -> list[etree._Element]:
    """Return original HYP children in document order."""
    hyp_tag = _tag("HYP", ns)
    return [c for c in line_el if c.tag == hyp_tag]


def _extract_text_from_line(
    line_el: etree._Element,
    ns: str,
) -> str:
    """
    Reconstruct the OCR text from a TextLine's children (String + SP + HYP).
    Used to compare with corrected_text to detect unchanged lines.
    """
    string_tag = _tag("String", ns)
    sp_tag = _tag("SP", ns)
    hyp_tag = _tag("HYP", ns)
    parts: list[str] = []
    for child in line_el:
        if child.tag == string_tag:
            parts.append(child.get("CONTENT", ""))
        elif child.tag == sp_tag:
            parts.append(" ")
        elif child.tag == hyp_tag:
            content = child.get("CONTENT", "-")
            if content:
                parts.append(content)
    return "".join(parts)


def _line_text_unchanged(
    line_el: etree._Element,
    corrected_text: str,
    ns: str,
) -> bool:
    """Return True if the corrected text matches what the line already contains."""
    current = _extract_text_from_line(line_el, ns)
    return current == corrected_text


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
# In-place update: modify only CONTENT on existing String elements
# ---------------------------------------------------------------------------

def _update_content_in_place(
    line_el: etree._Element,
    corrected_text: str,
    ns: str,
) -> bool:
    """
    When word count matches, update only CONTENT attributes in-place.

    Returns True if the in-place update succeeded.
    All original attributes (ID, HPOS, VPOS, WIDTH, HEIGHT, WC, STYLE,
    FONTSIZE, CC, etc.) and SP/HYP elements are left completely untouched.
    """
    orig_strings = _get_string_children(line_el, ns)
    tokens = _tokenize(corrected_text)
    word_tokens = [t for t in tokens if t.strip() != ""]

    if len(word_tokens) != len(orig_strings):
        return False

    # Update only CONTENT on each String element
    for string_el, word in zip(orig_strings, word_tokens):
        string_el.set("CONTENT", word.replace("\u00ad", ""))

    return True


# ---------------------------------------------------------------------------
# Rebuild helpers (slow path: used only when word count changed)
# ---------------------------------------------------------------------------

def _rebuild_normal_line(
    line_el: etree._Element,
    corrected_text: str,
    manifest: LineManifest,
    ns: str,
) -> None:
    """Rebuild a non-hyphenated TextLine with corrected text."""
    # --- Fast path: same word count → in-place CONTENT update only ---
    if _update_content_in_place(line_el, corrected_text, ns):
        return

    # --- Slow path: word count differs → full rebuild with proportional geometry ---
    # Save full copies of original children for geometry reference
    orig_strings = _get_string_children(line_el, ns)
    orig_sps = _get_sp_children(line_el, ns)
    orig_string_attribs = [dict(s.attrib) for s in orig_strings]
    orig_sp_attribs = [dict(s.attrib) for s in orig_sps]

    hyp_tag = _tag("HYP", ns)
    saved_hyp = [copy.deepcopy(c) for c in line_el if c.tag == hyp_tag]

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
    sp_n = 0

    for token, tok_hpos, tok_width in geo:
        if token.strip() == "":
            sp = etree.SubElement(line_el, _tag("SP", ns))
            if sp_n < len(orig_sp_attribs):
                # Reuse ALL original SP attributes
                for k, v in orig_sp_attribs[sp_n].items():
                    sp.set(k, v)
            else:
                sp.set("WIDTH", str(tok_width))
                sp.set("HPOS", str(tok_hpos))
                sp.set("VPOS", str(vpos))
            sp_n += 1
        else:
            s = etree.SubElement(line_el, _tag("String", ns))
            if str_n < len(orig_string_attribs):
                # Copy ALL original attributes, then override only what changed
                for k, v in orig_string_attribs[str_n].items():
                    s.set(k, v)
                s.set("CONTENT", token.replace("\u00ad", ""))
                s.set("HPOS", str(tok_hpos))
                s.set("WIDTH", str(tok_width))
            else:
                s.set("ID", f"{manifest.line_id}_STR_{str_n:04d}")
                s.set("CONTENT", token.replace("\u00ad", ""))
                s.set("HPOS", str(tok_hpos))
                s.set("VPOS", str(vpos))
                s.set("WIDTH", str(tok_width))
                s.set("HEIGHT", str(height))
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
    orig_strings = _get_string_children(line_el, ns)
    orig_sps = _get_sp_children(line_el, ns)
    orig_hyps = _get_hyp_children(line_el, ns)

    tokens = _tokenize(corrected_text)
    words = [t for t in tokens if t.strip() != ""]

    # --- Fast path: same word count → in-place CONTENT update only ---
    if len(words) == len(orig_strings):
        for string_el, word in zip(orig_strings, words):
            string_el.set("CONTENT", word.replace("\u00ad", ""))

        # Update SUBS attributes on last String
        last_str = orig_strings[-1] if orig_strings else None
        if last_str is not None:
            if manifest.hyphen_source_explicit and manifest.hyphen_subs_content:
                last_str.set("SUBS_TYPE", "HypPart1")
                last_str.set("SUBS_CONTENT", manifest.hyphen_subs_content)
            else:
                # Remove stale SUBS attributes if subs_content was neutralised
                for attr in ("SUBS_TYPE", "SUBS_CONTENT"):
                    if attr in last_str.attrib:
                        del last_str.attrib[attr]
        return

    # --- Slow path: different word count → full rebuild ---
    orig_string_attribs = [dict(s.attrib) for s in orig_strings]
    orig_sp_attribs = [dict(s.attrib) for s in orig_sps]
    orig_hyp_attribs = dict(orig_hyps[0].attrib) if orig_hyps else {}

    _clear_line(line_el, ns)

    hpos = int(line_el.get("HPOS", 0))
    vpos = int(line_el.get("VPOS", 0))
    width = int(line_el.get("WIDTH", 0))
    height = int(line_el.get("HEIGHT", 0))

    hyp_width = max(1, round(width * 0.04))
    text_width = max(1, width - hyp_width)

    if not tokens:
        hyp = etree.SubElement(line_el, _tag("HYP", ns))
        hyp.set("CONTENT", "-")
        if orig_hyp_attribs:
            for k, v in orig_hyp_attribs.items():
                hyp.set(k, v)
        else:
            hyp.set("HPOS", str(hpos + text_width))
            hyp.set("VPOS", str(vpos))
            hyp.set("WIDTH", str(hyp_width))
            hyp.set("HEIGHT", str(height))
        return

    geo = _compute_geometry(hpos, text_width, tokens)
    str_n = 0
    sp_n = 0
    last_word_hpos = hpos
    last_word_width = hyp_width

    for token, tok_hpos, tok_width in geo:
        if token.strip() == "":
            sp = etree.SubElement(line_el, _tag("SP", ns))
            if sp_n < len(orig_sp_attribs):
                for k, v in orig_sp_attribs[sp_n].items():
                    sp.set(k, v)
            else:
                sp.set("WIDTH", str(tok_width))
                sp.set("HPOS", str(tok_hpos))
                sp.set("VPOS", str(vpos))
            sp_n += 1
        else:
            is_last_word = (str_n == len(words) - 1)
            s = etree.SubElement(line_el, _tag("String", ns))
            if str_n < len(orig_string_attribs):
                for k, v in orig_string_attribs[str_n].items():
                    s.set(k, v)
                s.set("CONTENT", token.replace("\u00ad", ""))
                s.set("HPOS", str(tok_hpos))
                s.set("WIDTH", str(tok_width))
            else:
                s.set("ID", f"{manifest.line_id}_STR_{str_n:04d}")
                s.set("CONTENT", token.replace("\u00ad", ""))
                s.set("HPOS", str(tok_hpos))
                s.set("VPOS", str(vpos))
                s.set("WIDTH", str(tok_width))
                s.set("HEIGHT", str(height))

            if is_last_word:
                last_word_hpos = tok_hpos
                last_word_width = tok_width
                if manifest.hyphen_source_explicit and manifest.hyphen_subs_content:
                    s.set("SUBS_TYPE", "HypPart1")
                    s.set("SUBS_CONTENT", manifest.hyphen_subs_content)
                else:
                    for attr in ("SUBS_TYPE", "SUBS_CONTENT"):
                        if attr in s.attrib:
                            del s.attrib[attr]

            str_n += 1

    # Append HYP element preserving ALL original attributes
    hyp = etree.SubElement(line_el, _tag("HYP", ns))
    if orig_hyp_attribs:
        for k, v in orig_hyp_attribs.items():
            hyp.set(k, v)
    else:
        hyp.set("CONTENT", "-")
        hyp.set("HPOS", str(last_word_hpos + last_word_width))
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
    orig_strings = _get_string_children(line_el, ns)
    orig_sps = _get_sp_children(line_el, ns)

    tokens = _tokenize(corrected_text)
    words = [t for t in tokens if t.strip() != ""]

    # --- Fast path: same word count → in-place CONTENT update only ---
    if len(words) == len(orig_strings):
        for string_el, word in zip(orig_strings, words):
            string_el.set("CONTENT", word.replace("\u00ad", ""))

        # Update SUBS attributes on first String
        first_str = orig_strings[0] if orig_strings else None
        if first_str is not None:
            if manifest.hyphen_source_explicit and manifest.hyphen_subs_content:
                first_str.set("SUBS_TYPE", "HypPart2")
                first_str.set("SUBS_CONTENT", manifest.hyphen_subs_content)
            else:
                for attr in ("SUBS_TYPE", "SUBS_CONTENT"):
                    if attr in first_str.attrib:
                        del first_str.attrib[attr]
        return

    # --- Slow path: different word count → full rebuild ---
    orig_string_attribs = [dict(s.attrib) for s in orig_strings]
    orig_sp_attribs = [dict(s.attrib) for s in orig_sps]

    _clear_line(line_el, ns)

    hpos = int(line_el.get("HPOS", 0))
    vpos = int(line_el.get("VPOS", 0))
    width = int(line_el.get("WIDTH", 0))
    height = int(line_el.get("HEIGHT", 0))

    if not tokens:
        return

    geo = _compute_geometry(hpos, width, tokens)
    str_n = 0
    sp_n = 0

    for token, tok_hpos, tok_width in geo:
        if token.strip() == "":
            sp = etree.SubElement(line_el, _tag("SP", ns))
            if sp_n < len(orig_sp_attribs):
                for k, v in orig_sp_attribs[sp_n].items():
                    sp.set(k, v)
            else:
                sp.set("WIDTH", str(tok_width))
                sp.set("HPOS", str(tok_hpos))
                sp.set("VPOS", str(vpos))
            sp_n += 1
        else:
            s = etree.SubElement(line_el, _tag("String", ns))
            if str_n < len(orig_string_attribs):
                for k, v in orig_string_attribs[str_n].items():
                    s.set(k, v)
                s.set("CONTENT", token.replace("\u00ad", ""))
                s.set("HPOS", str(tok_hpos))
                s.set("WIDTH", str(tok_width))
            else:
                s.set("ID", f"{manifest.line_id}_STR_{str_n:04d}")
                s.set("CONTENT", token.replace("\u00ad", ""))
                s.set("HPOS", str(tok_hpos))
                s.set("VPOS", str(vpos))
                s.set("WIDTH", str(tok_width))
                s.set("HEIGHT", str(height))

            if str_n == 0:
                if manifest.hyphen_source_explicit and manifest.hyphen_subs_content:
                    s.set("SUBS_TYPE", "HypPart2")
                    s.set("SUBS_CONTENT", manifest.hyphen_subs_content)
                else:
                    for attr in ("SUBS_TYPE", "SUBS_CONTENT"):
                        if attr in s.attrib:
                            del s.attrib[attr]

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

        # --- Conservative: skip entirely unchanged lines ---
        # If the text hasn't changed AND no SUBS_CONTENT update is needed,
        # leave the original XML completely untouched.
        subs_needs_update = (
            lm.hyphen_role != HyphenRole.NONE
            and lm.hyphen_source_explicit
            and lm.hyphen_subs_content is not None
        )
        if not subs_needs_update and _line_text_unchanged(tl_el, corrected, ns):
            continue

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
