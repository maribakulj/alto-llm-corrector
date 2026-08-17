"""The guards must know the whole break-mark repertoire, not just ``-`` (L5).

``HYPHEN_CHARS`` has six members and the parsers use all of them, so a line
can legitimately be a PART1 by ending in ``⸗`` or ``¬``. Five guard sites
nonetheless tested the ASCII hyphen alone — ``endswith("-")``,
``rstrip("-")`` — which is not a corner case in this repository:

    PART1/BOTH lines by trailing mark, over the 1711 ALTO/PAGE lines of
    ``examples/`` and the BnL corpus:
        U+002D  -   331
        U+2E17  ⸗    24
        U+00AC  ¬     8

**32 of 363 hyphenated lines**, 8.8%, fell outside every one of those checks.
Not latent: the BnL corpus (in the bench repository since 2026-08-16) is Fraktur ground truth and its break mark is
``⸗``.

Each test below states the consequence rather than the code shape, and each
fails on the ASCII-only version.
"""

from __future__ import annotations

from pathlib import Path


import pytest

from saknussemm.core.hyphenation import _part1_text_migrated
from saknussemm.core.pairing import (
    HYPHEN_CHARS,
    ends_with_break_mark,
    strip_trailing_break_marks,
)

#: Every mark a real document in this repo actually breaks words with, plus
#: the rest of the repertoire so a future member is covered for free.
_MARKS = list(HYPHEN_CHARS)


class TestThePredicates:
    @pytest.mark.parametrize("mark", _MARKS)
    def test_every_repertoire_mark_is_recognised(self, mark: str) -> None:
        assert ends_with_break_mark(f"admini{mark}")
        assert ends_with_break_mark(f"admini{mark}   ")  # trailing whitespace

    @pytest.mark.parametrize("mark", _MARKS)
    def test_every_repertoire_mark_is_stripped(self, mark: str) -> None:
        assert strip_trailing_break_marks(f"admini{mark}") == "admini"

    def test_a_line_with_no_mark_is_not_one(self) -> None:
        assert not ends_with_break_mark("administration")
        assert strip_trailing_break_marks("administration") == "administration"

    def test_the_predicate_does_not_re_impose_the_alphabetic_heuristic(self) -> None:
        """``trailing_hyphen_char`` requires a letter before the mark, to keep
        ``1789-`` from pairing. This predicate must NOT: its callers already
        know the line breaks a word (the role says so, possibly from an
        explicit ``SUBS_TYPE``), and re-checking would silently un-guard an
        explicitly-marked line that happens to end in a digit."""
        from saknussemm.core.pairing import trailing_hyphen_char

        assert trailing_hyphen_char("en 1789-", HYPHEN_CHARS) is None
        assert ends_with_break_mark("en 1789-")

    def test_a_mark_outside_the_repertoire_is_left_alone(self) -> None:
        # An en dash is not a word-break mark here (L6) and must not be
        # stripped or recognised — that would change what pairs.
        assert not ends_with_break_mark("dialogue–")
        assert strip_trailing_break_marks("dialogue–") == "dialogue–"


class TestThePart1GrowthGuard:
    """``_part1_text_migrated`` compares OCR against correction on bare text.

    With ``rstrip("-")`` a ``⸗``-terminated line kept its mark, so the last
    word measured ONE CHARACTER LONGER than it is — and the guard's threshold
    is a character count (``part1_last_word_char_growth``, default 3). The
    cases below sit exactly on that boundary, because that is the only place
    a one-character error can change an answer: a growth of 4 real characters
    reads as 3 with the mark attached, and 3 does not exceed 3.
    """

    @pytest.mark.parametrize("mark", _MARKS)
    def test_a_word_completion_on_the_threshold_is_caught(self, mark: str) -> None:
        # "adm⸗" (3 bare chars) -> "admini" (6): growth 3, not > 3, allowed.
        # "adm⸗" -> "adminis" (7): growth 4 > 3 -> refused. With the mark
        # counted the bare OCR word is 4 chars and the growth reads 3: the
        # completion is waved through.
        assert _part1_text_migrated(f"le adm{mark}", "le adminis")

    @pytest.mark.parametrize("mark", _MARKS)
    def test_the_case_just_under_the_threshold_is_still_allowed(
        self, mark: str
    ) -> None:
        # Growth of exactly 3 real characters: allowed before AND after, so
        # the fix cannot be a blanket tightening.
        assert not _part1_text_migrated(f"le adm{mark}", "le admini")

    @pytest.mark.parametrize("mark", _MARKS)
    def test_an_ordinary_correction_still_passes(self, mark: str) -> None:
        # A spelling fix of the same length must NOT trip the guard — the
        # generalisation must not make it fire more often.
        assert not _part1_text_migrated(f"il est ncces{mark}", f"il est néces{mark}")

    @pytest.mark.parametrize("mark", _MARKS)
    def test_the_mark_itself_is_not_counted_as_growth(self, mark: str) -> None:
        # Identity: the bare texts are equal, so nothing grew.
        assert not _part1_text_migrated(f"il est néces{mark}", f"il est néces{mark}")


