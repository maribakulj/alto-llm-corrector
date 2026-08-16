"""A correction that duplicates its neighbour is reverted — everywhere.

A producer that loses its place emits the same plausible line two or three
times in a row. The guard that catches it is one function
(``check_adjacent_duplicates``), but the ways it can be defeated are all
about WHERE the comparison happens:

  * inside one chunk, a run of three used to flag only the first pair;
  * across a chunk boundary, the pass read the boundary line's
    POST-revert text — already back to OCR — and saw no duplicate;
  * across a page seam and across a granularity downgrade, same shape,
    different seam.

Gathered here from three files named after remediation waves (`RM-05b`);
names, docstrings and bodies unchanged.
"""

from __future__ import annotations

from lidenbrock.core.guards import check_adjacent_duplicates
from lidenbrock.core.schemas import LineStatus


def test_duplicate_run_of_three_all_reverted():
    # Distinct sources, identical corrections. The old loop flagged only the
    # first pair, leaving line 2 unreverted.
    reverts = check_adjacent_duplicates(
        [
            ("id0", "source alpha", "HALLUCINATED IDENTICAL LINE"),
            ("id1", "source beta", "HALLUCINATED IDENTICAL LINE"),
            ("id2", "source gamma", "HALLUCINATED IDENTICAL LINE"),
        ]
    )
    assert set(reverts) == {"id0", "id1", "id2"}


