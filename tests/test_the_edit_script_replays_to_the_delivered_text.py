"""The script a run hands back rewrites the file the run handed back.

A differential property (`T3`) over two deliverables of the SAME run:
``result.edit_script`` and ``result.corrected_files``. A consumer that
replays the script on the original document must land exactly where the
library's own rewriter landed — otherwise the library ships two answers to
one question and lets the caller pick.

The promise is written down, in ``_build_final_edit_script``'s own
docstring, as the reason that function is more than a dump of what the
producer proposed:

    It therefore never carries an op for a line that was reverted to OCR
    or reconciled to different text (a dry-run consumer replaying it would
    otherwise diverge from the pipeline's own corrected XML).

Nothing compared the two. ``test_edit_preconditions`` replays the script
and checks ONE line reaches the text the producer asked for, and checks a
lookalike document is refused — both about the replay machinery. Neither
opens the delivered XML, so the sentence above was an intention rather than
a checked invariant.

**What makes the fixture worth running.** The gap between "the script the
producer proposed" and "the script the run applied" only opens on a line
where the two differ, and the cheapest way to produce one is the
reconciler's own refusal. The pair used below is explicit — the source
records ``SUBS_CONTENT="travailleurs"`` — so the reconciler joins the two
corrected fragments and checks they still spell it. Corrupt either side and
the join no longer matches, and **both** lines revert to OCR: invariant "no
incoherent pair survives". The producer's proposals for those two lines
exist, are recorded, and must not reach the script, because the XML does
not carry them. A naive implementation — emit every captured op — passes
every other test in this suite and fails here on exactly those two lines.

The converse direction is asserted too, and it is not symmetric: a line
whose delivered text differs from its source with NO op behind it is a byte
the caller cannot account for, which is the same defect seen from the other
end.
"""

from __future__ import annotations

from lxml import etree

from lidenbrock.core.editing import apply_edit_script
from lidenbrock.core.schemas import LineStatus
from lidenbrock.formats.alto._ns import _detect_namespace
from lidenbrock.formats.alto._text import reconstruct_textline
from lidenbrock.formats.alto.parser import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import PipelineRun, run_pipeline

_CORPUS = "X0000002.xml"

#: A real hyphen pair of the BnF page (``SUBS_CONTENT="travailleurs"``),
#: and a correction of each side that sends it through the reconciler's
#: refusal: both stay structurally legal — same word count, PART1 still
#: ends on a hyphen — but ``trà`` + ``xxxxx`` no longer joins to the
#: recorded word. Both sides revert, and the producer's two proposals
#: become text that exists nowhere in the delivered file.
_PART1 = "PAG_00000002_TL000005"
_PART2 = "PAG_00000002_TL000006"
_REVERTED_PAIR = {
    _PART1: "fréquenté par un grand nombre de trà-",
    _PART2: "xxxxx ruraux de notre ville qui se ren-",
}

#: How many plain corrections must survive to the file. Without them the
#: run is all refusals and the agreement is between two empty sets.
_MINIMUM_LANDED = 3


def _delivered_text_by_line(xml: bytes) -> dict[str, str]:
    """The logical text of every TextLine in a rewritten file.

    ``reconstruct_textline`` is the rewriter's own reader; the trailing
    ``.strip()`` is the one documented difference with the parser's
    logical form (``test_text_reconstruction_parity``), and it is what
    makes this comparable to ``LineManifest.ocr_text``.
    """
    root = etree.fromstring(xml)
    ns = _detect_namespace(root)
    tag = f"{{{ns}}}TextLine" if ns else "TextLine"
    return {
        tl.get("ID"): reconstruct_textline(tl, ns).replace("\r", "").strip()
        for tl in root.iter(tag)
    }


def _a_run_with_landed_and_reverted_lines() -> tuple[PipelineRun, dict[str, str]]:
    """One run carrying both outcomes, plus the SOURCE text of every line.

    The source manifest is parsed a second time on purpose: the harness
    projects the run's decisions onto the one it used, so reading canonical
    text off it would compare the run against itself.
    """
    source = build_document_manifest([(EXAMPLES / _CORPUS, _CORPUS)])
    canonical = {lm.line_id: lm.ocr_text for page in source.pages for lm in page.lines}

    plain = [
        line_id
        for line_id, text in canonical.items()
        if line_id not in _REVERTED_PAIR and len(text.split()) > 3
    ][:5]
    corrections = dict(_REVERTED_PAIR)
    corrections.update({line_id: f"{canonical[line_id]} ajoute" for line_id in plain})
    return run_pipeline(_CORPUS, corrections), canonical