class TestTheFusionCheck:
    """The validator refuses a PART1 line that contains the whole logical
    word (``SUBS_CONTENT``) — the LLM fused the pair into one line.

    The comparison is against the line's LAST word, taken after stripping the
    break mark. With ``rstrip("-")`` a ``⸗`` stayed glued to that word, the
    comparison never matched, and a real fusion passed validation.
    """

    @pytest.mark.parametrize("mark", _MARKS)
    def test_a_fusion_is_refused_whatever_the_mark(self, mark: str) -> None:
        from saknussemm.core.validator import (
            HyphenIntegrityError,
            validate_llm_response,
        )

        # The realistic fusion, and the one the ASCII-only strip missed: the
        # model completes the word AND leaves the break mark in place, so the
        # line reads "il est nécessaires⸗". Stripping only "-" leaves
        # "nécessaires⸗", which never equals the logical word — the fusion
        # passed validation and PART2's text had already migrated up.
        with pytest.raises(HyphenIntegrityError, match="fusion"):
            validate_llm_response(
                {
                    "lines": [
                        {
                            "line_id": "L1",
                            "corrected_text": f"il est nécessaires{mark}",
                        }
                    ]
                },
                ["L1"],
                {"L1": "L2", "L2": "L1"},
                {"L1": f"il est néces{mark}", "L2": "saires"},
                {"L1": "nécessaires"},
            )

    @pytest.mark.parametrize("mark", _MARKS)
    def test_an_unfused_correction_passes(self, mark: str) -> None:
        from saknussemm.core.validator import validate_llm_response

        # Same pair, a proposal that keeps the fragment a fragment.
        validate_llm_response(
            {"lines": [{"line_id": "L1", "corrected_text": f"il est néces{mark}"}]},
            ["L1"],
            {"L1": "L2", "L2": "L1"},
            {"L1": f"il est néces{mark}", "L2": "saires"},
            {"L1": "nécessaires"},
        )


class TestTheOrphanGuardEndToEnd:
    """A PART1 the reconciler never got to, whose correction dropped the break
    mark, must fall back to its OCR text — the mark is the only thing telling
    a reader the word continues.

    Pinned through a real run because the guard sits inside acceptance, and
    the fallback REASON is part of what the run owes its host.
    """

    @pytest.mark.parametrize("mark", ["-", "⸗", "¬"])
    def test_a_dropped_break_mark_falls_back(self, tmp_path: Path, mark: str) -> None:
        from saknussemm import CorrectionPipeline
        from saknussemm.core.editing import EditScript, ReplaceLine
        from saknussemm.core.protocols import ProducerMetadata
        from saknussemm.core.schemas import LineStatus
        from saknussemm.formats.alto.parser import build_document_manifest

        ns = "http://www.loc.gov/standards/alto/ns-v3#"
        # One page, ONE line: nothing follows, so the PART1 is an orphan the
        # reconciler cannot pair and acceptance is the only thing guarding it.
        xml = (
            f'<?xml version="1.0"?><alto xmlns="{ns}"><Layout>'
            '<Page ID="P1" WIDTH="600" HEIGHT="200">'
            '<PrintSpace HPOS="0" VPOS="0" WIDTH="600" HEIGHT="200">'
            '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="600" HEIGHT="40">'
            '<TextLine ID="L1" HPOS="0" VPOS="0" WIDTH="300" HEIGHT="30">'
            f'<String ID="S1" CONTENT="admini{mark}" HPOS="0" VPOS="0" '
            'WIDTH="300" HEIGHT="30"/>'
            "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
        )
        path = tmp_path / "p.xml"
        path.write_text(xml, encoding="utf-8")
        doc = build_document_manifest([(path, path.name)])
        line = doc.pages[0].lines[0]
        assert line.hyphen_role.value in ("HypPart1", "HypBoth"), (
            f"fixture check: {mark!r} must make this a PART1"
        )

        class _CompletesTheWord:
            wants_geometry = False
            wants_image = False

            async def produce(self, payload, *, options):
                return (
                    EditScript(
                        ops=tuple(
                            ReplaceLine(line_id=ln.line_id, text="administration")
                            for ln in payload.lines
                        )
                    ),
                    None,
                )

        class _Null:
            def on_event(self, *a, **k):
                pass

        pipeline = CorrectionPipeline(
            producer=_CompletesTheWord(),
            observer=_Null(),
            producer_metadata=ProducerMetadata(name="test", implementation="v1"),
        )
        result = pipeline.run_sync(
            document_manifest=doc, source_files={path.name: path}
        )

        outcome = result.report.lines[0]
        assert outcome.decision.status == LineStatus.FALLBACK.value, (
            f"a dropped {mark!r} was accepted: the delivered line no longer "
            "says the word continues"
        )
        assert outcome.decision.final_text == f"admini{mark}"
        assert outcome.decision.reason is not None
        assert outcome.decision.reason.code == "orphan_hyphen_completed"


