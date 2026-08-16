"""An edit must stay attached to the line it was computed for.

``line_id`` alone repeats across source files — two exports legitimately
both call their first line ``L1``. Anything keyed on the bare id therefore
holds whichever file was parsed last, and the deliverable that suffers is
the one nobody re-derives: the ``EditScript`` a dry run hands back. An op
that lost its span degrades to a whole-line replacement; an op that kept
the WRONG file's span is worse, and both look fine in a diff.

Both cases replay each op over its OWN file's OCR text and require the
result to match what the pipeline actually wrote. That is the only check
that distinguishes "attributed" from "plausible".
"""

from __future__ import annotations

import pytest

from lidenbrock.core.protocols import ProducerMetadata

from tests._docs import _ALTO_ONE_LINE


@pytest.mark.asyncio
async def test_f4_producer_ops_do_not_collide_across_files(tmp_path):
    """Two files legitimately reuse line_id 'L1' with the SAME rule
    matching at DIFFERENT offsets. Pre-fix the last chunk overwrote
    _producer_ops['L1'], so file A's op lost its span (degraded to
    replace_line) — or worse, could carry file B's span."""
    from lidenbrock import CorrectionPipeline
    from lidenbrock.core.editing import ReplaceSpan, apply_edit_script
    from lidenbrock.core.editing import EditScript
    from lidenbrock.formats.alto.parser import build_document_manifest
    from lidenbrock.producers.rules import RulesProducer, SubstitutionRule
    from tests._pipeline_harness import RecordingObserver

    path_a = tmp_path / "a.xml"
    path_b = tmp_path / "b.xml"
    path_a.write_text(_ALTO_ONE_LINE.format(text="la frauce entiere"), "utf-8")
    path_b.write_text(_ALTO_ONE_LINE.format(text="grande frauce unie"), "utf-8")

    doc = build_document_manifest([(path_a, "a.xml"), (path_b, "b.xml")])
    pipeline = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("frauce", "france")]),
        observer=RecordingObserver(),
        producer_metadata=ProducerMetadata(name="rules", implementation="fr-ocr-v1"),
    )
    result = await pipeline.run(
        document_manifest=doc,
        source_files={"a.xml": path_a, "b.xml": path_b},
    )

    ops = result.edit_script.ops
    assert len(ops) == 2, ops
    # Both files keep their producer op TYPE and their OWN span offsets
    # (document order: file A then file B).
    op_a, op_b = ops
    assert isinstance(op_a, ReplaceSpan), f"file A's op degraded: {op_a!r}"
    assert isinstance(op_b, ReplaceSpan), f"file B's op degraded: {op_b!r}"
    assert op_a.anchor.start == 3, op_a
    assert op_b.anchor.start == 7, op_b
    # Replaying each file's op over ITS OWN OCR text reproduces the
    # pipeline's final text for that file.
    replay_a = apply_edit_script(EditScript(ops=[op_a]), {"L1": "la frauce entiere"})
    replay_b = apply_edit_script(EditScript(ops=[op_b]), {"L1": "grande frauce unie"})
    assert replay_a.text_by_id["L1"] == "la france entiere"
    assert replay_b.text_by_id["L1"] == "grande france unie"


@pytest.mark.asyncio
async def test_review_w1_edit_script_ops_attributable_across_files(tmp_path):
    """Wave-1 review follow-up (F4 residual) — the (page_id, line_id)
    keying fixed the internal capture collision, but the EMITTED dry-run
    edit_script still carried two ops with the same bare line_id and no
    file qualifier: a consumer replaying the whole script could not
    attribute each op to its file. Ops must now carry the page_id and
    apply_edit_script(page_id=…) must scope replay to one page."""
    from lidenbrock import CorrectionPipeline
    from lidenbrock.core.editing import EditScript, apply_edit_script
    from lidenbrock.formats.alto.parser import build_document_manifest
    from lidenbrock.producers.rules import RulesProducer, SubstitutionRule
    from tests._pipeline_harness import RecordingObserver

    path_a = tmp_path / "a.xml"
    path_b = tmp_path / "b.xml"
    path_a.write_text(_ALTO_ONE_LINE.format(text="la frauce entiere"), "utf-8")
    path_b.write_text(_ALTO_ONE_LINE.format(text="grande frauce unie"), "utf-8")

    doc = build_document_manifest([(path_a, "a.xml"), (path_b, "b.xml")])
    pipeline = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("frauce", "france")]),
        observer=RecordingObserver(),
        producer_metadata=ProducerMetadata(name="rules", implementation="fr-ocr-v1"),
    )
    result = await pipeline.run(
        document_manifest=doc,
        source_files={"a.xml": path_a, "b.xml": path_b},
    )

    ops = result.edit_script.ops
    assert len(ops) == 2, ops
    # Every emitted op is attributable: page_ids present and distinct
    # (page_ids are document-unique even when line_ids repeat).
    page_a_id, page_b_id = (p.page_id for p in doc.pages)
    assert [op.page_id for op in ops] == [page_a_id, page_b_id], ops

    # Replaying the WHOLE script scoped to one page applies only that
    # page's op — no cross-file bleed, no spurious rejection.
    full = EditScript(ops=list(ops))
    replay_a = apply_edit_script(full, {"L1": "la frauce entiere"}, page_id=page_a_id)
    replay_b = apply_edit_script(full, {"L1": "grande frauce unie"}, page_id=page_b_id)
    assert replay_a.text_by_id["L1"] == "la france entiere"
    assert not replay_a.rejected, replay_a.rejected
    assert replay_b.text_by_id["L1"] == "grande france unie"
    assert not replay_b.rejected, replay_b.rejected

    # Unscoped replay keeps its historical behaviour (all ops considered).
    legacy = apply_edit_script(EditScript(ops=[ops[0]]), {"L1": "la frauce entiere"})
    assert legacy.text_by_id["L1"] == "la france entiere"
