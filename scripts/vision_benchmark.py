"""Vision benchmark harness — text vs vision vs hybrid (ROADMAP V3 Phase 4, 7).

Measures whether a vision producer earns its cost on a REAL image+ALTO
ground-truth corpus. The method is honest about what is synthetic and what
is real:

  * REAL: the page images (scans) and the ground-truth transcription
    (the ALTO ``CONTENT``), from a paired ``NNNN.xml`` / ``NNNN.png``
    corpus (e.g. the BNL 19th-c. press GT: ALTO v4, ``MeasurementUnit
    mm10``, scans at 300 DPI so the XML→pixel transform is a uniform
    ``dpi/254`` ≈ 1.1811 scale — verified on the corpus).
  * SYNTHETIC: the OCR *errors*. Each GT line is degraded into a plausible
    OCR reading by the same deterministic, RNG-free scripted degrader the
    Phase-2 QE data uses (``scripts/qe_data.degrade_token``); the degraded
    text is the pipeline INPUT, the GT is the reference.

Three configurations correct the degraded input and are scored by
character error rate (CER) against the GT, alongside the real call cost
(``producer_calls``) and how many lines were escalated:

  * ``text``   — the text producer alone;
  * ``vision`` — the vision producer on every line;
  * ``hybrid`` — text producer + a QE router escalating the risky lines to
    the vision producer (``escalation_producer=``).

The core measurement lives in importable functions (tested offline in
``tests/test_vision_benchmark.py``). ``main`` runs a ``plumbing`` mode with
DETERMINISTIC oracle producers — no network, no API key — which validates
the whole harness end to end (it really crops every escalated line from the
real scans) and shows the cost/quality trade-off the numbers must exhibit;
swap in real LLM/VLM providers for a production benchmark.

Usage::

    python scripts/vision_benchmark.py --corpus /path/to/"37 GT BNL" --dpi 300
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "packages" / "corrigenda" / "src"))
sys.path.insert(0, str(_REPO_ROOT))  # scripts.qe_data

from scripts.qe_data import degrade_token  # noqa: E402

from corrigenda import CorrectionPipeline  # noqa: E402
from corrigenda.core.editing import EditScript, ReplaceLine  # noqa: E402
from corrigenda.core.protocols import ProducerMetadata  # noqa: E402
from corrigenda.core.quality import RoutingPolicy  # noqa: E402
from corrigenda.core.schemas import (  # noqa: E402
    DocumentManifest,
    ImageAsset,
    ImageTransform,
)
from corrigenda.formats.alto.parser import build_document_manifest  # noqa: E402
from corrigenda.producers.rules import (  # noqa: E402
    RulesProducer,
    default_french_ocr_rules,
)

#: ALTO ``MeasurementUnit mm10`` → pixels is ``px = mm10 * dpi / 254`` (a mm10
#: is 0.1 mm; 1 inch = 25.4 mm = 254 mm10). At 300 DPI this is ≈ 1.1811.
_MM10_PER_INCH = 254.0


# ---------------------------------------------------------------------------
# Character error rate
# ---------------------------------------------------------------------------


def levenshtein(a: str, b: str) -> int:
    """Classic two-row edit distance (stdlib, no dependency)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def corpus_cer(pairs: list[tuple[str, str]]) -> float:
    """Aggregate CER over ``(hypothesis, reference)`` line pairs:
    total edit distance / total reference length."""
    dist = sum(levenshtein(hyp, ref) for hyp, ref in pairs)
    ref_chars = sum(len(ref) for _, ref in pairs)
    return dist / ref_chars if ref_chars else 0.0


# ---------------------------------------------------------------------------
# Degradation: GT manifest -> degraded-input manifest (+ GT reference)
# ---------------------------------------------------------------------------


