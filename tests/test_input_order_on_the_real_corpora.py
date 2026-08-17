"""Input order changes the delivered bytes, and it is supposed to.

``docs/promises.md`` carried *"l'ordre des fichiers d'entrée ne change rien"*,
graded **partielle** with the note *"prouvé sur un corpus jouet de deux
fichiers d'une ligne, là où c'est trivial"*. Measured on the real corpora on
2026-08-17, the grading was too generous: the promise is not partially
covered, it is **false** — and false because of behaviour this repository
ratified in tests long before the promise was written.

**What was measured.** Five real ALTO files — ``examples/X0000002.xml``,
``examples/bnf-alto-prod-bpt6k5406037v-f40.xml`` and the three pinned Gallica
pages — run through a correcting producer in four orders. The same order twice
is byte-identical and op-identical, so the run is deterministic; but:

===============  ===================================
order            files whose bytes differ from forward
===============  ===================================
reverse          2 of 5
rotated          1 of 5
interleaved      4 of 5
===============  ===================================

**Why.** ``link_cross_page_hyphens`` walks *adjacent pages* and knows nothing
of source files, so the last page of one file and the first page of the next
are consecutive pages of one document. In forward order that produced four
links crossing a file boundary — including one from a BnF page onto a Gallica
page whose two fragments spell ``donMais,``. Reordering the list changes which
pages are adjacent, so it changes which pairs exist, so two lines swap between
``corrected`` and ``fallback`` with reason ``hyphen_pair_fallback``: exactly
1199/609 either way, different lines.

**And that is the intended behaviour, checked before concluding otherwise.**
``tests/test_parser.py`` asserts it twice, with fixtures named ``page1.xml``
and ``page2.xml`` — once for an explicit pair carrying ``SUBS_CONTENT``, once
for a heuristic one, whose docstring reads *"Heuristic PART1 (trailing dash,
no SUBS_TYPE) also links cross-page"*. One file per page is how a digital
library exports a volume, so consecutive files being consecutive pages is a
feature. The contract says the same thing from the other side: page reading
order is part of the output contract, which is what forbids parallelising
pages.

So two stated promises contradict each other, and the measurement says which
one the code implements. This file keeps the half that is true, and pins the
counter-example so the false half cannot be re-derived from the true one.

**The half that is true** is what `F4` and `ADR-009` were about: no identity
is keyed on something only unique within one file. Checked here on the real
corpora rather than on two one-line documents — 1808 lines, 5 files, and the
per-line decisions must agree ref for ref except at the seams.

**The hazard this leaves a caller**, which is a documentation matter and named
in ``README.md``: handing unrelated documents to one call makes them one
document. Nothing refuses it, and the cost measured above is two discarded
corrections and a word derivable across two unrelated scans.
"""

from __future__ import annotations

import pytest

from saknussemm import CorrectionPipeline
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._paths import EXAMPLES, TESTS
from tests._pipeline_harness import RecordingObserver

_FILES = [
    EXAMPLES / "X0000002.xml",
    EXAMPLES / "bnf-alto-prod-bpt6k5406037v-f40.xml",
    *sorted((TESTS / "external_corpus" / "pinned").glob("*.xml")),
]

#: Reading order, as a caller who exported a volume page by page would pass it.
_FORWARD = [(path, path.name) for path in _FILES]


def _run(order: list[tuple]) -> tuple[dict[str, bytes], dict, list]:
    manifest = build_document_manifest(order)
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("e", "3")]),
        observer=RecordingObserver(),
        producer_metadata=ProducerMetadata(name="rules", implementation="fr-ocr-v1"),
    ).run_sync(
        document_manifest=manifest,
        source_files={name: path for path, name in order},
    )
    ops = sorted(
        (op.page_id, op.line_id, type(op).__name__, getattr(op.anchor, "start", None))
        for op in result.edit_script.ops
    )
    return dict(result.corrected_files), result.decisions.by_ref, ops


def _crossing_links(order: list[tuple]) -> list[tuple[str, str, str, str]]:
    """``(file, line_id, direction, partner file)`` for every pair spanning files."""
    manifest = build_document_manifest(order)
    file_of_page = {page.page_id: page.source_file for page in manifest.pages}
    crossing = []
    for page in manifest.pages:
        for line in page.lines:
            for partner_id, partner_page, direction in (
                (line.hyphen_pair_line_id, line.hyphen_pair_page_id, "backward"),
                (
                    line.hyphen_forward_pair_id,
                    line.hyphen_forward_pair_page_id,
                    "forward",
                ),
            ):
                if not (partner_id and partner_page):
                    continue
                partner_file = file_of_page.get(partner_page)
                if partner_file != page.source_file:
                    crossing.append(
                        (page.source_file, line.line_id, direction, str(partner_file))
                    )
    return crossing


