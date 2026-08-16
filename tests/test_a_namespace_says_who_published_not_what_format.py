"""A namespace URI says who published a document, not what format it is in.

Gallica serves a large family of its ALTO under the BnF's own namespace,
``http://bibnum.bnf.fr/ns/alto_prod``. Those files carry
``TextBlock``/``TextLine``/``String``/``SP``/``HYP`` and **explicit**
``SUBS_TYPE``/``SUBS_CONTENT`` hyphenation — the richest input this library
accepts — and the door refused every one of them because the namespace URI
did not contain ``loc.gov``.

Nothing downstream was ever branded: the parser and the rewriter read the
namespace off the document they were handed and re-emit it unchanged. The
proof is here — a vendor namespace goes in, parses with its hyphenation,
and comes back out of the rewriter under its own URI.

The two refusal tests are the point of the pair: widening a door is only
safe if it is still a door. One pins that the schema's mandatory element is
really required, the other that an unrelated root is still turned away.

Measured with the fix reverted: **two** of these fail — the two that go
through ``sniff_format``. The parse and round-trip tests pass either way,
on purpose. They reach the ALTO parser directly, so what they record is
that the machinery never had to change; reading them as guards of the fix
would credit them with work they do not do.
"""

from __future__ import annotations

import pytest
from saknussemm.core.schemas import HyphenRole
from saknussemm.errors import ParseError
from saknussemm.formats._xml import detect_namespace
from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.formats.alto.rewriter import rewrite_alto_file
from saknussemm.formats.loader import sniff_format
from lxml import etree

from tests._paths import EXAMPLES

BNF_VENDOR_NS = EXAMPLES / "bnf-alto-prod-bpt6k5406037v-f40.xml"
VENDOR_NS_URI = "http://bibnum.bnf.fr/ns/alto_prod"


def test_a_vendor_namespace_alto_is_recognised_as_alto():
    assert sniff_format(BNF_VENDOR_NS) == "alto"


def test_the_standard_namespaces_still_answer_first():
    """The fallback is a fallback: the LoC and PRImA markers are untouched."""
    assert sniff_format(EXAMPLES / "X0000002.xml") == "alto"
    assert sniff_format(EXAMPLES / "sample.xml") == "alto"
    page = (
        EXAMPLES
        / "page"
        / ("Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml")
    )
    assert sniff_format(page) == "page"


def test_a_vendor_namespace_alto_parses_with_its_explicit_hyphenation():
    """What the door was refusing: a page whose hyphenation is ASSERTED.

    Heuristic pairing has to infer a partner from a trailing mark. These
    lines carry ``SUBS_TYPE`` and ``SUBS_CONTENT``, so the producer states
    both the role and the whole word — nothing to guess.
    """
    doc = build_document_manifest([(BNF_VENDOR_NS, BNF_VENDOR_NS.name)])
    (page,) = doc.pages
    substantive = [line for line in page.lines if line.ocr_text.strip()]
    assert len(substantive) == 27

    part1 = [
        line
        for line in page.lines
        if line.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
    ]
    assert part1, "the page's hyphenated lines did not survive the parse"
    assert all(line.hyphen_source_explicit for line in part1)
    # `plusieurs` is deliberately an unaccented witness: this fixture's bytes
    # are UTF-8 behind an ISO-8859-1 declaration, so any accented string is
    # mojibake until the encoding pass lands. Structure is what this file
    # tests; the text is the next commit's subject.
    assert "plusieurs" in {line.hyphen_subs_content for line in part1}


def test_a_vendor_namespace_survives_the_rewrite_unchanged():
    """Round-trip: the file goes back out under ITS namespace, not ours."""
    doc = build_document_manifest([(BNF_VENDOR_NS, BNF_VENDOR_NS.name)])
    (page,) = doc.pages
    for line in page.lines:
        line.corrected_text = line.ocr_text

    result = rewrite_alto_file(BNF_VENDOR_NS, [page], provider="none", model="none")

    root = etree.fromstring(result.xml_bytes)
    assert detect_namespace(root) == VENDOR_NS_URI
    assert set(result.rewriter_paths.values()) == {"untouched"}
    assert not result.losses


def test_a_root_named_alto_without_its_mandatory_layout_is_refused(tmp_path):
    """The fallback checks the schema, not the spelling of the root tag.

    Without this, ``sniff_format`` would accept anything whose root element
    happens to be called ``alto`` — which is a name check wearing a format
    check's clothes.
    """
    impostor = tmp_path / "impostor.xml"
    impostor.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<alto xmlns="http://example.invalid/not-alto">'
        b"<Description/></alto>"
    )
    with pytest.raises(ParseError) as excinfo:
        sniff_format(impostor)
    assert "Layout" in str(excinfo.value)


def test_an_unrelated_root_is_still_refused(tmp_path):
    """Widening a door is only safe while it is still a door."""
    other = tmp_path / "other.xml"
    other.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<mets xmlns="http://www.loc.gov/METS/"><fileSec/></mets>'
    )
    with pytest.raises(ParseError):
        sniff_format(other)
