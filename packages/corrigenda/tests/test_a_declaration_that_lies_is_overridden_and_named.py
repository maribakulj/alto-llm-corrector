"""A source file that lies about its encoding is read right — and says so.

Gallica serves ALTO declaring ``ISO-8859-1`` whose bytes are UTF-8. Read as
declared, ``cléricales`` arrives as ``clÃ©ricales``. That is not a cosmetic
problem for a post-OCR corrector: handed mojibake, a model repairs it, and
the run delivers a text change the report cannot tell apart from a
correction — the undeclared alteration `V1` exists to refuse.

So the library reads the file as what it *is*, and records the override on
the manifest. Both halves are tested here, and the second is the one that
matters: an override nobody can see is the defect wearing a fix's clothes.

The negative control is the point of the file. ``mislabelled_utf8`` must
also know how to say *no*, or it is not a rule, it is a habit.
"""

from __future__ import annotations

import corrigenda
from corrigenda.formats._xml import mislabelled_utf8, read_source_tree

from tests._paths import EXAMPLES

LIES = EXAMPLES / "bnf-alto-prod-bpt6k5406037v-f40.xml"
TRUTHFUL_LATIN1 = EXAMPLES / "bnf-alto-prod-latin1-control.xml"


def test_the_rule_fires_on_a_declaration_that_lies():
    assert mislabelled_utf8(LIES.read_bytes()) == "ISO-8859-1"


def test_the_rule_stays_silent_on_a_file_that_really_is_latin1():
    """The negative control: same document, genuinely encoded latin-1.

    Its bytes do NOT decode as strict UTF-8, so condition 2 fails and the
    override never happens. Without this, "declares latin-1" would be the
    whole rule, and every honest latin-1 document in the world would be
    re-read as something it is not.
    """
    assert mislabelled_utf8(TRUTHFUL_LATIN1.read_bytes()) is None


def test_a_truthful_utf8_declaration_is_taken_at_its_word():
    """The rule is deliberately one-sided — it never second-guesses UTF-8."""
    assert mislabelled_utf8((EXAMPLES / "X0000002.xml").read_bytes()) is None
    assert mislabelled_utf8((EXAMPLES / "sample.xml").read_bytes()) is None


def test_an_ascii_only_file_is_left_alone_whatever_it_declares(tmp_path):
    """Condition 3: with no non-ASCII byte, both readings are identical.

    Firing here would record an override that changed nothing — a report
    entry with no event behind it, which is the ghost `R1` was about.
    """
    ascii_only = tmp_path / "ascii.xml"
    ascii_only.write_bytes(
        b'<?xml version="1.0" encoding="ISO-8859-1"?>\n<alto><Layout/></alto>'
    )
    assert mislabelled_utf8(ascii_only.read_bytes()) is None


def test_both_files_deliver_the_same_correct_text():
    """The two fixtures differ in their bytes, not in what they say.

    One is UTF-8 behind a latin-1 label, the other is really latin-1. Read
    correctly, both say ``cléricales``. If this ever asserts two different
    strings, the override is doing something other than what it claims.
    """
    witness = "cléricales"
    for fixture in (LIES, TRUTHFUL_LATIN1):
        doc = corrigenda.load(str(fixture))
        texts = [
            line.ocr_text
            for page in doc.manifest.pages
            for line in page.lines
            if witness in line.ocr_text
        ]
        assert texts, f"{fixture.name}: the witness line did not survive"


def test_only_the_lying_file_records_an_override():
    """Same text out, different accounting — and that is the whole point."""
    lying = corrigenda.load(str(LIES)).manifest
    assert lying.source_encodings == {LIES.name: "ISO-8859-1"}

    truthful = corrigenda.load(str(TRUTHFUL_LATIN1)).manifest
    assert truthful.source_encodings == {}


def test_the_reader_is_the_single_way_in_so_the_two_sides_cannot_diverge():
    """Parser and rewriter read through one function, so they agree.

    ALTO and PAGE once disagreed in silence about the same class of event
    (`R4`); two independent readings of one file is how that happens. The
    tree the rewriter gets is the tree the parser got.
    """
    from_reader = read_source_tree(LIES).getroot()
    ns = from_reader.tag[1 : from_reader.tag.index("}")]
    contents = [el.get("CONTENT") for el in from_reader.iter(f"{{{ns}}}String")]
    assert any(text and "cléricales" in text for text in contents)
    assert not any(text and "Ã©" in text for text in contents)
