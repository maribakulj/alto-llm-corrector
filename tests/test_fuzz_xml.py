"""Plan V4.2 phase 2 — XML fuzzing of the parse boundary.

The property suite (test_properties_hypothesis.py) generates VALID ALTO
and asserts pipeline invariants. This file feeds the parsers HOSTILE
input — malformed XML, encoding mismatches, non-numeric coordinates,
degenerate polygons, incoherent SUBS_* — and asserts the §8.4 error
contract at the library's front door:

    parse either SUCCEEDS, or raises a classified CorrectionError
    (ParseError family). Never an unclassified lxml / OS / ValueError,
    never a TypeError-shaped crash.

Every generator here produces input a caller could actually upload;
nothing relies on internal APIs.
"""

from __future__ import annotations

import collections
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from saknussemm.core.schemas import DocumentManifest
from saknussemm.errors import CorrectionError, ParseError
from saknussemm.formats.alto.parser import (
    build_document_manifest as build_alto_manifest,
)
from saknussemm.formats.page.parser import (
    build_document_manifest as build_page_manifest,
)

_Builder = Callable[[Sequence[tuple[Path, str]]], DocumentManifest]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(payload: bytes, build: _Builder) -> str:
    """Parse *payload* and return which of the contract's outcomes happened.

    ``"parsed"`` when a manifest came back with lines, ``"parsed-empty"``
    when it came back with none, ``"ParseError"`` when the failure was
    classified in the promised family. Anything else raises here.

    Two things this stopped being lenient about on 2026-08-17. It caught
    ``CorrectionError``, which is an alias for the **base** class — so a
    ``ConfigurationError`` or a ``ProviderError`` escaping the parser
    counted as the contract holding, while the promise at the top of this
    file is the ``ParseError`` family specifically. Measured over 2400
    draws across the six generators: every classified failure is already a
    ``ParseError``, so naming it costs nothing today and makes the promise
    checkable. And it returned nothing, which left the callers unable to
    say whether a generator ever reached the code being fuzzed —
    :func:`test_each_generator_reaches_the_semantics` is why that matters.
    """
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "fuzz.xml"
        p.write_bytes(payload)
        try:
            manifest = build([(p, "fuzz.xml")])
        except ParseError:
            return "ParseError"
        except CorrectionError as exc:  # classified, but not as promised
            raise AssertionError(
                f"the parser raised {type(exc).__name__}, which is classified "
                "but outside the ParseError family this file's contract "
                "names. Either it belongs in that family, or the contract at "
                f"the top of this file is wrong. ({exc})"
            ) from exc
    lines = sum(len(page.lines) for page in manifest.pages)
    return "parsed" if lines else "parsed-empty"


def _parse_bytes_alto(payload: bytes) -> str:
    return _parse(payload, build_alto_manifest)


def _parse_bytes_page(payload: bytes) -> str:
    return _parse(payload, build_page_manifest)


# An attribute value that may or may not be a number: the strict
# coordinate policy must classify the failure, not leak a ValueError.
_ATTR_VALUE = st.one_of(
    st.integers(-(10**9), 10**9).map(str),
    st.floats(allow_nan=True, allow_infinity=True).map(str),
    st.just(""),
    st.text(max_size=12),
)

# Free text that may contain XML metacharacters once escaped — the
# builder escapes it, so this fuzzes CONTENT, not well-formedness.
_FREE_TEXT = st.text(max_size=40)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# 1. Arbitrary bytes — the rawest contract
# ---------------------------------------------------------------------------


@settings(max_examples=80, deadline=None)
@given(payload=st.binary(max_size=2048))
def test_arbitrary_bytes_never_crash_alto_unclassified(payload: bytes) -> None:
    _parse_bytes_alto(payload)


@settings(max_examples=80, deadline=None)
@given(payload=st.binary(max_size=2048))
def test_arbitrary_bytes_never_crash_page_unclassified(payload: bytes) -> None:
    _parse_bytes_page(payload)