def _replay(run: PipelineRun, canonical: dict[str, str]) -> dict[str, str]:
    """Apply the final script the way a consumer would: page by page.

    ``page_id`` scoping is not decoration — a script spanning several files
    reuses line_ids, and replaying it unscoped is the `F4` shape.
    """
    text: dict[str, str] = {}
    rejected = []
    for page in run.document_manifest.pages:
        result = apply_edit_script(
            run.result.edit_script,
            canonical,
            line_by_id={lm.line_id: lm for lm in page.lines},
            page_id=page.page_id,
        )
        text.update(result.text_by_id)
        rejected.extend(result.rejected)
    assert not rejected, (
        f"the run's own script does not apply to the run's own input: "
        f"{rejected[:5]}. Every precondition was computed from this "
        "document; a rejection here means the script describes a document "
        "nobody has."
    )
    return text


def test_replaying_the_script_reproduces_the_delivered_file() -> None:
    run, canonical = _a_run_with_landed_and_reverted_lines()
    delivered = _delivered_text_by_line(run.result.corrected_files[_CORPUS])

    disagree = {
        line_id: (replayed, delivered.get(line_id))
        for line_id, replayed in _replay(run, canonical).items()
        if delivered.get(line_id) != replayed
    }
    assert not disagree, (
        f"replaying the run's edit_script lands somewhere the run's own "
        f"XML did not (replayed, delivered): {disagree}. The script is a "
        "deliverable, not a log of what the producer suggested — a line "
        "reverted to OCR or rewritten by the reconciler must not carry the "
        "proposal that lost."
    )


def test_every_changed_line_has_an_op_behind_it() -> None:
    """The other direction: no byte the caller cannot account for."""
    run, canonical = _a_run_with_landed_and_reverted_lines()
    delivered = _delivered_text_by_line(run.result.corrected_files[_CORPUS])
    replayed = _replay(run, canonical)

    unexplained = {
        line_id: (source, delivered[line_id])
        for line_id, source in canonical.items()
        if line_id in delivered
        and delivered[line_id] != source
        and line_id not in replayed
    }
    assert not unexplained, (
        f"line(s) the file changed with no op to show for it (source, "
        f"delivered): {unexplained}. A consumer replaying the script would "
        "reconstruct a different document and have no way to know."
    )


def test_the_run_exercises_both_outcomes() -> None:
    """Otherwise the two assertions above agree over nothing that matters.

    Two things have to be true at once, and neither is implied by the
    other: corrections that reached the file, and a proposal the run
    recorded and then refused. The second is the whole reason the script
    is built from decisions rather than from producer output.
    """
    run, canonical = _a_run_with_landed_and_reverted_lines()
    delivered = _delivered_text_by_line(run.result.corrected_files[_CORPUS])

    landed = [
        line_id
        for line_id, source in canonical.items()
        if line_id in delivered and delivered[line_id] != source
    ]
    assert len(landed) >= _MINIMUM_LANDED, (
        f"only {len(landed)} line(s) actually changed in the delivered file "
        f"— expected at least {_MINIMUM_LANDED}. The corrections stopped "
        "landing, and the property above now compares a document to itself."
    )

    by_ref = {d.ref.line_id: d for d in run.result.decisions.decisions}
    for line_id in _REVERTED_PAIR:
        decision = by_ref[line_id]
        assert decision.status is LineStatus.FALLBACK, (
            f"{line_id} was expected to revert (the corrected fragments no "
            f"longer join to the recorded SUBS_CONTENT) but ended "
            f"{decision.status}. "
            "Without a refused proposal, emitting every captured op would "
            "pass the property above."
        )
        assert delivered[line_id] == canonical[line_id], (
            f"{line_id} reverted yet the file does not carry its source "
            "text — the fixture no longer produces the case it exists for."
        )