_ALTO_TWO_PAGES = """\
<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Layout>
    <Page ID="P1" WIDTH="1000" HEIGHT="1000">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="1000">
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
          {page1}
        </TextBlock>
      </PrintSpace>
    </Page>
    <Page ID="P2" WIDTH="1000" HEIGHT="1000">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="1000">
        <TextBlock ID="B2" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
          {page2}
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""


def _seam_doc(tmp_path) -> object:
    import textwrap

    p1_texts = [
        "Il faisait ce jour la un temps splendide",
        "et la lumiere dorait les vieux murs",
        "la riviere descendait vers le moulin",
    ]
    p2_texts = [
        "les enfants couraient dans la prairie",
        "un orage montait derriere la colline",
    ]

    def _body(texts: list[str], start: int) -> str:
        return "".join(
            f'<TextLine ID="L{start + i}" HPOS="10" VPOS="{30 * i + 10}"'
            f' WIDTH="900" HEIGHT="20">'
            f'<String CONTENT="{t}" HPOS="10" VPOS="{30 * i + 10}"'
            f' WIDTH="900" HEIGHT="20"/>'
            "</TextLine>"
            for i, t in enumerate(texts)
        )

    p = tmp_path / "seam.xml"
    p.write_text(
        textwrap.dedent(_ALTO_TWO_PAGES).format(
            page1=_body(p1_texts, 0), page2=_body(p2_texts, 3)
        ),
        encoding="utf-8",
    )
    return p


def test_f3_three_run_duplicate_across_chunk_boundary_reverts_third(tmp_path):

    from lidenbrock.core.pipeline import CorrectionPipeline
    from lidenbrock.core.schemas import ChunkPlannerConfig, GuardConfig
    from lidenbrock.formats.alto.parser import build_document_manifest
    from tests._pipeline_harness import apply_decisions, DictProvider, RecordingObserver
    from tests.test_planner_budget_and_cross_chunk_guard import _write_doc

    path = _write_doc(tmp_path)
    doc = build_document_manifest([(path, "doc.xml")])

    dup = "le meme texte hallucine identique pour trois lignes"
    pipeline = CorrectionPipeline.for_provider(
        # Window 4, overlap 0 → chunk0 targets {L0..L3}, chunk1 {L4..L7}.
        # L2+L3 are reverted by chunk0's intra-chunk pass BEFORE the
        # boundary pass compares (L3, L4).
        DictProvider({"L2": dup, "L3": dup, "L4": dup}),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
        config=ChunkPlannerConfig(
            max_input_chars_per_request=200,
            max_lines_per_request=50,
            line_window_size=4,
            line_window_overlap=0,
        ),
        guard_config=GuardConfig(min_source_similarity=0.0, neighbour_margin=1.0),
    )
    apply_decisions(
        doc,
        pipeline.run_sync(document_manifest=doc, source_files={"doc.xml": path}),
    )

    lines = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    for lid in ("L2", "L3", "L4"):
        assert lines[lid].corrected_text == lines[lid].ocr_text, lid
        assert lines[lid].status is LineStatus.FALLBACK, lid


def test_f3_twin_three_run_duplicate_across_page_seam_reverts_third(tmp_path):
    """Twin branch of F3: the document-level PAGE-SEAM pass reads live
    corrected_text too. A 3-run whose first two members (last two lines
    of page 1) were already reverted intra-page masked the seam pair
    (L2, L3) the same way."""
    from lidenbrock.core.pipeline import CorrectionPipeline
    from lidenbrock.core.schemas import GuardConfig
    from lidenbrock.formats.alto.parser import build_document_manifest
    from tests._pipeline_harness import apply_decisions, DictProvider, RecordingObserver

    path = _seam_doc(tmp_path)
    doc = build_document_manifest([(path, "seam.xml")])

    dup = "le meme texte hallucine identique pour trois lignes"
    pipeline = CorrectionPipeline.for_provider(
        DictProvider({"L1": dup, "L2": dup, "L3": dup}),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
        guard_config=GuardConfig(min_source_similarity=0.0, neighbour_margin=1.0),
    )
    apply_decisions(
        doc,
        pipeline.run_sync(document_manifest=doc, source_files={"seam.xml": path}),
    )

    lines = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    for lid in ("L1", "L2", "L3"):
        assert lines[lid].corrected_text == lines[lid].ocr_text, lid
        assert lines[lid].status is LineStatus.FALLBACK, lid


def test_review_w1_duplicate_across_downgrade_subchunk_seam_reverts(
    tmp_path, monkeypatch
):
    """Wave-1 review follow-up — the cross-chunk boundary pass built its
    owner map from the PLANNED chunks and was gated on
    ``len(plan.chunks) > 1``. A single planned chunk that granularity-
    descends into per-line sub-chunks therefore had NO boundary pass at
    all: an identical hallucination on two adjacent lines finalized by
    two different sub-chunks survived the duplicate guard entirely."""
    from unittest.mock import AsyncMock

    from lidenbrock.core.pipeline import CorrectionPipeline
    from lidenbrock.core.schemas import ChunkPlannerConfig, GuardConfig, RetryPolicy
    from lidenbrock.formats.alto.parser import build_document_manifest
    from tests._pipeline_harness import RecordingObserver, apply_decisions
    from tests.test_planner_budget_and_cross_chunk_guard import _write_doc

    monkeypatch.setattr(
        "lidenbrock.core.pipeline.asyncio.sleep", AsyncMock(return_value=None)
    )

    path = _write_doc(tmp_path)
    doc = build_document_manifest([(path, "doc.xml")])
    dup = "le meme texte hallucine identique pour deux lignes"

    class _DescendToLineProvider:
        """Refuses every multi-line request (forcing the full
        PAGE→BLOCK→WINDOW→LINE descent), then hallucinates the same
        sentence for the adjacent L3 and L4 — each finalized by its own
        single-line sub-chunk."""

        async def list_models(self, api_key: str) -> list:  # pragma: no cover
            return []

        async def complete_structured(
            self,
            *,
            api_key,
            model,
            system_prompt,
            user_payload,
            json_schema,
            temperature=0.0,
        ):
            lines = user_payload.get("lines", [])
            if len(lines) > 1:
                raise ValueError("mock: multi-line request refused")
            (ln,) = lines
            corrected = {"L3": dup, "L4": dup}.get(
                ln["line_id"], ln.get("ocr_text", "")
            )
            return {
                "lines": [{"line_id": ln["line_id"], "corrected_text": corrected}]
            }, None

    pipeline = CorrectionPipeline.for_provider(
        _DescendToLineProvider(),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
        # Defaults plan the 8-line doc as ONE chunk — the pre-fix gate
        # `len(plan.chunks) > 1` then skipped the boundary pass outright.
        config=ChunkPlannerConfig(),
        guard_config=GuardConfig(min_source_similarity=0.0, neighbour_margin=1.0),
        retry_policy=RetryPolicy(
            max_attempts=1, temperatures=(0.0,), per_chunk_budget=30
        ),
    )
    apply_decisions(
        doc,
        pipeline.run_sync(document_manifest=doc, source_files={"doc.xml": path}),
    )

    lines = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    # Identity corrections on the other lines survive untouched…
    assert lines["L0"].corrected_text == lines["L0"].ocr_text
    # …and the adjacent duplicate pair is reverted to OCR source.
    for lid in ("L3", "L4"):
        assert lines[lid].corrected_text == lines[lid].ocr_text, (
            f"{lid} kept the duplicated hallucination: {lines[lid].corrected_text!r}"
        )
        assert lines[lid].status is LineStatus.FALLBACK, lid