# ---------------------------------------------------------------------------
# L5 — an empty line is skipped over, not treated as a wall
# ---------------------------------------------------------------------------


class TestAnEmptyLineIsNotAPartner:
    """The rule the cross-PAGE walk already lived by, applied inside a page.

    ``link_hyphen_pairs`` took ``lines[i + 1]`` as the continuation. A blank
    line between a PART1 and its real continuation therefore became the
    PART2: it holds no text, so nothing reconciles, the pair-drift guards
    never run, and the actual continuation is left unlinked — the same
    consequence the empty-PAGE defect had, one scale down.

    Latent on this repo's corpora — 0 empty lines in 1711 — which is why it
    needs a test rather than a measurement.
    """

    @staticmethod
    def _page(texts: list[str]):
        from saknussemm.core.schemas import Coords, LineManifest, PageManifest

        return PageManifest(
            page_id="P1",
            page_index=0,
            source_file="f.xml",
            page_width=600,
            page_height=800,
            blocks=[],
            lines=[
                LineManifest(
                    line_id=f"L{i}",
                    page_id="P1",
                    block_id="B1",
                    line_order_global=i,
                    line_order_in_block=i,
                    coords=Coords(hpos=0, vpos=i * 40, width=300, height=30),
                    ocr_text=text,
                )
                for i, text in enumerate(texts)
            ],
        )

    def _linked(self, texts: list[str]):
        from saknussemm.core.pairing import link_hyphen_pairs
        from saknussemm.core.schemas import HyphenRole, PairingPolicy
        from saknussemm.formats.page.parser import _assign_hyphen_roles

        page = self._page(texts)
        _assign_hyphen_roles(page.lines)
        link_hyphen_pairs(page.lines, PairingPolicy(geometric_checks=False))
        return {lm.line_id: lm for lm in page.lines}, HyphenRole

    def test_the_blank_line_does_not_become_the_partner(self) -> None:
        by_id, role = self._linked(["une admini", "", "stration"])
        # Fixture check: the first line must actually be a PART1.
        assert by_id["L0"].hyphen_role is role.NONE  # no mark -> not a break

    def test_a_word_spanning_a_blank_line_is_still_linked(self) -> None:
        by_id, role = self._linked(["une admini-", "", "stration complète"])
        assert by_id["L0"].hyphen_role is role.PART1
        # The link skips the blank and lands on the text.
        assert by_id["L0"].hyphen_pair_line_id == "L2"
        assert by_id["L2"].hyphen_role is role.PART2
        # And the blank line is left alone: it is not a hyphen member.
        assert by_id["L1"].hyphen_role is role.NONE
        assert by_id["L1"].hyphen_pair_line_id is None

    def test_a_whitespace_only_line_counts_as_blank(self) -> None:
        by_id, _role = self._linked(["une admini-", "   ", "stration"])
        assert by_id["L0"].hyphen_pair_line_id == "L2"

    def test_several_blank_lines_are_all_skipped(self) -> None:
        by_id, _role = self._linked(["une admini-", "", "", "", "stration"])
        assert by_id["L0"].hyphen_pair_line_id == "L4"

    def test_the_ordinary_adjacent_case_is_unchanged(self) -> None:
        by_id, role = self._linked(["une admini-", "stration complète"])
        assert by_id["L0"].hyphen_pair_line_id == "L1"
        assert by_id["L1"].hyphen_role is role.PART2

    def test_a_blank_last_line_leaves_the_break_unpaired(self) -> None:
        """No text after the break at all: the PART1 stays an orphan and is
        counted as one, rather than being paired with nothing."""
        from saknussemm.core.pairing import unpaired_break_refs

        by_id, _role = self._linked(["une admini-", ""])
        assert by_id["L0"].hyphen_pair_line_id is None
        page = self._page(["une admini-", ""])
        from saknussemm.core.pairing import link_hyphen_pairs
        from saknussemm.core.schemas import PairingPolicy
        from saknussemm.formats.page.parser import _assign_hyphen_roles

        _assign_hyphen_roles(page.lines)
        link_hyphen_pairs(page.lines, PairingPolicy(geometric_checks=False))
        assert len(unpaired_break_refs([page])) == 1


