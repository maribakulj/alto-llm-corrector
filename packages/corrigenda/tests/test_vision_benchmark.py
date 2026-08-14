"""Vision benchmark harness (scripts/vision_benchmark.py) — offline plumbing.

Validates the measurement logic — CER, GT-degradation, and the
text/vision/hybrid comparison with the escalation router — WITHOUT the real
image corpus or any network: fake producers stand in for the LLM/VLM, so
the numbers exercise the harness, not a model. The real-image cropping is
covered by test_vision.py; the real-corpus run is a human step.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest

from corrigenda.core.editing import EditScript, ReplaceLine
from corrigenda.core.protocols import ProducerMetadata
from corrigenda.core.quality import RoutingPolicy
from corrigenda.core.schemas import HyphenRole
from corrigenda.formats.alto.parser import build_document_manifest

from tests._paths import REPO

_REPO_ROOT = REPO
_SCRIPT = _REPO_ROOT / "scripts" / "vision_benchmark.py"
_SAMPLE = _REPO_ROOT / "examples" / "sample.xml"

_spec = importlib.util.spec_from_file_location("vision_benchmark", _SCRIPT)
assert _spec and _spec.loader
vb = importlib.util.module_from_spec(_spec)
sys.modules["vision_benchmark"] = vb
_spec.loader.exec_module(vb)


# ---------------------------------------------------------------------------
# CER
# ---------------------------------------------------------------------------


def test_levenshtein():
    assert vb.levenshtein("abc", "abc") == 0
    assert vb.levenshtein("kitten", "sitting") == 3
    assert vb.levenshtein("", "abc") == 3
    assert vb.levenshtein("abc", "") == 3


def test_corpus_cer():
    # one substitution over 3 ref chars, plus a perfect line.
    assert vb.corpus_cer([("abd", "abc"), ("x", "x")]) == pytest.approx(1 / 4)
    assert vb.corpus_cer([]) == 0.0


# ---------------------------------------------------------------------------
# GT degradation
# ---------------------------------------------------------------------------


def test_degrade_manifest_preserves_structure_and_captures_gt():
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    degraded, gt = vb.degrade_manifest(doc, seed=1837, rate_percent=80)

    orig_lines = [lm for p in doc.pages for lm in p.lines]
    deg_lines = [lm for p in degraded.pages for lm in p.lines]
    assert len(orig_lines) == len(deg_lines)
    # GT keyed by (document_id, line_id); structure/coords untouched.
    for o, d in zip(orig_lines, deg_lines):
        assert gt[(degraded.document_id, d.line_id)] == o.ocr_text
        assert d.coords == o.coords
    # At an 80% rate at least one degradable line actually changed.
    assert any(d.ocr_text != o.ocr_text for o, d in zip(orig_lines, deg_lines))


# ---------------------------------------------------------------------------
# Fake producers + run_config
# ---------------------------------------------------------------------------


class _Text:
    """Identity text producer — leaves the degraded text as-is."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True
    metadata = ProducerMetadata(name="text", implementation="identity")

    async def produce(self, payload, *, options):
        ops = [
            ReplaceLine(line_id=ln.line_id, text=ln.ocr_text) for ln in payload.lines
        ]
        return EditScript(ops=ops), None


