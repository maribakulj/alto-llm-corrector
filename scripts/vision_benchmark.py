"""Vision benchmark harness — text vs vision vs hybrid (ROADMAP V3 Phase 4, 7).

Measures whether a vision producer earns its cost on a REAL image+ALTO
ground-truth corpus. The scans and the reference are always real (the ALTO
``CONTENT`` of a GT corpus is a human transcription); what varies is where
the INPUT text comes from:

  * ``--ocr sidecar.json`` (**preferred**) — REAL OCR of the corpus's own
    line images, produced by ``scripts/ocr_corpus.py`` (Tesseract, one crop
    per GT line). Nothing in the measurement is synthetic then: real scans,
    real OCR errors, human reference. Real OCR fails in ways no
    substitution table reproduces — merged words, dropped characters,
    apostrophe drift, hallucinated glyphs.
  * default — SYNTHETIC errors: each GT line is degraded by the
    deterministic, RNG-free scripted degrader the Phase-2 QE data uses
    (``scripts/qe_data.degrade_token``). Useful when no OCR engine is
    available; the report's ``input`` block always says which was used.

The corpus is a paired ``NNNN.xml`` / ``NNNN.png`` set (e.g. the BNL
19th-c. press GT: ALTO v4, ``MeasurementUnit mm10``, scans at 300 DPI so
the XML→pixel transform is a uniform ``dpi/254`` ≈ 1.1811 scale — verified
on the corpus).

Three configurations correct the degraded input and are scored by
character error rate (CER) against the GT, alongside the real call cost
(``producer_calls``) and how many lines were escalated:

  * ``text``   — the text producer alone;
  * ``vision`` — the vision producer on every line;
  * ``hybrid`` — text producer + a QE router escalating the risky lines to
    the vision producer (``escalation_producer=``).

Who plays the VLM is the other axis, and confusing it with the one above
has already misled readers of this repo — so the report always carries a
``producer`` block naming it:

  * default — DETERMINISTIC oracle producers: no network, no API key. The
    oracle is handed the GT and returns it, so its CER is the **plumbing
    floor** (what survives the guards and the reconciler when the answer is
    already perfect), NOT a model score. This mode validates the harness
    end to end and really crops every escalated line from the real scans.
  * ``--provider mistral|anthropic`` — a REAL VLM over the network. Only
    this answers "does a model improve the text", and only this costs money.

An aggregate CER hides a heterogeneous corpus (the BNL GT is 71% French,
29% German fraktur), so every report also breaks the score down per source
file under ``per_file``.

Usage::

    python scripts/ocr_corpus.py --corpus /path/to/GT --lang fra --out ocr.json
    # plumbing floor (offline, free)
    python scripts/vision_benchmark.py --corpus /path/to/GT --ocr ocr.json
    # real model (costs API calls; --limit N first to smoke-test the wiring)
    python scripts/vision_benchmark.py --corpus /path/to/GT --ocr ocr.json \\
        --provider mistral --only text,vision
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "packages" / "lidenbrock" / "src"))
sys.path.insert(0, str(_REPO_ROOT))  # scripts.qe_data

from scripts.qe_data import degrade_token  # noqa: E402

from lidenbrock import CorrectionPipeline  # noqa: E402
from lidenbrock.core.editing import EditScript, ReplaceLine  # noqa: E402
from lidenbrock.core.protocols import ProducerMetadata  # noqa: E402
from lidenbrock.core.quality import RoutingPolicy  # noqa: E402
from lidenbrock.core.pairing import (  # noqa: E402
    HYPHEN_CHARS,
    link_hyphen_pairs,
    trailing_hyphen_char,
)
from lidenbrock.core.schemas import (  # noqa: E402
    DocumentManifest,
    HyphenRole,
    ImageAsset,
    ImageTransform,
)
from lidenbrock.formats.alto.parser import build_document_manifest  # noqa: E402
from lidenbrock.producers.rules import (  # noqa: E402
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


def rederive_heuristic_hyphenation(doc: DocumentManifest) -> None:
    """Re-derive text-detected hyphenation after the input text is swapped in.

    Both input modes build the manifest by parsing the GROUND-TRUTH ALTO
    and then overwriting every ``ocr_text``. Hyphenation is detected in
    the parser's first pass, on the text present at parse time — so
    without this, the manifest keeps hyphenation derived from the HUMAN
    transcription while carrying OCR text. That is a state no parser can
    produce: a heuristic PART1 is heuristic *because* its text ends on a
    break mark, so the note and the text cannot disagree.

    Measured on ``corpus/37-GT-BNL`` with the 2026-07-25 sidecar: the GT
    has 24 lines ending in ``⸗``, the Tesseract reading has **zero**, and
    22 of the 94 PART1/BOTH lines ended up marked as break lines over
    text with no break mark. `542c783` — which taught the parser the
    whole repertoire — made that reachable, and the 2026-08-14 campaign
    read the resulting pair fallbacks as a quality regression. They were
    an artefact of this function's absence.

    Explicit hyphenation (``SUBS_TYPE``/``HYP`` in the markup) is left
    alone: it is asserted by the file, not read off the text, so swapping
    the text does not invalidate it. This corpus has none — all 94 break
    lines are heuristic.

    The derivation itself stays in the library: ``trailing_hyphen_char``
    is the parser's own predicate (repertoire + the alphabetic-before
    rule that rejects ``1789-``), and ``link_hyphen_pairs`` is the
    parser's own second pass (geometric vetting, blank lines skipped
    over). What lives here is the wiring, not a second copy of the rule.
    """
    for page in doc.pages:
        for line in page.lines:
            if line.hyphen_source_explicit or line.hyphen_forward_explicit:
                continue
            line.hyphen_role = HyphenRole.NONE
            line.hyphen_pair_line_id = None
            line.hyphen_pair_page_id = None
            line.hyphen_subs_content = None
            line.hyphen_forward_pair_id = None
            line.hyphen_forward_pair_page_id = None
            line.hyphen_forward_subs_content = None
            if trailing_hyphen_char(line.ocr_text, HYPHEN_CHARS) is not None:
                line.hyphen_role = HyphenRole.PART1
        link_hyphen_pairs(page.lines)


def apply_ocr_manifest(
    doc: DocumentManifest, readings: dict[str, str]
) -> tuple[DocumentManifest, dict[tuple[str, str], str]]:
    """Same contract as :func:`degrade_manifest`, but the input text comes
    from a REAL OCR engine (``scripts/ocr_corpus.py``) instead of scripted
    degradation — the last synthetic ingredient removed.

    ``readings`` maps ``line_id -> raw OCR text`` for THIS file (line_ids
    are unique per source file). A line the engine returned nothing for
    keeps its GT text and is reported by the caller: an empty reading is a
    real OCR outcome, but silently treating it as a correct line would
    flatter every configuration equally.
    """
    gt_by_line: dict[tuple[str, str], str] = {}
    ocred = doc.model_copy(deep=True)
    doc_id = ocred.document_id
    for page in ocred.pages:
        for line in page.lines:
            gt_by_line[(doc_id, line.line_id)] = line.ocr_text
            raw = readings.get(line.line_id)
            if raw:
                line.ocr_text = raw
    rederive_heuristic_hyphenation(ocred)
    return ocred, gt_by_line


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
    rederive_heuristic_hyphenation(degraded)
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
        from lidenbrock.integrations.vision import crop_region

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


def _line_deltas(triples: list[tuple[str, str, str, str, str]]) -> dict[str, int]:
    """Per-line verdicts for one config: did each line get better or worse?

    ``false_positives`` are the worst kind — the line was ALREADY correct
    and the model broke it. On clean OCR that is the whole risk, and it is
    exactly what the SKIP tier of the hybrid router exists to avoid.
    """
    improved = degraded = unchanged = false_positives = 0
    for _f, _lid, ocr, out, ref in triples:
        before, after = levenshtein(ocr, ref), levenshtein(out, ref)
        if after < before:
            improved += 1
        elif after > before:
            degraded += 1
            if before == 0:
                false_positives += 1
        else:
            unchanged += 1
    return {
        "lines_improved": improved,
        "lines_degraded": degraded,
        "lines_unchanged": unchanged,
        "false_positives": false_positives,
    }


@dataclass
class ConfigResult:
    name: str
    cer: float
    producer_calls: int = 0
    escalated_lines: int = 0
    lines: int = 0
    crops: int = 0
    pairs: list[tuple[str, str]] = field(default_factory=list)
    #: source file name → that file's own (output, reference) pairs. A
    #: corpus is rarely homogeneous — the BNL GT is 71% French and 29%
    #: German fraktur — and one aggregate CER averages regimes that can
    #: differ by an order of magnitude. Per-file scores let a reader
    #: regroup by whatever property matters (language, script, date)
    #: without re-running the model.
    by_file: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    #: (file, line_id, input OCR, output, reference) for EVERY line. An
    #: aggregate CER can fall while individual lines are wrecked — on this
    #: corpus one page went from CER 0.0402 to 0.0513 while the corpus
    #: average improved, and nothing in the report said so. Keeping the
    #: triples lets the report count improved/degraded lines and lets an
    #: audit look for the damage a mean hides.
    triples: list[tuple[str, str, str, str, str]] = field(default_factory=list)


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
    guard_config=None,
) -> ConfigResult:
    """Correct every degraded document with one configuration and score it.

    ``guard_config`` is the Stage-C/B guard profile. It is left ``None``
    (engine default, ``min_source_similarity=0.35``) for the oracle
    plumbing run, and set to ``GuardConfig.vision()`` for a real VLM: a
    model that reads the image can legitimately return text far from a
    badly-garbled OCR line, which the text floor would reject. Since the
    floor decides which proposals survive, it is part of what the CER
    measures — the report records it.
    """
    kwargs: dict = {}
    if guard_config is not None:
        kwargs["guard_config"] = guard_config
    pipeline = CorrectionPipeline(
        producer=producer,
        observer=_Null(),
        qe_scorer=qe_scorer,
        routing_policy=routing_policy or RoutingPolicy(),
        escalation_producer=escalation_producer,
        **kwargs,
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
        fname = next(iter(source_files), doc.document_id)
        bucket = res.by_file.setdefault(fname, [])
        for page in doc.pages:
            for line in page.lines:
                out = final.get((page.page_id, line.line_id), line.ocr_text)
                ref = gt[(doc.document_id, line.line_id)]
                res.pairs.append((out, ref))
                bucket.append((out, ref))
                res.triples.append((fname, line.line_id, line.ocr_text, out, ref))
    res.lines = len(res.pairs)
    res.cer = corpus_cer(res.pairs)
    for p in (producer, escalation_producer):
        res.crops += getattr(p, "crops", 0)
    return res


# ---------------------------------------------------------------------------
# The benchmark
# ---------------------------------------------------------------------------


def benchmark(
    corpus_dir: Path,
    *,
    dpi: float,
    seed: int,
    rate_percent: int,
    ocr_sidecar: Path | None = None,
    provider: str | None = None,
    model: str | None = None,
    limit: int | None = None,
    only: tuple[str, ...] = ("text", "vision", "hybrid"),
    dump_lines: Path | None = None,
) -> dict:
    """Run the selected configurations over the corpus and return the report.

    ``ocr_sidecar`` (from ``scripts/ocr_corpus.py``) makes the INPUT real
    OCR instead of scripted degradation — with it, nothing in the
    measurement is synthetic: real scans, real OCR errors, human reference.

    ``provider`` decides what plays the VLM, and it is the difference
    between two measurements that must never be confused:

    * ``None`` — :class:`OracleVisionProducer`, which ignores the pixels
      and returns the GT. Its CER is the **plumbing floor**: what survives
      the guards and the reconciler when the answer is already perfect. It
      is NOT a model score, and reading it as one has already misled
      readers of this repo.
    * ``"mistral"`` / ``"anthropic"`` — a real VLM over the network. Only
      this answers "does a model improve the text".

    The returned report always carries a ``producer`` block naming which
    one ran, so no downstream table can lose that distinction.
    """
    xmls = sorted(p for p in corpus_dir.glob("*.xml"))
    if limit is not None:
        xmls = xmls[:limit]
    docs: list[tuple[DocumentManifest, dict[str, Path], dict[str, ImageAsset]]] = []
    gt: dict[tuple[str, str], str] = {}
    baseline_pairs: list[tuple[str, str]] = []
    baseline_by_file: dict[str, list[tuple[str, str]]] = {}

    ocr_by_file: dict[str, dict[str, str]] = {}
    ocr_meta: dict = {}
    if ocr_sidecar is not None:
        payload = json.loads(ocr_sidecar.read_text(encoding="utf-8"))
        ocr_by_file = payload.get("ocr", {})
        ocr_meta = {
            "engine": payload.get("engine"),
            "lang": payload.get("lang"),
            "lines": payload.get("lines"),
        }

    noisy_texts: set[str] = set()
    scale = dpi / _MM10_PER_INCH
    for xml in xmls:
        png = xml.with_suffix(".png")
        if not png.exists():
            continue
        clean = build_document_manifest([(xml, xml.name)])
        if ocr_sidecar is not None:
            degraded, gt_part = apply_ocr_manifest(clean, ocr_by_file.get(xml.name, {}))
        else:
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
                baseline_by_file.setdefault(xml.name, []).append((line.ocr_text, ref))
                baseline_pairs.append((line.ocr_text, ref))
                if line.ocr_text != ref:
                    noisy_texts.add(line.ocr_text)

    if not docs:
        raise SystemExit(f"no *.xml + *.png pairs found under {corpus_dir}")

    import asyncio

    # A real VLM reads the image, so a correct reading of a badly-garbled
    # line lands far from the OCR source and the text floor (0.35) would
    # reject it. The oracle path keeps the engine default so the existing
    # plumbing numbers stay comparable to their published selves.
    guard_config = None
    if provider is not None:
        from lidenbrock.core.schemas import GuardConfig

        guard_config = GuardConfig.vision()

    # Resolve the model id ONCE, here, so the report can name what actually
    # ran rather than what was typed: `--provider mistral` with no --model
    # would otherwise be recorded as `model: null`, and a run you cannot
    # attribute to a model is not a measurement.
    resolved_model = model
    if provider is not None:
        from scripts.run_vision import PROVIDERS

        resolved_model = model or PROVIDERS[provider][2]

    def _make_vision():
        """The VLM slot: an oracle, or an actual model over the network."""
        if provider is None:
            return OracleVisionProducer(gt)
        import os

        from lidenbrock.core.schemas import ModelCapabilities
        from lidenbrock.integrations.vision import VisionEditProducer

        from scripts.run_vision import PROVIDERS

        client_cls, key_env, _default, max_images = PROVIDERS[provider]
        api_key = os.environ.get(key_env, "")
        if not api_key:
            raise SystemExit(
                f"{key_env} is unset — export it in your shell (never pass a "
                "key as a flag: it lands in shell history and the process list)"
            )
        return VisionEditProducer(
            client_cls(),
            api_key,
            resolved_model,
            capabilities=ModelCapabilities(
                text=True,
                vision=True,
                structured_output=True,
                max_images=max_images,
            ),
        )

    text = RulesProducer(default_french_ocr_rules())
    hybrid_text = RulesProducer(default_french_ocr_rules())

    planned = [
        ("text", lambda: run_config("text", docs=docs, gt=gt, producer=text)),
        (
            "vision",
            lambda: run_config(
                "vision",
                docs=docs,
                gt=gt,
                producer=_make_vision(),
                guard_config=guard_config,
            ),
        ),
        (
            "hybrid",
            lambda: run_config(
                "hybrid",
                docs=docs,
                gt=gt,
                producer=hybrid_text,
                escalation_producer=_make_vision(),
                # Plumbing mode: an oracle QE escalates exactly the degraded
                # lines. A real benchmark swaps in HeuristicQEScorer or the
                # lidenbrock[qe] MaskedLMQEScorer and tunes the bound.
                qe_scorer=OracleQEScorer(noisy_texts),
                routing_policy=RoutingPolicy(escalate_at_or_above=0.5),
                guard_config=guard_config,
            ),
        ),
    ]
    configs = [build() for name, build in planned if name in only]
    results = asyncio.run(_gather(configs))

    if dump_lines is not None:
        dump_lines.write_text(
            json.dumps(
                {
                    r.name: [
                        {
                            "file": f,
                            "line_id": lid,
                            "ocr": ocr,
                            "out": out,
                            "ref": ref,
                        }
                        for f, lid, ocr, out, ref in r.triples
                    ]
                    for r in results
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    return {
        "corpus_dir": str(corpus_dir),
        "pages": len(docs),
        "lines": results[0].lines,
        "dpi": dpi,
        "mm10_to_px_scale": round(scale, 4),
        # What produced the INPUT text: a real OCR engine, or the scripted
        # degrader (then seed/rate apply). Stated so a report can never be
        # mistaken for the other kind of measurement.
        "input": (
            {"source": "real_ocr", **ocr_meta}
            if ocr_sidecar is not None
            else {"source": "scripted_degradation", "seed": seed, "rate": rate_percent}
        ),
        # What played the VLM. The `input` block above says where the text
        # came from; this one says who corrected it, and the two are
        # independent: real OCR corrected by an oracle is still an oracle
        # measurement. `kind: oracle` means the producer was handed the GT,
        # so its CER is the plumbing floor and NOT a model score. Any table
        # quoting a CER from this report must carry this field with it.
        "producer": (
            {"kind": "oracle", "implementation": "gt", "guard_profile": "default"}
            if provider is None
            else {
                "kind": "real_vlm",
                "provider": provider,
                "model": resolved_model,
                "guard_profile": "vision",
            }
        ),
        "baseline_cer": round(corpus_cer(baseline_pairs), 4),
        "configs": [
            {
                "name": r.name,
                "cer": round(r.cer, 4),
                "producer_calls": r.producer_calls,
                "escalated_lines": r.escalated_lines,
                "crops": r.crops,
                # A falling mean is not the same as "nothing got worse".
                # `scripts/benchmark.py` has reported these since Phase 2;
                # this harness did not, so a page that went from CER 0.0402
                # to 0.0513 hid inside a corpus average that improved.
                # `degraded` is the number that must be READ, not the mean.
                **_line_deltas(r.triples),
            }
            for r in results
        ],
        # Per-source-file scores. A corpus is rarely one population: the
        # BNL GT is 71% French and 29% German fraktur, and an aggregate CER
        # silently averages the two. Emitting the breakdown costs nothing
        # and lets a reader regroup by language, script or date — and see
        # a config that wins on average while losing on a subset.
        "per_file": {
            name: {
                "lines": len(pairs),
                "baseline_cer": round(corpus_cer(pairs), 4),
                **{
                    r.name: round(corpus_cer(r.by_file.get(name, [])), 4)
                    for r in results
                    if r.by_file.get(name)
                },
            }
            for name, pairs in sorted(baseline_by_file.items())
        },
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
    parser.add_argument(
        "--ocr",
        type=Path,
        default=None,
        help="sidecar from scripts/ocr_corpus.py — use REAL OCR as the input "
        "instead of scripted degradation",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--provider",
        choices=("mistral", "anthropic"),
        default=None,
        help="run a REAL VLM instead of the GT oracle — this is what turns "
        "the plumbing run into a model measurement (costs API calls)",
    )
    parser.add_argument("--model", default=None, help="model id (provider default)")
    parser.add_argument(
        "--limit", type=int, default=None, help="first N pages only (smoke test)"
    )
    parser.add_argument(
        "--only",
        default="text,vision,hybrid",
        help="comma-separated configs to run — with --provider, `vision` "
        "alone keeps the bill to one pass",
    )
    parser.add_argument(
        "--dump-lines",
        type=Path,
        default=None,
        help="write every (file, line_id, ocr, output, reference) tuple as "
        "JSON — a real run is expensive, so keep its per-line evidence for "
        "audits the aggregate cannot answer",
    )
    args = parser.parse_args(argv)

    report = benchmark(
        args.corpus,
        dpi=args.dpi,
        seed=args.seed,
        rate_percent=args.rate,
        ocr_sidecar=args.ocr,
        provider=args.provider,
        model=args.model,
        limit=args.limit,
        only=tuple(c.strip() for c in args.only.split(",") if c.strip()),
        dump_lines=args.dump_lines,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
