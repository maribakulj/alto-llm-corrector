"""An identity run gives back the source, byte for byte, plus one record.

``docs/promises.md`` graded "ALTO byte parity when nothing changes" as
**partial**: a sha256 golden and a verbatim SUBSET, but never the whole
serialisation. The distinction is the promise. A golden hash pins that the
output does not move between releases — it says nothing about whether the
output is the SOURCE, and a rewriter that reformatted every file identically
would satisfy it forever. The per-line text check compares texts, which is
blind to attribute order, whitespace between elements, self-closing tags,
namespace declarations and every other byte the XML carries.

What is asserted here is the sentence itself: correct every line with its own
OCR text, and the delivered file is the source re-serialised, differing by
exactly the ``postProcessingStep`` the run is required to add.

**Why this is reachable at all**, and worth guarding. The rewriter serialises
with ``pretty_print=False`` on the tree it parsed, precisely so a user
diffing source against output sees only real changes; the untouched path
leaves an element alone rather than rebuilding it. Both are choices, neither
is forced, and a plausible tidy-up of either — normalising attribute order, or
routing every line through the rebuild for uniformity — would break this
without breaking a single text-level test.

**Sensitivity measured on three mutations**, and the first version of this
file failed the measurement rather than the code. Flipping the rewriter to
``pretty_print=True`` left it green, because the record was cut out of the
TREE and the comparison re-serialised both sides — normalising away exactly
what the promise is about. Cutting it out of the BYTES fixes that. Dropping
the provenance entirely, and disabling the untouched path so identity lines
route elsewhere, both fail too.
"""

from __future__ import annotations

import re

import pytest
from lxml import etree

from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.formats.alto.rewriter import rewrite_alto_file

from tests._paths import EXAMPLES

_CORPORA = ("sample.xml", "X0000002.xml")
_PROVENANCE = "postProcessingStep"


def _identity_output(name: str) -> bytes:
    path = EXAMPLES / name
    document = build_document_manifest([(path, name)])
    for page in document.pages:
        for line in page.lines:
            line.corrected_text = line.ocr_text
    total = sum(len(page.lines) for page in document.pages)
    xml_bytes, metrics, _ = rewrite_alto_file(path, document.pages, "test", "mock")
    # EVERY line, not merely "no rebuild". Checking only fast/slow leaves the
    # subs-only path free to claim them, and that path also emits identical
    # bytes here — so the comparison below would still pass while the premise
    # of this file ("nothing was touched") had quietly stopped being true.
    assert metrics.untouched == total, (
        f"an identity correction must take the UNTOUCHED path on all {total} "
        f"lines; got untouched={metrics.untouched}, subs_only="
        f"{metrics.subs_only}, fast={metrics.fast_path}, slow={metrics.slow_path}"
    )
    return xml_bytes


def _serialise(root: etree._Element) -> bytes:
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=False
    )


#: The run record, cut out of the BYTES rather than out of the tree.
#:
#: Removing it with lxml and re-serialising was the first attempt, and it
#: quietly defeated the point: re-serialising normalises the formatting, so
#: the comparison became one of trees. Measured — flipping the rewriter to
#: ``pretty_print=True`` left every assertion green. A promise about bytes has
#: to be checked on bytes.
_PROVENANCE_BYTES = re.compile(
    rb"<postProcessingStep.*?</postProcessingStep>|<postProcessingStep[^>]*/>",
    re.DOTALL,
)


def _without_provenance(xml: bytes) -> tuple[bytes, int]:
    """The delivered bytes minus the run record, and how many were cut."""
    stripped, removed = _PROVENANCE_BYTES.subn(b"", xml)
    return stripped, removed


@pytest.mark.parametrize("name", _CORPORA)
def test_the_identity_output_is_the_source_reserialised(name: str) -> None:
    """The whole serialisation, not a subset of it.

    Anything the rewriter touches on a file it was asked to leave alone shows
    up here — attribute order, inter-element whitespace, a namespace
    declaration moved, a self-closing tag expanded, the file pretty-printed —
    none of which any text-level or hash-level assertion can see, and none of
    which a TREE comparison can see either.
    """
    delivered, removed = _without_provenance(_identity_output(name))
    source = _serialise(etree.parse(str(EXAMPLES / name)).getroot())
    assert removed == 1, "the run must record itself exactly once"
    assert delivered == source, (
        f"{name}: an identity run changed bytes it was not asked to change. "
        "The output must be the source re-serialised — the rewriter parses "
        "and re-emits without pretty-printing so a user diffing the two sees "
        "only real corrections."
    )


@pytest.mark.parametrize("name", _CORPORA)
def test_the_one_difference_is_the_run_record(name: str) -> None:
    """Asserted rather than stripped and forgotten.

    §11 requires every corrected file to record the pass. A test that removed
    the record and only compared the remainder would stay green on a rewriter
    that stopped writing it — which is how a provenance loss gets waved
    through, and why the count is checked instead of assumed.
    """
    delivered = _identity_output(name)
    assert _PROVENANCE.encode() in delivered
    stripped, removed = _without_provenance(delivered)
    assert removed == 1
    assert len(delivered) > len(stripped)