# ---------------------------------------------------------------------------
# 2. Truncations & mutations of a real document
# ---------------------------------------------------------------------------

_VALID_ALTO = b"""<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Layout><Page ID="P1" WIDTH="1000" HEIGHT="1400">
    <PrintSpace>
      <TextBlock ID="B1" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="200">
        <TextLine ID="L1" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="40">
          <String CONTENT="premiere" HPOS="10" VPOS="10" WIDTH="200" HEIGHT="40"/>
        </TextLine>
        <TextLine ID="L2" HPOS="10" VPOS="60" WIDTH="900" HEIGHT="40">
          <String CONTENT="seconde" HPOS="10" VPOS="60" WIDTH="200" HEIGHT="40"/>
        </TextLine>
      </TextBlock>
    </PrintSpace>
  </Page></Layout>
</alto>
"""


@settings(max_examples=80, deadline=None)
@given(cut=st.integers(0, len(_VALID_ALTO) - 1))
def test_truncated_alto_is_classified(cut: int) -> None:
    """Any prefix of a valid document parses or fails classified."""
    _parse_bytes_alto(_VALID_ALTO[:cut])


@settings(max_examples=80, deadline=None)
@given(
    pos=st.integers(0, len(_VALID_ALTO) - 1),
    byte=st.integers(0, 255),
)
def test_single_byte_mutation_is_classified(pos: int, byte: int) -> None:
    """Flipping one byte anywhere must never produce an unclassified crash."""
    mutated = bytes(_VALID_ALTO[:pos]) + bytes([byte]) + bytes(_VALID_ALTO[pos + 1 :])
    _parse_bytes_alto(mutated)


@settings(max_examples=40, deadline=None)
@given(
    encoding_label=st.sampled_from(
        ["UTF-8", "UTF-16", "ISO-8859-1", "koi8-r", "bogus-enc"]
    )
)
def test_encoding_declaration_mismatch_is_classified(encoding_label: str) -> None:
    """Declared encoding ≠ actual bytes: parse or ParseError, no leak."""
    body = _VALID_ALTO.replace(
        b'encoding="UTF-8"', f'encoding="{encoding_label}"'.encode()
    )
    _parse_bytes_alto(body)


# ---------------------------------------------------------------------------
# 3. Structured ALTO fuzz — hostile attributes & SUBS_* combinations
# ---------------------------------------------------------------------------


@st.composite
def hostile_alto(draw: st.DrawFn) -> bytes:
    """Well-formed XML, hostile SEMANTICS: random coordinate values,
    random/incoherent SUBS_TYPE / SUBS_CONTENT / HYP, arbitrary text."""
    n_lines = draw(st.integers(1, 5))
    lines: list[str] = []
    for i in range(n_lines):
        subs_type = draw(
            st.sampled_from(["", "HypPart1", "HypPart2", "HYPHEN", "hyppart1", "junk"])
        )
        subs_content = draw(st.one_of(st.just(""), _FREE_TEXT))
        content = _esc(draw(_FREE_TEXT))
        hpos = draw(_ATTR_VALUE)
        attrs = f'HPOS="{_esc(hpos)}" VPOS="{i * 50}" WIDTH="100" HEIGHT="40"'
        subs = ""
        if subs_type:
            subs = f' SUBS_TYPE="{subs_type}"'
            if subs_content:
                subs += f' SUBS_CONTENT="{_esc(subs_content)}"'
        hyp = '<HYP CONTENT="-"/>' if draw(st.booleans()) else ""
        maybe_id = f'ID="L{i}"' if draw(st.booleans()) else ""
        lines.append(
            f"<TextLine {maybe_id} {attrs}>"
            f'<String CONTENT="{content}"{subs} {attrs}/>{hyp}'
            f"</TextLine>"
        )
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">'
        '<Layout><Page ID="P1" WIDTH="1000" HEIGHT="1400"><PrintSpace>'
        '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="900" HEIGHT="900">'
        + "".join(lines)
        + "</TextBlock></PrintSpace></Page></Layout></alto>"
    )
    return doc.encode("utf-8")