class TestAnEmptyLineAtAPageSeam:
    """Same rule at the seam. ``link_cross_page_hyphens`` compared
    ``lines[-1]`` with ``lines[0]``, so one blank line at the foot of a page
    or the head of the next hid a word that spans it."""

    @staticmethod
    def _pages(first: list[str], second: list[str]):
        from saknussemm.core.schemas import Coords, LineManifest, PageManifest

        def page(pid: str, index: int, texts: list[str]) -> PageManifest:
            return PageManifest(
                page_id=pid,
                page_index=index,
                source_file="f.xml",
                page_width=600,
                page_height=800,
                blocks=[],
                lines=[
                    LineManifest(
                        line_id=f"{pid}_L{i}",
                        page_id=pid,
                        block_id="B1",
                        line_order_global=i,
                        line_order_in_block=i,
                        coords=Coords(hpos=0, vpos=i * 40, width=300, height=30),
                        ocr_text=text,
                    )
                    for i, text in enumerate(texts)
                ],
            )

        return [page("P1", 0, first), page("P2", 1, second)]

    def _link(self, first: list[str], second: list[str]):
        from saknussemm.core.pairing import link_cross_page_hyphens
        from saknussemm.core.schemas import PairingPolicy
        from saknussemm.formats.page.parser import _assign_hyphen_roles

        pages = self._pages(first, second)
        for page in pages:
            _assign_hyphen_roles(page.lines)
        link_cross_page_hyphens(pages, PairingPolicy(geometric_checks=False))
        return {lm.line_id: lm for page in pages for lm in page.lines}

    def test_a_blank_line_at_the_foot_of_the_page_is_skipped(self) -> None:
        by_id = self._link(["texte", "une admini-", ""], ["stration suite"])
        assert by_id["P1_L1"].hyphen_pair_line_id == "P2_L0"
        assert by_id["P1_L1"].hyphen_pair_page_id == "P2"

    def test_a_blank_line_at_the_head_of_the_next_page_is_skipped(self) -> None:
        by_id = self._link(["une admini-"], ["", "stration suite"])
        assert by_id["P1_L0"].hyphen_pair_line_id == "P2_L1"

    def test_blanks_on_both_sides_of_the_seam(self) -> None:
        by_id = self._link(["une admini-", ""], ["  ", "stration"])
        assert by_id["P1_L0"].hyphen_pair_line_id == "P2_L1"

    def test_the_ordinary_seam_is_unchanged(self) -> None:
        by_id = self._link(["une admini-"], ["stration suite"])
        assert by_id["P1_L0"].hyphen_pair_line_id == "P2_L0"


# ---------------------------------------------------------------------------
# The generators must reach the repertoire too — L5's blind spot
# ---------------------------------------------------------------------------


def test_the_generators_draw_their_break_mark_from_the_repertoire() -> None:
    """`L5` swept five guard sites and left the GENERATORS on ASCII.

    Measured 2026-08-17 over 200 draws of each: both emitted ``-`` and none
    of the other five, ever. So the ten Hypothesis properties that touch
    hyphenation ran on one sixth of the repertoire — while this repository's
    own corpus marks **every** break with ``¬`` and the bench's Fraktur
    ground truth uses ``⸗``. The mark the properties exercised was the one
    the corpus does not use.

    This draws documents and looks at what came out. The first version of it
    scanned the source for a hard-coded ``CONTENT="-"`` and for a mention of
    ``HYPHEN_CHARS`` — and **did not catch** the obvious regression, because
    pinning ``break_mark = "-"`` removes neither the literal nor the import.
    A shape check for a behavioural property, which is the mistake this whole
    effort exists to find.

    Sampling is reliable here rather than approximate: the mark is drawn
    uniformly from six values, so 60 documents seeing fewer than three
    distinct marks has a probability of about one in a billion.
    """
    from hypothesis import HealthCheck, given, settings

    from tests._alto_gen import rich_alto_documents

    for label, strategy in (
        ("rich_alto_documents", rich_alto_documents()),
        ("alto_documents", _alto_documents_strategy()),
    ):
        seen: set[str] = set()

        @settings(
            max_examples=60, deadline=None, suppress_health_check=list(HealthCheck)
        )
        @given(document=strategy)
        def collect(document: object) -> None:
            xml = document[0] if isinstance(document, tuple) else document
            seen.update(mark for mark in HYPHEN_CHARS if f'CONTENT="{mark}"' in xml)  # type: ignore[operator]

        collect()
        assert len(seen) >= 3, (
            f"{label} produced only {sorted(seen)!r} over 60 documents. The "
            "break mark must be drawn from HYPHEN_CHARS: a generator that "
            "emits one of six marks makes every hyphenation property a test "
            "of that one mark, and the corpus uses a different one."
        )


def _alto_documents_strategy() -> object:
    """Imported lazily — ``test_properties_hypothesis`` imports this package."""
    from tests.test_properties_hypothesis import alto_documents

    return alto_documents()
