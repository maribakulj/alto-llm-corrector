"""Per-call image cap — a vision chunk never exceeds ``max_images``.

A multimodal provider bounds how many images one call may carry (Mistral
rejects a 9th with HTTP 400 ``"Total number of images exceeds the maximum
allowed of 8"``). The vision producer crops EVERY line of the chunk it is
given, so a page chunk of 22 lines is 22 images — over the cap, and the
whole run dies on a 400 that no retry can heal.

``ModelCapabilities.max_images`` already describes the limit and
``reason_cannot_serve`` already explains it; what was missing was the
enforcement. The engine now splits an image-bearing chunk into sibling
chunks that each stay within the cap — the app decides, the descriptor
only informs.

The cap counts LINES SENT, not target lines, because the producer crops
every line it receives. Textual context is not lost by the split:
``prev_text``/``next_text`` are looked up from the whole page, not from
the chunk's own membership.

Default is ``max_images=None`` (unbounded) — an undeclared cap changes
nothing, so every existing run stays byte-identical.
"""

from __future__ import annotations


import pytest

from saknussemm import CorrectionPipeline
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.core.schemas import HyphenRole, ModelCapabilities
from saknussemm.errors import ConfigurationError
from saknussemm.formats.alto.parser import build_document_manifest

from tests._paths import EXAMPLES

_SAMPLE = EXAMPLES / "sample.xml"


class _Null:
    def on_event(self, *a, **k):
        pass


class _CountingVision:
    """Identity vision producer that records how many lines each call got.

    ``wants_image`` is what makes the engine treat its chunks as
    image-bearing; every line in a payload becomes one crop, so
    ``len(payload.lines)`` IS the image count of that call.
    """

    wants_geometry = True
    wants_image = True
    requires_full_coverage = True

    def __init__(self, max_images: int | None) -> None:
        self.metadata = ProducerMetadata(name="vision", implementation="fake")
        self.capabilities = ModelCapabilities(
            text=True, vision=True, structured_output=True, max_images=max_images
        )
        #: Lines received per call — one entry per produce() invocation.
        self.call_sizes: list[int] = []
        #: Line ids received per call, to assert hyphen units stay together.
        self.call_line_ids: list[set[str]] = []

    async def produce(self, payload, *, options):
        self.call_sizes.append(len(payload.lines))
        self.call_line_ids.append({ln.line_id for ln in payload.lines})
        ops = [
            ReplaceLine(line_id=ln.line_id, text=ln.ocr_text) for ln in payload.lines
        ]
        return EditScript(ops=ops), None


def _load():
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    images = {page.page_id: f"{page.page_id}.png" for page in doc.pages}
    return doc, images


def _hyphen_units(doc) -> list[set[str]]:
    """Line-id sets of each hyphen pair, page-local."""
    units: list[set[str]] = []
    for page in doc.pages:
        by_id = {lm.line_id: lm for lm in page.lines}
        for lm in page.lines:
            if lm.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH):
                partner = lm.next_line_id
                if partner and partner in by_id:
                    units.append({lm.line_id, partner})
    return units


@pytest.mark.asyncio
async def test_chunk_is_split_to_respect_max_images():
    """A 10-line page with a 3-image cap reaches the model in calls of at
    most 3 images — and still corrects every line exactly once."""
    doc, images = _load()
    n_lines = sum(len(p.lines) for p in doc.pages)
    assert n_lines > 3, "sample must exceed the cap for this test to mean anything"

    vision = _CountingVision(max_images=3)
    pipeline = CorrectionPipeline(producer=vision, observer=_Null())
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}, page_images=images
    )

    assert vision.call_sizes, "producer was never called"
    assert max(vision.call_sizes) <= 3, f"cap breached: {vision.call_sizes}"
    assert result.fallback_lines == 0
    assert result.report.total_lines == n_lines


@pytest.mark.asyncio
async def test_split_keeps_hyphen_units_in_one_call():
    """Atomicity survives the split: both members of a pair ride the same
    call, so the reconciler still sees a whole unit."""
    doc, images = _load()
    units = _hyphen_units(doc)
    assert units, "sample must carry hyphen units"

    vision = _CountingVision(max_images=3)
    pipeline = CorrectionPipeline(producer=vision, observer=_Null())
    await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}, page_images=images
    )

    for unit in units:
        assert any(unit <= seen for seen in vision.call_line_ids), (
            f"hyphen unit {sorted(unit)} was split across calls: "
            f"{[sorted(s) for s in vision.call_line_ids]}"
        )


@pytest.mark.asyncio
async def test_no_cap_declared_leaves_chunking_untouched():
    """``max_images=None`` is the default and must change nothing — each
    page still reaches the producer whole, in a single call."""
    doc, images = _load()

    vision = _CountingVision(max_images=None)
    pipeline = CorrectionPipeline(producer=vision, observer=_Null())
    await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}, page_images=images
    )

    # One PAGE chunk per page — the sample is two pages (7 + 3 lines).
    assert vision.call_sizes == [len(page.lines) for page in doc.pages]


@pytest.mark.asyncio
async def test_cap_too_small_for_a_hyphen_unit_is_a_configuration_error():
    """A cap of 1 cannot hold a 2-line hyphen unit. That is a
    misconfiguration, not something to paper over by splitting the pair."""
    doc, images = _load()
    assert _hyphen_units(doc), "sample must carry hyphen units"

    vision = _CountingVision(max_images=1)
    pipeline = CorrectionPipeline(producer=vision, observer=_Null())
    with pytest.raises(ConfigurationError, match="max_images"):
        await pipeline.run(
            document_manifest=doc,
            source_files={_SAMPLE.name: _SAMPLE},
            page_images=images,
        )