@settings(max_examples=120, deadline=None)
@given(payload=hostile_alto())
def test_hostile_alto_semantics_are_classified(payload: bytes) -> None:
    _parse_bytes_alto(payload)


# ---------------------------------------------------------------------------
# 4. Structured PAGE fuzz — degenerate polygons
# ---------------------------------------------------------------------------

_POINTS = st.one_of(
    st.just(""),
    st.just("0,0"),
    st.just("1,2 3"),
    st.just("a,b c,d"),
    st.just("-5,-5 -1,-1"),
    st.just("999999999,999999999 0,0"),
    st.text(alphabet="0123456789,- .", max_size=30),
)


@st.composite
def hostile_page(draw: st.DrawFn) -> bytes:
    n_lines = draw(st.integers(1, 4))
    lines = []
    for i in range(n_lines):
        pts = draw(_POINTS)
        text = _esc(draw(_FREE_TEXT))
        lines.append(
            f'<TextLine id="l{i}"><Coords points="{_esc(pts)}"/>'
            f"<TextEquiv><Unicode>{text}</Unicode></TextEquiv></TextLine>"
        )
    region_pts = draw(_POINTS)
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">'
        f'<Page imageFilename="img.jpg" imageWidth="{_esc(draw(_ATTR_VALUE))}"'
        f' imageHeight="1400">'
        f'<TextRegion id="r1"><Coords points="{_esc(region_pts)}"/>'
        + "".join(lines)
        + "</TextRegion></Page></PcGts>"
    )
    return doc.encode("utf-8")


@settings(max_examples=120, deadline=None)
@given(payload=hostile_page())
def test_hostile_page_polygons_are_classified(payload: bytes) -> None:
    _parse_bytes_page(payload)


# ---------------------------------------------------------------------------
# 5. Does any of the above reach the code it claims to fuzz?
# ---------------------------------------------------------------------------
#
# A fuzz test that only ever exercises the front door is green forever and
# says nothing about the semantics behind it. Every generator here was
# measured on 2026-08-17, `database=None` so no stored example biases the
# count — and measured over **twelve seeds**, because the first attempt
# calibrated on a single 400-draw run and the floor it produced failed
# inside the full suite, where `pytest-randomly` reseeds the entropy. One
# measurement of a variable rate is not a measurement of that rate.
#
#   ==================  ======  ======  ======  =========================
#   generator              min  median     max  note
#   ==================  ======  ======  ======  =========================
#   st.binary -> ALTO    0.0 %   0.0 %   0.0 %  never valid XML, by nature
#   st.binary -> PAGE    0.0 %   0.0 %   0.0 %  idem
#   truncations         0.33 %  0.33 %  0.33 %  exactly the untruncated one
#   one-byte mutations  9.33 % 14.17 % 18.33 %  genuinely reaches the parser
#   hostile_alto        2.67 %  4.83 %  9.33 %  a 3.5x spread across seeds
#   hostile_page        40.7 %  51.8 %  60.7 %  the most productive of the six
#   ==================  ======  ======  ======  =========================
#
# The audit reported `hostile_alto` at 1 % useful. A single run here said
# 9.5 %, which was near the top of its own spread; the median is 4.8 %. So
# the audit undersold it by about 5x, not by 10x as that first run implied.
#
# Each floor is half the **minimum** across those seeds, not half the mean.
# What that buys is narrow and worth stating: these catch a generator that
# has collapsed — one producing nothing well-formed at all, which is how a
# whole section of this file would go quietly vacuous. They do not catch
# gradual degradation, and a floor tight enough to catch that would flake
# on the spread above. The two `st.binary` rows are pinned at zero **on
# purpose** and asserted as zero rather than skipped.

_MEASURED_FLOORS: dict[str, float] = {
    "truncations": 0.0016,
    "one-byte mutations": 0.046,
    "hostile_alto": 0.013,
    "hostile_page": 0.20,
}