def degrade_manifest(
    doc: DocumentManifest, *, seed: int, rate_percent: int
) -> tuple[DocumentManifest, dict[tuple[str, str], str]]:
    """Return ``(input_manifest, gt_by_line)``: a deep copy of ``doc`` whose
    every line's ``ocr_text`` is the scripted OCR degradation of its GT text,
    keyed reference captured as ``(page_id, line_id) -> gt_text``.

    Geometry, ids and structure are untouched — only the text degrades, so
    the pipeline receives the same page it would from a real OCR of the
    scan, just with synthetic errors whose truth we know."""
    gt_by_line: dict[tuple[str, str], str] = {}
    degraded = doc.model_copy(deep=True)
    doc_id = degraded.document_id
    index = 0
    for page in degraded.pages:
        for line in page.lines:
            gt = line.ocr_text
            # Key by (document_id, line_id): bare line_ids repeat across
            # files (every ALTO names its first line TL_0001), and each
            # file's page is P_0001 too — only the per-run document_id
            # (a uuid) is unique across the corpus.
            gt_by_line[(doc_id, line.line_id)] = gt
            tokens = [
                degrade_token(tok, seed=seed, index=index, rate_percent=rate_percent)
                for tok in gt.split()
            ]
            line.ocr_text = " ".join(tokens)
            index += 1
    return degraded, gt_by_line


# ---------------------------------------------------------------------------
# Deterministic oracle producers (plumbing mode)
# ---------------------------------------------------------------------------


class OracleVisionProducer:
    """A stand-in for a perfect VLM: returns the GT text for every line.

    ``wants_image=True`` so the pipeline copies the §4.1 envelope and this
    producer REALLY crops each escalated line from the scan (exercising
    ``crop_region`` at corpus scale) — it then ignores the pixels and
    answers from the injected GT, so the plumbing run is deterministic and
    offline. Replace with a real multimodal producer for a true benchmark.

    The GT is keyed by ``(document_id, line_id)`` — bare line_ids repeat
    across files (every ALTO calls its first line ``TL_0001``), so the
    document id is what disambiguates.
    """

    wants_geometry = True
    wants_image = True
    requires_full_coverage = True

    def __init__(self, gt_by_line: dict[tuple[str, str], str]) -> None:
        self._gt = gt_by_line
        self.metadata = ProducerMetadata(name="oracle-vision", implementation="gt")
        self.crops = 0

    async def produce(self, payload, *, options):
        from corrigenda.integrations.vision import crop_region

        asset = payload.image_ref
        ops = []
        for ln in payload.lines:
            if isinstance(asset, ImageAsset) and ln.geometry is not None:
                crop_region(asset, ln.geometry.coords, margin_ratio=0.05)
                self.crops += 1
            gt = self._gt.get((payload.document_id, ln.line_id), ln.ocr_text)
            ops.append(ReplaceLine(line_id=ln.line_id, text=gt))
        return EditScript(ops=ops), None


class OracleQEScorer:
    """Plumbing-mode QE oracle: flags exactly the lines a degradation
    actually changed, so the hybrid escalates the noisy lines and leaves the
    clean ones to the text producer — the ideal cost/quality split a real
    QE scorer approximates. Scores by text membership (the router only sees
    a line's text), so it needs the SET of degraded input texts."""

    def __init__(self, noisy_texts: set[str]) -> None:
        self._noisy = noisy_texts

    def needs_correction(self, text: str) -> float:
        return 0.99 if text in self._noisy else 0.0


# ---------------------------------------------------------------------------
# Running one configuration
# ---------------------------------------------------------------------------


@dataclass
class ConfigResult:
    name: str
    cer: float
    producer_calls: int = 0
    escalated_lines: int = 0
    lines: int = 0
    crops: int = 0
    pairs: list[tuple[str, str]] = field(default_factory=list)


class _Null:
    def on_event(self, *a, **k):
        pass


async def run_config(
    name: str,
    *,
    docs: list[tuple[DocumentManifest, dict[str, Path], dict[str, ImageAsset]]],
    gt: dict[tuple[str, str], str],
    producer,
    escalation_producer=None,
    qe_scorer=None,
    routing_policy: RoutingPolicy | None = None,
) -> ConfigResult:
    """Correct every degraded document with one configuration and score it."""
    pipeline = CorrectionPipeline(
        producer=producer,
        observer=_Null(),
        qe_scorer=qe_scorer,
        routing_policy=routing_policy or RoutingPolicy(),
        escalation_producer=escalation_producer,
    )
    res = ConfigResult(name=name, cer=0.0)
    for doc, source_files, images in docs:
        result = await pipeline.run(
            document_manifest=doc,
            source_files=source_files,
            page_images=images or None,
        )
        res.producer_calls += result.producer_calls
        res.escalated_lines += result.escalated_lines
        # ADR-011 — run() never mutates its input; the corrected text lives
        # on the report's per-line outcomes (final_text), keyed uniquely
        # within this one run by (page_id, line_id).
        final = {
            (o.page_id, o.line_id): o.decision.final_text for o in result.report.lines
        }
        for page in doc.pages:
            for line in page.lines:
                out = final.get((page.page_id, line.line_id), line.ocr_text)
                ref = gt[(doc.document_id, line.line_id)]
                res.pairs.append((out, ref))
    res.lines = len(res.pairs)
    res.cer = corpus_cer(res.pairs)
    for p in (producer, escalation_producer):
        res.crops += getattr(p, "crops", 0)
    return res


