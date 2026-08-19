"""One run, every undeliverable file — not one finding per run.

The projection invariant withholds a file whose artefact does not say what
the run decided, and that withholding is right: a divergent file is
corruption of the deliverable, not a degradation to grade. What was wrong is
that the rewrite loop *stopped* at the first one.

A run is billed. Discovering a second bad file therefore cost a second full
pass over the producer — the corpus re-sent, the tokens re-paid, the wait
re-taken — to learn something the first run already had in hand three
milliseconds of lxml later. Three bad files in a volume meant three bills.

Finishing the loop is what makes the *shape* of a failure readable too: one
bad file out of three hundred is a local accident, three hundred out of three
hundred is a broken configuration. Returning on the first made those two
indistinguishable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saknussemm import CorrectionPipeline
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.core.schemas import RetryPolicy
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


async def _run_over(tmp_path: Path, count: int):
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
    return await pipeline.run(document_manifest=doc, source_files=sources)


@pytest.mark.asyncio
async def test_three_bad_files_are_all_named_by_one_run(tmp_path) -> None:
    """The point of the change, stated as the count.

    Before, one entry however many files diverged, because the loop
    returned on the first — so the second cost another billed run.
    """
    result = await _run_over(tmp_path, 3)
    assert set(result.undeliverable_files) == {"f0.xml", "f1.xml", "f2.xml"}


@pytest.mark.asyncio
async def test_each_one_says_which_line_and_why(tmp_path) -> None:
    """A count is not a diagnosis: the reason travels per file.

    Without it the caller knows a file is missing and has to re-run under a
    debugger to learn what for — which is the cost this module exists to
    remove.
    """
    result = await _run_over(tmp_path, 2)
    for name, why in result.undeliverable_files.items():
        assert name in why, why
        assert "diverges from the run's decision" in why, why


@pytest.mark.asyncio
async def test_a_withheld_file_is_absent_never_doubtful(tmp_path) -> None:
    """The half of the contract that does NOT move.

    Finishing the loop is about diagnosis, never salvage. A file whose
    artefact diverged is not handed back in a lesser version — it is not
    handed back at all, and a lookup by name says so.
    """
    result = await _run_over(tmp_path, 3)
    assert result.corrected_files == {}
    with pytest.raises(KeyError):
        result.corrected_files["f0.xml"]