_TRUNCATIONS = st.integers(0, len(_VALID_ALTO) - 1).map(lambda c: _VALID_ALTO[:c])
_MUTATIONS = st.tuples(st.integers(0, len(_VALID_ALTO) - 1), st.integers(0, 255)).map(
    lambda t: _VALID_ALTO[: t[0]] + bytes([t[1]]) + _VALID_ALTO[t[0] + 1 :]
)

_GENERATORS: list[tuple[str, st.SearchStrategy[bytes], _Builder]] = [
    ("truncations", _TRUNCATIONS, build_alto_manifest),
    ("one-byte mutations", _MUTATIONS, build_alto_manifest),
    ("hostile_alto", hostile_alto(), build_alto_manifest),
    ("hostile_page", hostile_page(), build_page_manifest),
]


def _tally(
    strategy: st.SearchStrategy[bytes], build: _Builder, draws: int
) -> tuple[collections.Counter[str], int]:
    counter: collections.Counter[str] = collections.Counter()

    @settings(
        max_examples=draws,
        deadline=None,
        database=None,
        suppress_health_check=list(HealthCheck),
    )
    @given(payload=strategy)
    def run(payload: bytes) -> None:
        counter[_parse(payload, build)] += 1

    run()
    return counter, sum(counter.values())


@pytest.mark.parametrize(
    ("label", "strategy", "build"), _GENERATORS, ids=[g[0] for g in _GENERATORS]
)
def test_each_generator_reaches_the_semantics(
    label: str, strategy: st.SearchStrategy[bytes], build: _Builder
) -> None:
    """A generator whose every example dies at the front door fuzzes a door.

    The point of sections 2–4 is the code *behind* the parse: coordinate
    policy, ``SUBS_*`` coherence, degenerate polygons. If a generator drifts
    so that nothing well-formed comes out of it any more, all of that goes
    untested and every test here stays green — which is exactly the failure
    mode this file existed to prevent in the parsers.
    """
    counter, total = _tally(strategy, build, 300)
    reached = counter["parsed"] + counter["parsed-empty"]
    floor = _MEASURED_FLOORS[label]
    assert reached / total >= floor, (
        f"{label}: only {reached}/{total} examples reached a successful parse, "
        f"below the floor {floor:.1%} (half the rate measured 2026-08-17). "
        f"Outcomes: {dict(counter)}. The property tests using this generator "
        "are still green, and are now checking that malformed XML is rejected "
        "rather than the semantics they were written for."
    )


def test_random_bytes_reach_nothing_and_that_is_the_finding() -> None:
    """Pinned at zero, deliberately, because zero is the honest number.

    ``st.binary`` produces valid XML with probability nil, so the two tests
    in section 1 establish exactly one thing: arbitrary bytes are refused as
    a ``ParseError``. That is worth asserting — it is the rawest form of the
    §8.4 contract, and before 2026-08-17 not even the *class* was checked.
    It is not worth mistaking for semantic coverage, which is what an
    unmeasured "we fuzz the parser with random bytes" reads as.

    Asserted rather than deleted or skipped: if a future parser change made
    random bytes parse, that would be a serious finding, and this is where
    it would surface.
    """
    for label, build in (("ALTO", build_alto_manifest), ("PAGE", build_page_manifest)):
        counter, total = _tally(st.binary(max_size=2048), build, 200)
        reached = counter["parsed"] + counter["parsed-empty"]
        assert reached == 0, (
            f"{label}: {reached}/{total} random byte strings parsed into a "
            f"manifest. Outcomes: {dict(counter)}. Either the generator now "
            "produces XML — in which case say so and give this a floor like "
            "the other generators — or the parser accepts something it should "
            "not, which is the more interesting possibility."
        )
        assert counter["ParseError"] == total, (
            f"{label}: {total - counter['ParseError']} of {total} random byte "
            f"strings failed as something other than a ParseError. "
            f"Outcomes: {dict(counter)}."
        )
