"""The joined word must agree with the two lines it joins.

``SUBS_CONTENT`` is a decision the run makes per hyphen pair — the word the
two fragments spell together — and it is delivered in the XML. It is
**not** on :class:`LineDecision`, so ``_verify_projection`` never looks at
it: the projection invariant compares per-line text and nothing else.

`RM-01` exempted the field from the single decision writer deliberately,
with the reason written on the spot. Nothing was put in its place.

Measured on 2026-08-17: a manifest whose text is unchanged and whose
``hyphen_subs_content`` says ``MOT-COMPLETEMENT-FAUX`` delivers that string
into the file, and the projection reports every line ``EXACT`` — correctly,
by its own definition, because the text is indeed unchanged.

**The invariant that was missing, and it is exact rather than approximate**:
the joined word is the head's last word with its break mark removed,
followed by the tail's first word. Measured over every hyphen pair of every
real corpus in this repository — ``examples/`` plus the three pinned Gallica
pages — **413 pairs, zero divergences**.

A note on how nearly this file asserted the wrong thing. A first
measurement reported 26 divergences on ``X0000002.xml`` and looked like a
real defect. It was the probe: a ``BOTH`` line closes one pair through its
**backward** field and opens the next through its **forward** one, and the
probe compared one against the other's expectation. Reading each field in
its own direction gives zero. Two encodings of one relation, and a reader
that mixes them sees a defect that is not there.

**What each half covers, measured rather than assumed.** Read straight from
a source file, the property checks that the CORPUS is internally consistent:
the library carries ``SUBS_CONTENT`` out of the attribute and does not
compute it there, so a parse-only sweep guards the data, not the code. Read
from the DELIVERED file after a real run, it additionally guards that the
parse and the rewrite kept the value agreeing with the two lines — 35 and
114 pairs, zero divergences.

**It does NOT yet guard the reconciler**, and that is measured too:
reversing the joined word ``reconcile`` writes at ``reconcile.py:288`` leaves
both halves green. The pairs that survive a correcting run on these fixtures
are the ones reconciliation did not rewrite, so its write path is never
reached. Covering it needs a fixture that forces a pair to reconcile to new
text and keep its ``SUBS`` — named here rather than claimed, because a guard
described as covering more than it does is the defect this whole effort is
about.

Promoting this to a run-time refusal is a separate step: it would need the
same measurement over chains, cross-page seams and heuristic pairs before
it could fail a user's document rather than a test.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from saknussemm.core.pairing import HYPHEN_CHARS
from saknussemm.core.schemas import DocumentManifest, LineManifest
from saknussemm.formats.loader import build_document_manifest

from tests._paths import EXAMPLES, TESTS

_MARKS = "".join(HYPHEN_CHARS)

#: Every real ALTO in the repository that carries explicit hyphenation.
_CORPORA = [
    EXAMPLES / "X0000002.xml",
    EXAMPLES / "bnf-alto-prod-bpt6k5406037v-f40.xml",
    *sorted((TESTS / "external_corpus" / "pinned").glob("*.xml")),
]

#: Below this the sweep would be green on a corpus with no pairs at all.
_MINIMUM_PAIRS = 300


def _joined_pairs(manifest: DocumentManifest) -> list[tuple[str, str, str]]:
    """``[(line_id, joined word as delivered, joined word the texts spell)]``.

    Each field is read in **its own direction**, which is the part that has
    to be right: ``hyphen_subs_content`` is the backward join, and on a
    ``BOTH`` line ``hyphen_forward_subs_content`` is a different pair
    entirely.
    """
    by_ref: dict[tuple[str, str], LineManifest] = {
        (page.page_id, line.line_id): line
        for page in manifest.pages
        for line in page.lines
    }
    found: list[tuple[str, str, str]] = []
    for (page_id, line_id), head in by_ref.items():
        forward = [
            (
                head.hyphen_forward_subs_content,
                head.hyphen_forward_pair_id,
                head.hyphen_forward_pair_page_id,
            )
        ]
        if head.hyphen_role.value == "HypPart1":
            # A pure PART1 has no forward field: its single pair lives in the
            # backward one, pointing at the line below.
            forward.append(
                (
                    head.hyphen_subs_content,
                    head.hyphen_pair_line_id,
                    head.hyphen_pair_page_id,
                )
            )
        for subs, partner_id, partner_page in forward:
            if not subs or not partner_id:
                continue
            tail = by_ref.get((partner_page or page_id, partner_id))
            if tail is None:
                continue
            left = head.ocr_text.rstrip().rstrip(_MARKS).split()
            right = tail.ocr_text.split()
            if not left or not right:
                continue
            found.append((line_id, subs, left[-1] + right[0]))
    return found


def test_the_sweep_covers_enough_pairs_to_mean_something() -> None:
    total = sum(
        len(_joined_pairs(build_document_manifest([(path, path.name)])))
        for path in _CORPORA
    )
    assert total >= _MINIMUM_PAIRS, (
        f"only {total} joined pair(s) across the corpora; the assertion below "
        "would hold over almost nothing. Measured 2026-08-17: 413."
    )


@pytest.mark.parametrize("path", _CORPORA, ids=lambda p: p.name)
def test_every_joined_word_is_what_its_two_lines_spell(path) -> None:
    diverging = [
        (line_id, delivered, expected)
        for line_id, delivered, expected in _joined_pairs(
            build_document_manifest([(path, path.name)])
        )
        if delivered != expected
    ]
    assert not diverging, (
        f"{path.name}: {len(diverging)} joined word(s) say something the two "
        f"lines do not spell — {diverging[:3]}. SUBS_CONTENT is delivered in "
        "the XML and is absent from LineDecision, so the projection invariant "
        "cannot see it: a wrong joined word ships with every line reported "
        "EXACT."
    )


def test_a_poisoned_joined_word_is_caught() -> None:
    """Guard the guard, on the shape the audit measured.

    Without this, a bug in the derivation above would make every corpus case
    pass vacuously — which is how this field went unguarded in the first
    place.
    """
    path = EXAMPLES / "X0000002.xml"
    manifest = build_document_manifest([(path, path.name)])
    poisoned = False
    for page in manifest.pages:
        for line in page.lines:
            if line.hyphen_subs_content and not poisoned:
                line.hyphen_subs_content = "MOT-COMPLETEMENT-FAUX"
                poisoned = True
    assert poisoned, "no pair to poison — the fixture stopped carrying SUBS"
    assert any(
        delivered != expected for _, delivered, expected in _joined_pairs(manifest)
    ), (
        "a joined word replaced by a string bearing no relation to either "
        "line was not detected. The derivation above cannot be doing what it "
        "claims."
    )


@pytest.mark.parametrize("path", _CORPORA[:1] + _CORPORA[-1:], ids=lambda p: p.name)
def test_the_delivered_file_still_agrees_after_a_real_run(path) -> None:
    """The half that guards the library rather than the corpus.

    A parse-only sweep reads ``SUBS_CONTENT`` back out of the attribute the
    file already carried, so it cannot see a library that mangles it. This
    runs a correcting producer end to end and re-parses the delivered bytes:
    the joined word must still be what the two delivered lines spell.

    Scope, measured: this covers the parse and the rewrite. It does **not**
    cover the reconciler's own write — reversing it leaves this green,
    because the pairs surviving a correcting run on these fixtures are the
    ones reconciliation left alone.

    Fewer pairs than in the source is expected, not a loss: a pair whose
    correction diverged falls back and its ``SUBS`` is neutralised, which is
    the documented remedy. What must not happen is a pair surviving with a
    joined word its own two lines contradict.
    """
    from saknussemm.core.pipeline import CorrectionPipeline
    from saknussemm.producers.rules import RulesProducer, SubstitutionRule

    from tests._pipeline_harness import RecordingObserver

    manifest = build_document_manifest([(path, path.name)])
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("e", "3")]),
        observer=RecordingObserver(),
    ).run_sync(document_manifest=manifest, source_files={path.name: path})

    delivered = Path(tempfile.mkdtemp()) / path.name
    delivered.write_bytes(result.corrected_files[path.name])
    pairs = _joined_pairs(build_document_manifest([(delivered, delivered.name)]))

    assert pairs, (
        f"{path.name}: the delivered file carries no joined pair at all, so "
        "this case checks nothing. Either every pair fell back or the rewriter "
        "stopped emitting SUBS."
    )
    diverging = [(line_id, got, want) for line_id, got, want in pairs if got != want]
    assert not diverging, (
        f"{path.name}: {len(diverging)} delivered joined word(s) contradict "
        f"their own two lines — {diverging[:3]}. Nothing in the run would have "
        "said so: SUBS_CONTENT is not on LineDecision, so the projection "
        "invariant reports EXACT while the file spells a word neither line does."
    )
