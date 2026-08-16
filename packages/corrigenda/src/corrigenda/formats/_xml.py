"""Format-agnostic XML helpers shared by every transcription format.

lxml lives here — so this module is NOT part of the pure ``core`` (the
import-contract test allows ``formats`` to import lxml) — but it is NOT a
format either: namespace detection, tag qualification, and the hardened
parser are identical for ALTO, PAGE, and any future format.

Homing them here keeps the format packages *siblings* — ``alto → _xml ←
page`` — instead of making one an accidental base that the other reaches
sideways into (the former ``page → alto`` edge, which meant deleting or
refactoring ALTO would break PAGE). Each format's ``_ns`` re-exports these
three under its existing private names, so call sites are unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from lxml import etree

from corrigenda.errors import CorrigendaError, ParseError


def detect_namespace(root: object) -> str:
    """Return the namespace URI from a root element's tag, or '' if none.

    Defensive against a tag that opens with ``{`` but has no closing brace,
    and against a non-element ``root`` (``getattr`` fallback) — works for
    both the ALTO and PAGE parse/rewrite entry points.
    """
    tag = getattr(root, "tag", "")
    if isinstance(tag, str) and tag.startswith("{") and "}" in tag:
        return tag[1 : tag.index("}")]
    return ""


def local_name(element: object) -> str:
    """Return an element's tag without its namespace, or '' if it has none.

    The inverse of :func:`detect_namespace`: that one keeps the URI and
    drops the name, this one keeps the name and drops the URI. Used where
    a document must be recognised by its *schema shape* rather than by
    whose namespace URI it was published under.
    """
    tag_value = getattr(element, "tag", "")
    if not isinstance(tag_value, str):
        return ""
    if tag_value.startswith("{") and "}" in tag_value:
        return tag_value[tag_value.index("}") + 1 :]
    return tag_value


def tag(local: str, ns: str) -> str:
    """Qualify a local tag name with a namespace (Clark notation)."""
    return f"{{{ns}}}{local}" if ns else local


def make_safe_parser() -> etree.XMLParser:
    """Return an lxml parser hardened against XXE / SSRF / entity-amplification.

    The four flags together neutralise the well-known XML attack surface:

      - ``resolve_entities=False`` — do not expand ``&entity;`` references.
        Defeats internal-entity amplification ("billion laughs") and any
        residual external-entity leak across lxml versions.
      - ``no_network=True`` — refuse to fetch external DTDs / entities.
        Defeats SSRF via ``<!DOCTYPE x SYSTEM "http://...">``.
      - ``load_dtd=False`` — do not load any DTD (inline or external).
        Defence in depth on top of ``no_network``.
      - ``dtd_validation=False`` — do not validate against a DTD. Default
        already; pinned here for clarity (a future maintainer flipping
        validation on would silently re-enable DTD loading).

    Returns a FRESH parser instance per call: lxml parsers are not
    documented as thread-safe and the construction cost is microseconds.

    Use this for EVERY ``etree.parse`` / ``etree.fromstring`` call that
    touches user-controlled XML — the grep-based contract test in
    ``packages/corrigenda/tests/test_xml_security.py`` trips on any call
    site under ``formats/`` that doesn't.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
    )


@contextmanager
def classified_parse_errors(source_name: str) -> Iterator[None]:
    """§8.4 — a parser may only raise classified :class:`CorrigendaError`s.

    Wrap a parser entry point's body in this context manager so hostile
    or malformed input can never escape as an unclassified exception
    (ADR-008; pinned by the fuzz suite):

      - ``etree.XMLSyntaxError`` (malformed XML, encoding mismatches,
        truncated files) → :class:`ParseError`;
      - bare ``ValueError`` (e.g. a genuinely non-numeric coordinate under
        the strict ``parse_int_tolerant`` policy) → :class:`ParseError`;
      - ``OSError`` (unreadable/missing source file) → :class:`ParseError`.

    Existing classified errors — :class:`ParseError` itself,
    :class:`DuplicateIdError`, any :class:`CorrigendaError` — pass through
    untouched. Genuine programming errors (``TypeError``,
    ``AttributeError``, …) are deliberately NOT wrapped: masking a library
    bug as a bad-input error would hide it from every caller.
    """
    try:
        yield
    except CorrigendaError:
        raise
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ParseError(f"{source_name}: cannot parse document: {exc}") from exc
    except OSError as exc:
        raise ParseError(f"{source_name}: cannot read source file: {exc}") from exc


__all__ = [
    "classified_parse_errors",
    "detect_namespace",
    "local_name",
    "make_safe_parser",
    "tag",
]
