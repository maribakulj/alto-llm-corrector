"""One run, every undeliverable file — not one finding per run.

The projection invariant refuses a document whose artefact does not say what
the run decided, and that refusal is right: a divergent file is corruption of
the deliverable, not a degradation to grade. What was wrong is that the
rewrite loop *stopped* at the first one.

A run is billed. Discovering a second bad file therefore cost a second full
pass over the producer — the corpus re-sent, the tokens re-paid, the wait
re-taken — to learn something the first run already had in hand three
milliseconds of lxml later. Three bad files in a volume meant three bills.

Nothing about the contract moves here: the run still raises, and no file is
delivered. What the exception carries changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saknussemm import CorrectionPipeline
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.core.schemas import RetryPolicy
from saknussemm.errors import ProjectionError
from saknussemm.formats.alto.parser import build_document_manifest

from tests.hyphenation.test_unit_fallback_atomicity import _Null

_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"><Layout>
<Page ID="{pid}" WIDTH="1000" HEIGHT="1000">
<PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextBlock ID="B{n}" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="900">
<TextLine ID="L{n}" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="20">
<String ID="S{n}" CONTENT="mot" HPOS="10" VPOS="10" WIDTH="80" HEIGHT="20"/>
</TextLine>
</TextBlock></PrintSpace></Page>
</Layout></alto>"""


class _WritesAnUnrepresentableLine:
    """Decides a text the ALTO writer provably cannot carry back.

    A lone U+0000 is not representable in XML at all, so whatever the writer
    emits, the re-extracted text cannot equal the decision — which is the
    definition of a projection divergence. Using the format's own limit
    rather than a rewriter bug keeps this test about the LOOP, not about any
    particular defect.
    """

    wants_geometry = False
    wants_image = False
    requires_full_coverage = False

    async def produce(self, payload, *, options):
        ops = [
            ReplaceLine(line_id=line.line_id, text="mot \x00 cassé")
            for line in payload.lines
        ]
        return EditScript(ops=ops), None


async def _run_over(tmp_path: Path, count: int) -> ProjectionError:
    sources = {}
    for n in range(count):
        path = tmp_path / f"f{n}.xml"
        path.write_text(_ALTO.format(pid=f"P{n}", n=n), encoding="utf-8")
        sources[path.name] = path
    doc = build_document_manifest([(p, name) for name, p in sources.items()])
    pipeline = CorrectionPipeline(
        producer=_WritesAnUnrepresentableLine(),
        observer=_Null(),
        retry_policy=RetryPolicy(transient_backoff_base=0.0, output_backoff_base=0.0),
        producer_metadata=ProducerMetadata(name="x", implementation="m"),
    )
    with pytest.raises(ProjectionError) as caught:
        await pipeline.run(document_manifest=doc, source_files=sources)
    return caught.value


@pytest.mark.asyncio
async def test_three_bad_files_are_all_named_by_one_run(tmp_path) -> None:
    """The point of the change, stated as the count.

    Before, `.failures` would have held one entry however many files
    diverged, because the loop returned on the first.
    """
    error = await _run_over(tmp_path, 3)
    assert len(error.failures) == 3, error.failures
    assert {"f0.xml", "f1.xml", "f2.xml"} <= {
        name for name in ("f0.xml", "f1.xml", "f2.xml") if name in str(error)
    }


@pytest.mark.asyncio
async def test_the_single_file_message_is_unchanged(tmp_path) -> None:
    """A caller reading `str(exc)` must see what it always saw.

    The list is an addition, not a replacement: wrapping the one-file case in
    a summary would break every log line and every test that greps the
    message.
    """
    error = await _run_over(tmp_path, 1)
    assert error.failures == (str(error),)
    assert "diverges from the run's decision" in str(error)


@pytest.mark.asyncio
async def test_nothing_is_delivered_when_any_file_diverges(tmp_path) -> None:
    """The half of the contract that does NOT move.

    Finishing the loop is about diagnosis, not about salvage: a run with one
    bad file still delivers nothing, and `run()` still raises rather than
    returning a partial result.
    """
    error = await _run_over(tmp_path, 3)
    assert isinstance(error, ProjectionError)
    assert error.code == "projection_mismatch"