def test_the_same_order_twice_is_byte_identical() -> None:
    """The control arm, and the reason the rest of this file means anything.

    Without it, "the bytes changed when I reordered" and "the bytes change
    every run" are the same observation. Measured: they are not — same order,
    same bytes, same ops.
    """
    first_files, _, first_ops = _run(_FORWARD)
    second_files, _, second_ops = _run(_FORWARD)
    assert first_ops == second_ops, "the edit script is not reproducible"
    differing = [n for n in first_files if first_files[n] != second_files[n]]
    assert not differing, (
        f"{differing} came back different from an identical run. Nothing below "
        "can distinguish an ordering effect from plain non-determinism until "
        "this holds."
    )


def test_consecutive_files_are_consecutive_pages() -> None:
    """The ratified behaviour, pinned on the real corpora.

    ``tests/test_parser.py`` asserts it on two hand-built one-page files. This
    says it also happens on five real documents that are **not** one volume,
    because that is the part a caller meets and the part the promise denied.
    """
    crossing = _crossing_links(_FORWARD)
    assert crossing, (
        "no hyphen pair crosses a file boundary on five real files. If "
        "cross-file seams were deliberately removed, this file's whole premise "
        "changed and `docs/promises.md` needs revisiting — the promise it "
        "contradicts would become true."
    )
    files = {row[0] for row in crossing} | {row[3] for row in crossing}
    assert len(files) > 1, f"the links do not actually span files: {crossing}"


@pytest.mark.parametrize(
    "label",
    ["reverse", "rotated", "interleaved"],
)
def test_reordering_the_files_changes_the_delivered_bytes(label: str) -> None:
    """The counter-example, asserted so the false promise cannot come back.

    This is not a defect being pinned. It is the consequence of a feature,
    and it is here because the promise it refutes was graded *partielle* for
    a year on the strength of a fixture too small to show it.
    """
    orders = {
        "reverse": _FORWARD[::-1],
        "rotated": _FORWARD[2:] + _FORWARD[:2],
        "interleaved": [_FORWARD[i] for i in (1, 3, 0, 4, 2)],
    }
    forward_files, _, _ = _run(_FORWARD)
    other_files, _, _ = _run(orders[label])

    assert set(forward_files) == set(other_files), (
        "reordering changed WHICH files came back, which would be a different "
        "and much worse defect than the one this file documents"
    )
    differing = [n for n in forward_files if forward_files[n] != other_files[n]]
    assert differing, (
        f"{label}: every file came back byte-identical. That would mean "
        "cross-file seams stopped forming, so `link_cross_page_hyphens` no "
        "longer treats consecutive files as consecutive pages — a deliberate "
        "change, and `docs/promises.md` should record it as making the "
        "promise true rather than as a test regression."
    )


def test_only_the_seams_move_and_nothing_else() -> None:
    """The half of the promise that IS true, on the real corpora.

    `F4` keyed the producer-op index on a bare ``line_id``, so a second file
    reusing ``L1`` overwrote the first. `ADR-009` answered with ``LineRef``.
    This asserts the answer from the outside on 1808 real lines: reordering
    may move a decision at a **seam**, and nothing else. A bad identity key
    would move decisions in the middle of pages, far from any seam.
    """
    _, forward_decisions, _ = _run(_FORWARD)
    _, reverse_decisions, _ = _run(_FORWARD[::-1])

    assert set(forward_decisions) == set(reverse_decisions), (
        "the set of decided lines depends on input order, which no reading of "
        "the contract allows"
    )
    flipped = {
        ref
        for ref in forward_decisions
        if forward_decisions[ref].status is not reverse_decisions[ref].status
    }
    assert flipped, (
        "no decision moved at all, so this case is not discriminating. See the "
        "note in the reordering test above."
    )
    # A seam line is one at the head or the foot of its page: those are the
    # only lines `link_cross_page_hyphens` can touch.
    manifest = build_document_manifest(_FORWARD)
    seams = set()
    for page in manifest.pages:
        if page.lines:
            seams.add((page.page_id, page.lines[0].line_id))
            seams.add((page.page_id, page.lines[-1].line_id))
    inland = [ref for ref in flipped if (ref.page_id, ref.line_id) not in seams]
    assert not inland, (
        f"{len(inland)} decision(s) moved on lines that are neither the head "
        f"nor the foot of their page: {inland[:3]}. Only the seam can depend "
        "on which page sits next door, so a decision moving inland means "
        "something is keyed on an identity that is not unique across the run "
        "— the `F4` family, which `ADR-009` was supposed to close."
    )
