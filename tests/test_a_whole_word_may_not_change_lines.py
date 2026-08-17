"""No text migrates between physical lines — including a word moved intact.

This is the invariant the repository states most often (`CLAUDE.md`:
*Lines never merge: No text migrates between lines*) and the Stage-C guard
exists to hold it regardless of hyphen role.

It modelled one shape of violation: a word **completed** across the seam,
fragment plus fragment, judged by similarity to the concatenation
``own_source + neighbour``. That is the shape an LLM produces when the OCR
mangled an end-of-line hyphen.

**A word moved intact is a different shape, and it resembles neither
half.** Measured on 2026-08-17, two adjacent lines and a producer that
appends a word to the first and removes it from the second:

    L1 'Les citoyens sur la place publique pour attendre'
    L2 'longtemps le retour du souverain et sa suite'
    ->  TL1 corrected 'Les citoyens … pour attendre longtemps'
        TL2 corrected 'le retour du souverain et sa suite'
        fallback_lines: 0

``longtemps`` changed line. Both lines reported ``corrected``, no reason,
nothing counted. The guard returned False because
``similarity("longtemps", "attendrelongtemps")`` is 0.69, under the 0.8
concatenation threshold — the word does not look like a completion, since
it never was one.

**Why the rule needs both halves of the move.** Flagging "A's last word
now equals B's first word" alone would revert a real typographic
repetition — a short function word legitimately corrected into the same
word the next line starts with. Requiring that B also *lost* it costs
nothing and removes that whole class; the last test here is that control,
and it is the reason the rule is written the way it is rather than the
shorter way.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._pipeline_harness import RecordingObserver

_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>'
    '<Page ID="P1" WIDTH="2000" HEIGHT="400"><PrintSpace>'
    '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="2000" HEIGHT="300">'
)
_TAIL = "</TextBlock></PrintSpace></Page></Layout></alto>"


def _text_line(line_id: str, vpos: int, words: str) -> str:
    strings = "".join(
        f'<String ID="{line_id}_{i}" CONTENT="{word}" HPOS="{i * 150}" '
        f'VPOS="{vpos}" WIDTH="140" HEIGHT="40"/>'
        f'<SP WIDTH="10" HPOS="{i * 150 + 140}" VPOS="{vpos}"/>'
        for i, word in enumerate(words.split())
    )
    return (
        f'<TextLine ID="{line_id}" HPOS="0" VPOS="{vpos}" WIDTH="1900" '
        f'HEIGHT="40">{strings}</TextLine>'
    )


def _run(first: str, second: str, rules: list[SubstitutionRule]) -> dict[str, str]:
    """``{line_id: "status|reason"}`` after a real run over two adjacent lines."""
    directory = Path(tempfile.mkdtemp())
    path = directory / "seam.xml"
    path.write_text(
        _HEAD + _text_line("TL1", 10, first) + _text_line("TL2", 60, second) + _TAIL,
        encoding="utf-8",
    )
    manifest = build_document_manifest([(path, path.name)])
    pipeline = CorrectionPipeline(
        producer=RulesProducer(rules), observer=RecordingObserver()
    )
    result = pipeline.run_sync(
        document_manifest=manifest, source_files={path.name: path}
    )
    return {
        outcome.line_id: (
            f"{outcome.decision.status}|"
            f"{outcome.decision.reason.code if outcome.decision.reason else None}"
        )
        for outcome in result.report.lines
    }


#: The word that changes line. Long enough that no similarity threshold
#: could mistake it for a correction of ``attendre``.
_FIRST = "Les citoyens sur la place publique pour attendre"
_SECOND = "longtemps le retour du souverain et sa suite"
_MIGRATION = [
    SubstitutionRule("pour attendre", "pour attendre longtemps"),
    SubstitutionRule("longtemps le retour", "le retour"),
]


def test_the_producer_really_moves_the_word() -> None:
    """Without the move there is no migration, and the test proves nothing.

    Checked on the identity of the rules rather than on the outcome,
    because the outcome under a working guard is a fallback — which is
    exactly what makes it impossible to observe the move afterwards.
    """
    assert _SECOND.split()[0] == "longtemps"
    assert _FIRST.split()[-1] == "attendre"
    assert any("longtemps" in rule.replacement for rule in _MIGRATION)


def test_a_word_that_changes_line_reverts_both_sides() -> None:
    outcomes = _run(_FIRST, _SECOND, _MIGRATION)
    assert outcomes == {
        "TL1": "fallback|boundary_migration_forward",
        "TL2": "fallback|boundary_migration_forward",
    }, (
        f"a whole word changed line and the run reported {outcomes}. No text "
        "migrates between physical lines — the guard modelled a word being "
        "COMPLETED across the seam, and a word moved intact resembles "
        "neither fragment. Both sides revert, because reverting only the "
        "receiving side would turn the duplication into a hole on the other."
    )


def test_a_legitimate_repetition_across_the_seam_is_left_alone() -> None:
    """The control, and the reason the rule requires both halves of the move.

    Line A's last word is mis-OCRed as ``1e`` and corrected to ``le``,
    which is also how line B legitimately begins. A rule that only asked
    "does A's last word now equal B's first word?" would revert this
    perfectly good correction. B keeps its own word, so nothing moved.
    """
    outcomes = _run(
        "il attendit sur la place avec 1e",
        "le peuple et les soldats du roi",
        [SubstitutionRule("avec 1e", "avec le")],
    )
    assert outcomes["TL1"].startswith("corrected"), (
        f"a correction that happens to produce the word the next line "
        f"starts with was reverted — {outcomes}. Nothing left line 2: it "
        "still begins with its own word, so no word changed line."
    )