class _OracleVision:
    """Perfect VLM stand-in (no image needed) — returns GT text."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self, gt):
        self._gt = gt
        self.metadata = ProducerMetadata(name="vision", implementation="gt")

    async def produce(self, payload, *, options):
        ops = [
            ReplaceLine(
                line_id=ln.line_id,
                text=self._gt.get((payload.document_id, ln.line_id), ln.ocr_text),
            )
            for ln in payload.lines
        ]
        return EditScript(ops=ops), None


def _one_doc(seed=1837, rate=80):
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    degraded, gt = vb.degrade_manifest(doc, seed=seed, rate_percent=rate)
    docs = [(degraded, {_SAMPLE.name: _SAMPLE}, {})]
    noisy = {
        ln.ocr_text
        for p in degraded.pages
        for ln in p.lines
        if ln.ocr_text != gt[(degraded.document_id, ln.line_id)]
    }
    return docs, gt, noisy


def test_apply_ocr_manifest_replaces_input_and_keeps_gt():
    """Real-OCR mode: the manifest's text becomes the engine's reading, the
    GT is captured as the reference, geometry is untouched."""
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    first = doc.pages[0].lines[0]
    ocred, gt = vb.apply_ocr_manifest(doc, {first.line_id: "raw OCR reading"})
    out_first = ocred.pages[0].lines[0]
    assert out_first.ocr_text == "raw OCR reading"
    assert gt[(ocred.document_id, first.line_id)] == first.ocr_text
    assert out_first.coords == first.coords


def test_apply_ocr_manifest_keeps_gt_when_engine_returned_nothing():
    """An empty reading is a real OCR outcome; the line keeps its GT text
    rather than becoming an empty line that would flatter every config."""
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    first = doc.pages[0].lines[0]
    ocred, _ = vb.apply_ocr_manifest(doc, {first.line_id: ""})
    assert ocred.pages[0].lines[0].ocr_text == first.ocr_text


def test_swapping_the_text_re_derives_the_hyphenation() -> None:
    """The note and the text may not disagree — the defect the 2026-08-14
    campaign found in itself.

    Both input modes parse the GROUND-TRUTH ALTO and then overwrite every
    ``ocr_text``. Hyphenation is detected in the parser's first pass, on
    the text present then, so without a re-derivation the manifest keeps
    break marks read off the HUMAN transcription while carrying engine
    text that has none. No parser can produce that state: a heuristic
    PART1 is heuristic BECAUSE its text ends on a break mark.

    On ``corpus/37-GT-BNL`` it made 21 of 94 break lines incoherent, and
    the pipeline reverted their pairs — read as a quality regression when
    it was an artefact of the harness.
    """
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    marked = doc.pages[0].lines[0]

    # The GT half: a line the parser reads as a break line.
    marked.ocr_text = "conti⸗"
    vb.rederive_heuristic_hyphenation(doc)
    assert marked.hyphen_role is HyphenRole.PART1, (
        "a line whose text ends on a repertoire break mark must be PART1 — "
        "otherwise this test is not exercising the derivation at all"
    )

    # The OCR half: the engine dropped the mark, as Tesseract does on all
    # 24 of the corpus's ``⸗`` lines.
    ocred, _ = vb.apply_ocr_manifest(doc, {marked.line_id: "conti"})
    out = ocred.pages[0].lines[0]
    assert out.ocr_text == "conti"
    assert out.hyphen_role is HyphenRole.NONE, (
        "the break note survived a text swap that removed the break mark: "
        "the manifest now claims a hyphenation the text it carries does "
        "not show, and the pair reconciler will revert both members"
    )


def test_explicit_hyphenation_survives_a_text_swap() -> None:
    """Markup-asserted hyphenation is NOT text-derived, so swapping the
    text does not invalidate it. Only the heuristic side is recomputed —
    dropping an engine's own ``SUBS_TYPE`` would be a different lie."""
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    line = doc.pages[0].lines[0]
    line.hyphen_role = HyphenRole.PART1
    line.hyphen_source_explicit = True
    line.hyphen_subs_content = "continuation"

    ocred, _ = vb.apply_ocr_manifest(doc, {line.line_id: "no mark here"})
    out = ocred.pages[0].lines[0]
    assert out.hyphen_role is HyphenRole.PART1
    assert out.hyphen_subs_content == "continuation"


@pytest.mark.asyncio
async def test_vision_beats_identity_text():
    docs, gt, _ = _one_doc()
    text = await vb.run_config("text", docs=docs, gt=gt, producer=_Text())
    vision = await vb.run_config("vision", docs=docs, gt=gt, producer=_OracleVision(gt))
    assert vision.cer < text.cer  # the oracle recovers GT
    assert vision.cer == pytest.approx(0.0, abs=1e-9)
    assert text.lines == vision.lines > 0


@pytest.mark.asyncio
async def test_hybrid_escalates_noisy_lines_only():
    docs, gt, noisy = _one_doc()
    assert noisy, "the sample must have degradable lines for this test"
    hybrid = await vb.run_config(
        "hybrid",
        docs=docs,
        gt=gt,
        producer=_Text(),
        escalation_producer=_OracleVision(gt),
        qe_scorer=vb.OracleQEScorer(noisy),
        routing_policy=RoutingPolicy(escalate_at_or_above=0.5),
    )
    text = await vb.run_config("text", docs=docs, gt=gt, producer=_Text())
    # Escalation happened, and routing the noisy lines to the oracle beats
    # text-only — the hybrid thesis, in miniature.
    assert hybrid.escalated_lines > 0
    assert hybrid.cer < text.cer
