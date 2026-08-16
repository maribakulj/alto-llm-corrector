"""The one deliberately destructive operation must be visible (R6).

When a hyphen chain is longer than ``max_lines_per_request``, the LINE
planner cannot keep it in one request without breaking pair atomicity, so it
SEVERS a forward link: the cut pair degrades to two independent lines, each
keeping its OCR text verbatim (``split_forward_link``, ADR-010).

That cut is the only operation in the engine that deliberately destroys a
structural fact, and it was invisible to the host. The record rode on the
``ChunkPlan`` — an internal planning artefact nobody outside the planner ever
sees — and nothing else on the report covers it:

* not ``unpaired_breaks``: the split resets the tail's role to ``NONE``, and
  that count only looks at lines which still *want* a partner;
* not a fallback: both sides keep their text and are corrected normally;
* not a ``format_loss``: nothing leaves the markup.

What a host is actually handed is a delivered line whose text still ends
mid-word and which declares no break at all. It should be able to find that
out.
"""

from __future__ import annotations

from pathlib import Path


from lidenbrock import CorrectionPipeline
from lidenbrock.core.editing import EditScript, ReplaceLine
from lidenbrock.core.protocols import ProducerMetadata
from lidenbrock.core.schemas import ChunkPlannerConfig, HyphenRole
from lidenbrock.formats.alto.parser import build_document_manifest

_NS = "http://www.loc.gov/standards/alto/ns-v3#"


def _alto(n_lines: int) -> str:
    """``n_lines`` lines, each ending in a hyphen — one long chain.

    The word before the hyphen is alphabetic on purpose: the heuristic
    pairing requires an alphabetic character immediately before the mark, so
    ``mot0-`` would be read as a numeric range and pair with nothing (the
    same guard that keeps ``1789-`` out). A fixture that got that wrong would
    produce single-line chunks and no chain at all — and the test would pass
    for the wrong reason on the day the split stopped happening.
    """
    lines = "".join(
        f'<TextLine ID="L{i}" HPOS="0" VPOS="{i * 40}" WIDTH="300" HEIGHT="30">'
        f'<String ID="S{i}" CONTENT="mot{chr(97 + i % 26)}-" HPOS="0" '
        f'VPOS="{i * 40}" WIDTH="300" HEIGHT="30"/></TextLine>'
        for i in range(n_lines)
    )
    return (
        f'<?xml version="1.0"?>\n<alto xmlns="{_NS}"><Layout>'
        f'<Page ID="P1" WIDTH="600" HEIGHT="{n_lines * 40 + 40}">'
        f'<PrintSpace HPOS="0" VPOS="0" WIDTH="600" HEIGHT="{n_lines * 40 + 40}">'
        f'<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="600" '
        f'HEIGHT="{n_lines * 40}">{lines}</TextBlock>'
        "</PrintSpace></Page></Layout></alto>"
    )


class _FailsOnMultiLineChunks:
    """Echoes a single-line chunk; answers a multi-line one incompletely.

    Not gratuitous: LINE is the ONLY granularity that severs a link, and
    ``plan_page``'s auto-selection never reaches it (PAGE -> BLOCK -> WINDOW,
    and LINE only under ``force_granularity``). The single path that gets
    there in a real run is the pipeline's granularity DESCENT, after a chunk
    has failed its retries. So a split is not merely rare — it requires a
    failing chunk on a page holding an over-cap chain, and a test that
    reports one has to go through that door too.

    An incomplete answer fails full-coverage validation, which is what drives
    the descent.
    """

    wants_geometry = False
    wants_image = False

    async def produce(self, payload, *, options):
        lines = list(payload.lines)
        if len(lines) > 1:
            lines = lines[:-1]  # one op short -> line-count mismatch
        return (
            EditScript(
                ops=tuple(
                    ReplaceLine(line_id=line.line_id, text=line.ocr_text)
                    for line in lines
                )
            ),
            None,
        )


class _Null:
    def on_event(self, *a, **k):
        pass


