"""What the two lines of a broken word are allowed to become.

``reconcile_hyphen_pair`` is the app deciding while the producer informs:
it takes the two corrected texts and either writes them onto the two
physical lines or falls the pair back to its OCR. These cases are the
boundary of that acceptance — absorption in the explicit and heuristic
modes, a break mark outside ASCII, and the subs content a BOTH line
carries forward.
"""

from __future__ import annotations

from corrigenda.core.hyphenation import reconcile_hyphen_pair
from corrigenda.core.schemas import HyphenRole

from tests.hyphenation._lines import _line


def test_explicit_subs_join_accepts_non_ascii_break_char():
    # Fraktur double-oblique hyphen U+2E17 ("⸗"). The corrected pair keeps it
    # and the subs join must still match "Aufmerksamkeit".
    part1 = _line(
        "p1", "Aufmerksam⸗", role=HyphenRole.PART1, subs="Aufmerksamkeit", explicit=True
    )
    part2 = _line("p2", "keit", role=HyphenRole.PART2)
    f1, f2, subs = reconcile_hyphen_pair(part1, part2, "Aufmerksam⸗", "keit")
    # Not a fallback: the corrected texts and subs survive.
    assert f1 == "Aufmerksam⸗"
    assert f2 == "keit"
    assert subs == "Aufmerksamkeit"


def test_explicit_part2_absorption_falls_back():
    part1 = _line(
        "p1", "neces-", role=HyphenRole.PART1, subs="necessaires", explicit=True
    )
    part2 = _line("p2", "saires", role=HyphenRole.PART2)
    # PART2 absorbed "du roi" from the next line — boundary join still
    # matches subs, but the physical line grew.
    f1, f2, subs = reconcile_hyphen_pair(part1, part2, "neces-", "saires du roi")
    assert (f1, f2, subs) == (part1.ocr_text, part2.ocr_text, None)


def test_explicit_part2_no_absorption_accepted():
    part1 = _line(
        "p1", "neces-", role=HyphenRole.PART1, subs="necessaires", explicit=True
    )
    part2 = _line("p2", "saires", role=HyphenRole.PART2)
    f1, f2, subs = reconcile_hyphen_pair(part1, part2, "neces-", "saires")
    assert (f1, f2, subs) == ("neces-", "saires", "necessaires")


def test_f1_heuristic_part2_absorption_falls_back():
    """Heuristic pair: PART2 'saires' → 'saires du roi' absorbed the next
    physical line's words. The boundary word is unchanged so the
    boundary-word guard passes, and the floor-3 expansion allowance in
    _part2_text_migrated is too permissive for a short PART2 — pre-fix
    the merged line survived, violating lines-never-merge."""
    part1 = _line("p1", "néces-", role=HyphenRole.PART1, explicit=False)
    part2 = _line(
        "p2",
        "saires",
        role=HyphenRole.PART2,
        explicit=False,
    )
    f1, f2, subs = reconcile_hyphen_pair(part1, part2, "néces-", "saires du roi")
    assert (f1, f2, subs) == (part1.ocr_text, part2.ocr_text, None)


def test_f1_heuristic_part2_same_word_count_still_accepted():
    """The growth guard must not reject legitimate same-word-count
    corrections in heuristic mode."""
    part1 = _line("p1", "boule-", role=HyphenRole.PART1, explicit=False)
    part2 = _line("p2", "vard du rol", role=HyphenRole.PART2, explicit=False)
    f1, f2, subs = reconcile_hyphen_pair(part1, part2, "boule-", "vard du roi")
    assert (f1, f2, subs) == ("boule-", "vard du roi", None)


def test_f1_explicit_no_subs_part2_absorption_falls_back():
    """Twin branch (F1): explicit pair WITHOUT usable SUBS_CONTENT takes
    the boundary-word path, which pre-fix had the same absorption gap as
    the heuristic branch."""
    part1 = _line("p1", "néces-", role=HyphenRole.PART1, subs=None, explicit=True)
    part2 = _line("p2", "saires", role=HyphenRole.PART2)
    f1, f2, subs = reconcile_hyphen_pair(part1, part2, "néces-", "saires du roi")
    assert (f1, f2, subs) == (part1.ocr_text, part2.ocr_text, None)


def test_f1_both_line_forward_subs_preserved_on_acceptance():
    """Heuristic-branch subs semantics preserved: a BOTH line's forward
    reconcile passes subs_content explicitly; acceptance must keep it."""
    part1 = _line("m1", "frag-", role=HyphenRole.BOTH, explicit=False)
    part2 = _line("m2", "ment suivant", role=HyphenRole.PART2)
    f1, f2, subs = reconcile_hyphen_pair(
        part1,
        part2,
        "frag-",
        "ment suivant",
        subs_content="fragment",
        source_explicit=False,
    )
    assert (f1, f2, subs) == ("frag-", "ment suivant", "fragment")
