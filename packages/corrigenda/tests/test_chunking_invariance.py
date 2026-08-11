"""Chunking must not change the answer.

The planner splits a page into chunks for the model's sake — a budget
concern, not a semantic one. So a producer whose output depends only on
each line's own text must yield the SAME final text for every line
regardless of how the document was chunked. Where that fails, chunking is
leaking into the result, and a run's correctness would depend on a tuning
knob.

Why this test exists: the provider image cap (Mistral refuses a 9th image
in one call) was discovered by a BILLED run dying on an HTTP 400. It is a
chunking-shaped bug, and this is the shape of test that catches that
family offline, for free, before a key is ever used.

Deliberate exclusions, so the comparison stays fair:

* the XML BYTES are not compared. A chunk policy is fingerprinted into the
  output's ``processingStep`` (§11), so two chunkings legitimately produce
  different bytes while deciding identically. The invariant is about
  DECISIONS.
* a chunk budget tight enough to sever a hyphen chain (``HypSplit``) is
  excluded: severing a unit is a documented, recorded unit operation, so a
  different answer there is correct behaviour, not a leak.
"""

from __future__ import annotations


import pytest

from corrigenda import CorrectionPipeline
from corrigenda.core.editing import EditScript, ReplaceLine
from corrigenda.core.protocols import ProducerMetadata
from corrigenda.core.schemas import ChunkPlannerConfig, ModelCapabilities
from corrigenda.formats.alto.parser import build_document_manifest

from tests._paths import EXAMPLES

_SAMPLE = EXAMPLES / "sample.xml"


class _Null:
    def on_event(self, *a, **k):
        pass


class _CapitaliseFirst:
    """Deterministic, context-free, length-preserving correction.

    Depends ONLY on the line's own text — never on its neighbours, its
    chunk's composition, or the order it was seen in. Any difference across
    chunkings therefore comes from the engine, not the producer.

    Length-preserving and first-character-only on purpose: it never touches
    a trailing break hyphen, so hyphen reconciliation behaves identically in
    every configuration.
    """

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self) -> None:
        self.metadata = ProducerMetadata(name="capitalise", implementation="test")
        self.calls = 0

    async def produce(self, payload, *, options):
        self.calls += 1
        ops = [
            ReplaceLine(
                line_id=ln.line_id,
                text=(ln.ocr_text[:1].upper() + ln.ocr_text[1:]),
            )
            for ln in payload.lines
        ]
        return EditScript(ops=ops), None


#: Chunk policies that must all decide identically. Each drives the planner
#: down a different granularity; none is tight enough to sever a hyphen
#: chain (the smallest line budget is 4, and the sample's units are pairs).
_POLICIES = {
    "page": ChunkPlannerConfig(),
    "block": ChunkPlannerConfig(max_input_chars_per_request=400),
    "window": ChunkPlannerConfig(
        max_input_chars_per_request=120, max_lines_per_request=4, line_window_size=4
    ),
    "window-no-overlap": ChunkPlannerConfig(
        max_input_chars_per_request=120,
        max_lines_per_request=4,
        line_window_size=4,
        line_window_overlap=0,
    ),
}


async def _decide(policy: ChunkPlannerConfig) -> tuple[dict, int, int]:
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    producer = _CapitaliseFirst()
    pipeline = CorrectionPipeline(producer=producer, observer=_Null(), config=policy)
    result = await pipeline.run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )
    final = {
        (d.ref.page_id, d.ref.line_id): d.final_text for d in result.decisions.decisions
    }
    return final, result.decisions.fallback_lines, producer.calls


@pytest.mark.asyncio
async def test_every_chunking_decides_the_same_text():
    """The core invariant: same input, same producer, different chunk
    policies → identical final text for every line."""
    baseline, baseline_fallbacks, baseline_calls = await _decide(_POLICIES["page"])
    assert baseline, "sample produced no decisions"
    assert baseline_fallbacks == 0, "baseline must not fall back"

    for name, policy in _POLICIES.items():
        if name == "page":
            continue
        final, fallbacks, calls = await _decide(policy)
        assert final == baseline, (
            f"chunk policy {name!r} changed the outcome — chunking is leaking "
            "into the decision. Differing lines: "
            + repr(
                {
                    k: (baseline.get(k), final.get(k))
                    for k in set(baseline) | set(final)
                    if baseline.get(k) != final.get(k)
                }
            )
        )
        assert fallbacks == 0, f"chunk policy {name!r} introduced a fallback"
        # Sanity: the policies must actually differ in how they chunk,
        # otherwise this test would pass while comparing nothing.
        if name.startswith("window"):
            assert calls > baseline_calls, (
                f"policy {name!r} was expected to split into more chunks than "
                f"the page baseline ({calls} vs {baseline_calls}) — the test "
                "is not exercising a different chunking"
            )


@pytest.mark.asyncio
async def test_rerunning_the_same_policy_is_stable():
    """Idempotence of the run itself: the same policy twice decides the same
    thing. Guards the comparison above against being noise."""
    first, _, _ = await _decide(_POLICIES["window"])
    second, _, _ = await _decide(_POLICIES["window"])
    assert first == second


class _CapitaliseFirstVision(_CapitaliseFirst):
    """Same context-free transform, but declaring itself image-bearing with a
    per-call image cap — so the engine's image-cap split applies."""

    wants_geometry = True
    wants_image = True

    def __init__(self, max_images: int | None) -> None:
        super().__init__()
        self.capabilities = ModelCapabilities(
            text=True, vision=True, structured_output=True, max_images=max_images
        )


async def _decide_vision(max_images: int | None) -> tuple[dict, int]:
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    producer = _CapitaliseFirstVision(max_images)
    pipeline = CorrectionPipeline(producer=producer, observer=_Null())
    result = await pipeline.run(
        document_manifest=doc,
        source_files={_SAMPLE.name: _SAMPLE},
        page_images={page.page_id: f"{page.page_id}.png" for page in doc.pages},
    )
    final = {
        (d.ref.page_id, d.ref.line_id): d.final_text for d in result.decisions.decisions
    }
    return final, producer.calls


@pytest.mark.asyncio
async def test_the_image_cap_split_does_not_change_the_answer():
    """Declaring a per-call image cap changes how many calls are made — it
    must not change what is decided.

    This is the incident that motivated this file, expressed as an
    invariant: an 8-image provider limit was found by a billed run dying on
    an HTTP 400. Splitting to respect the cap is a budget decision, so the
    decisions must be identical with the cap on and off.
    """
    uncapped, uncapped_calls = await _decide_vision(None)
    capped, capped_calls = await _decide_vision(2)

    assert capped_calls > uncapped_calls, (
        f"a cap of 2 should force more calls than none ({capped_calls} vs "
        f"{uncapped_calls}) — the split is not being exercised"
    )
    assert capped == uncapped, (
        "the image-cap split changed the outcome. Differing lines: "
        + repr(
            {
                k: (uncapped.get(k), capped.get(k))
                for k in set(uncapped) | set(capped)
                if uncapped.get(k) != capped.get(k)
            }
        )
    )