def _run(tmp_path: Path, n_lines: int, cap: int):
    xml_path = tmp_path / "chain.xml"
    xml_path.write_text(_alto(n_lines), encoding="utf-8")
    doc = build_document_manifest([(xml_path, xml_path.name)])
    pipeline = CorrectionPipeline(
        producer=_FailsOnMultiLineChunks(),
        observer=_Null(),
        producer_metadata=ProducerMetadata(name="test", implementation="v1"),
        config=ChunkPlannerConfig(
            # Small enough that PAGE/BLOCK/WINDOW cannot hold the page and
            # the planner descends to LINE, which is the only granularity
            # that severs anything.
            max_input_chars_per_request=60,
            max_lines_per_request=cap,
            line_window_size=4,
            line_window_overlap=0,
        ),
    )
    return pipeline.run_sync(
        document_manifest=doc, source_files={xml_path.name: xml_path}
    ), doc


def test_every_severed_link_reaches_the_report(tmp_path: Path) -> None:
    result, _doc = _run(tmp_path, 12, 2)
    splits = result.report.hyphen_splits
    assert splits, "an over-cap chain descending to LINE must be cut"
    for split in splits:
        assert split.page_id == "P1"
        # Every cut names a real, ADJACENT pair — not an arbitrary pair of
        # ids that happen to be on the page.
        tail_index = int(split.tail_line_id[1:])
        assert split.head_line_id == f"L{tail_index + 1}"


def test_the_split_is_not_covered_by_anything_else_on_the_report(
    tmp_path: Path,
) -> None:
    """Why it needed its own field, as assertions rather than as prose.

    ``unpaired_breaks`` is the field a reader would reach for, and it cannot
    answer: it counts lines that still WANT a partner, and the split's whole
    effect is to reset the tail's role so it wants none. Here the page ends
    on a hyphen, so exactly one line is genuinely unpaired — the last — and
    the count stays 1 no matter how many links were severed.
    """
    result, _doc = _run(tmp_path, 12, 2)
    splits = result.report.hyphen_splits
    assert splits

    # One genuine orphan (the page's final line ends mid-word with nothing
    # after it), and the severed tails are NOT in that count.
    assert result.report.unpaired_breaks == 1
    assert len(splits) > 1  # so the two numbers cannot coincide by accident

    outcomes = {ln.line_id: ln for ln in result.report.lines}
    for split in splits:
        tail = outcomes[split.tail_line_id]
        # The delivered text still ends mid-word. A line that breaks a word
        # and whose link was severed is the state a host has to be told
        # about, and this field is the only thing that tells it.
        assert tail.decision.final_text.endswith("-")


def test_the_reported_role_can_predate_the_split(tmp_path: Path) -> None:
    """Observed while pinning R6, and left as it is rather than papered over.

    ``LineOutcome.hyphen_role`` comes from the line's TRACE, written when the
    chunk was first enriched. A split happens later — during the granularity
    descent that follows a failed chunk — so a severed tail can be reported
    with the role it had BEFORE the cut (``HypBoth`` where the manifest now
    says ``HypPart2``).

    That is a second, narrower truth problem than R6's, and one this field
    does not fix: it is exactly why the split needs its OWN record rather
    than being inferred from the roles on the report. Pinned so it is a known
    quantity and not a surprise, and so a future fix has a test to flip.
    """
    result, _doc = _run(tmp_path, 12, 2)
    outcomes = {ln.line_id: ln for ln in result.report.lines}
    stale = [
        s.tail_line_id
        for s in (result.report.hyphen_splits or [])
        if outcomes[s.tail_line_id].hyphen_role
        not in (HyphenRole.NONE.value, HyphenRole.PART2.value)
    ]
    assert stale, (
        "if this list is empty the roles now follow the split — good news; "
        "update this test to assert the stronger property instead"
    )


def test_a_chain_inside_the_cap_reports_nothing(tmp_path: Path) -> None:
    """The other direction: no cut, no field. `None` rather than an empty
    list, like every other optional counter on the report."""
    result, _doc = _run(tmp_path, 2, 5)
    assert result.report.hyphen_splits is None