# ---------------------------------------------------------------------------
# The benchmark
# ---------------------------------------------------------------------------


def benchmark(corpus_dir: Path, *, dpi: float, seed: int, rate_percent: int) -> dict:
    """Run the three configurations over the corpus and return the report."""
    xmls = sorted(p for p in corpus_dir.glob("*.xml"))
    docs: list[tuple[DocumentManifest, dict[str, Path], dict[str, ImageAsset]]] = []
    gt: dict[tuple[str, str], str] = {}
    baseline_pairs: list[tuple[str, str]] = []

    noisy_texts: set[str] = set()
    scale = dpi / _MM10_PER_INCH
    for xml in xmls:
        png = xml.with_suffix(".png")
        if not png.exists():
            continue
        clean = build_document_manifest([(xml, xml.name)])
        degraded, gt_part = degrade_manifest(
            clean, seed=seed, rate_percent=rate_percent
        )
        gt.update(gt_part)
        images = {
            page.page_id: ImageAsset(
                page_id=page.page_id,
                uri=str(png),
                transform=ImageTransform(scale_x=scale, scale_y=scale),
            )
            for page in degraded.pages
        }
        docs.append((degraded, {xml.name: xml}, images))
        for page in degraded.pages:
            for line in page.lines:
                ref = gt_part[(degraded.document_id, line.line_id)]
                baseline_pairs.append((line.ocr_text, ref))
                if line.ocr_text != ref:
                    noisy_texts.add(line.ocr_text)

    if not docs:
        raise SystemExit(f"no *.xml + *.png pairs found under {corpus_dir}")

    import asyncio

    text = RulesProducer(default_french_ocr_rules())
    vision = OracleVisionProducer(gt)
    hybrid_text = RulesProducer(default_french_ocr_rules())
    hybrid_vision = OracleVisionProducer(gt)

    configs = [
        run_config("text", docs=docs, gt=gt, producer=text),
        run_config("vision", docs=docs, gt=gt, producer=vision),
        run_config(
            "hybrid",
            docs=docs,
            gt=gt,
            producer=hybrid_text,
            escalation_producer=hybrid_vision,
            # Plumbing mode: an oracle QE escalates exactly the degraded
            # lines. A real benchmark swaps in HeuristicQEScorer or the
            # corrigenda[qe] MaskedLMQEScorer and tunes the bound.
            qe_scorer=OracleQEScorer(noisy_texts),
            routing_policy=RoutingPolicy(escalate_at_or_above=0.5),
        ),
    ]
    results = asyncio.run(_gather(configs))

    return {
        "corpus_dir": str(corpus_dir),
        "pages": len(docs),
        "lines": results[0].lines,
        "dpi": dpi,
        "mm10_to_px_scale": round(scale, 4),
        "seed": seed,
        "rate_percent": rate_percent,
        "baseline_cer": round(corpus_cer(baseline_pairs), 4),
        "configs": [
            {
                "name": r.name,
                "cer": round(r.cer, 4),
                "producer_calls": r.producer_calls,
                "escalated_lines": r.escalated_lines,
                "crops": r.crops,
            }
            for r in results
        ],
    }


async def _gather(coros: list) -> list[ConfigResult]:
    out = []
    for c in coros:
        out.append(await c)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="directory of paired NNNN.xml (ALTO) + NNNN.png (scan)",
    )
    parser.add_argument("--dpi", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=1837)
    parser.add_argument("--rate", type=int, default=30, help="degradation %%")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    report = benchmark(
        args.corpus, dpi=args.dpi, seed=args.seed, rate_percent=args.rate
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
