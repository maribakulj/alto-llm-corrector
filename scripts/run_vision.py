"""Correct an ALTO/PAGE document with a REAL vision model, from the terminal.

The end-to-end vision path with an actual VLM — no demo web app, no
server. It wires the pieces Phase 4 built:

    ALTO/PAGE + scan
        → build_image_asset()          (decode, hash, dimensions)
        → VisionEditProducer           (crop each line, call the VLM)
        → AnthropicMultimodalClient    (the real model)
        → CorrectionPipeline           (guards, hyphen reconciler, rewriter)
        → corrected XML + report.json

Two modes:

* **vision** (default) — every line goes to the VLM.
* **hybrid** (``--hybrid``) — a QE scorer routes lines: clean ones are
  SKIPped, risky ones ESCALATE to the VLM, the rest go to the text
  producer. This is the configuration whose cost claim Phase 3/4 exists
  to test, so it reports ``producer_calls`` and ``escalated_lines``.

Pair the run with ``GuardConfig.vision()``: a VLM reads the image, so a
correct reading of a badly-garbled line diverges further from the OCR text
than the text-tuned guard tolerates.

The API key is read from the environment (``ANTHROPIC_API_KEY`` /
``MISTRAL_API_KEY``) and is **never** a command-line flag — a flag would
land in shell history and in the process list, readable by any other
process on the machine.

Usage::

    export MISTRAL_API_KEY=...            # or ANTHROPIC_API_KEY
    python scripts/run_vision.py --provider mistral --list-models
    python scripts/run_vision.py --provider mistral --model pixtral-12b-2409 \\
        --xml page.xml --image page.png --dpi 300 --out ./corrected

The XML→pixel scale defaults to 1.0 (OCR ran at the scan's resolution).
For ALTO in ``mm10`` units, pass the scan's DPI with ``--dpi`` — the
transform is ``dpi/254`` (300 DPI ≈ 1.1811).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "packages" / "lidenbrock" / "src"))
sys.path.insert(0, str(_REPO))

from scripts.providers_multimodal import (  # noqa: E402
    AnthropicMultimodalClient,
    MistralMultimodalClient,
    supports_temperature,
)

import lidenbrock  # noqa: E402
from lidenbrock.core.quality import HeuristicQEScorer, RoutingPolicy  # noqa: E402
from lidenbrock.core.schemas import GuardConfig, ModelCapabilities  # noqa: E402
from lidenbrock.integrations.vision import (  # noqa: E402
    VisionEditProducer,
    build_image_asset,
)
from lidenbrock.producers.rules import (  # noqa: E402
    RulesProducer,
    default_french_ocr_rules,
)

_MM10_PER_INCH = 254.0

#: provider → (client class, env var holding the key, default model,
#: images accepted per call).
#: The key ALWAYS comes from the environment: passing it as a CLI flag
#: would put it in shell history and in the process list.
#:
#: The image cap is the host's job to declare: the library ships the
#: ``max_images`` descriptor and the chunk split, but only the caller knows
#: which vendor is on the wire. ``None`` means "not measured here, assume
#: unbounded" — Mistral's 8 was measured against the live API (a 9th image
#: is a hard 400), Anthropic's has not been, so it stays undeclared rather
#: than guessed.
PROVIDERS: dict[str, tuple[type, str, str, int | None]] = {
    "anthropic": (
        AnthropicMultimodalClient,
        "ANTHROPIC_API_KEY",
        "claude-opus-5",
        None,
    ),
    "mistral": (
        MistralMultimodalClient,
        "MISTRAL_API_KEY",
        MistralMultimodalClient.DEFAULT_MODEL,
        MistralMultimodalClient.MAX_IMAGES_PER_CALL,
    ),
}


class _Progress:
    """Minimal observer so a terminal run shows something while it works."""

    def on_event(self, event_type: str, payload: dict) -> None:
        if event_type in {"chunk_completed", "chunk_error", "page_completed"}:
            print(
                f"  [{event_type}] {payload.get('chunk_id') or payload.get('page_id')}"
            )


async def main_async(args: argparse.Namespace) -> int:
    xml = Path(args.xml)
    image = Path(args.image)
    doc = lidenbrock.load(xml)

    scale = (args.dpi / _MM10_PER_INCH) if args.dpi else 1.0
    transform = None
    if scale != 1.0:
        from lidenbrock.core.schemas import ImageTransform

        transform = ImageTransform(scale_x=scale, scale_y=scale)

    # One ImageAsset per page — this run assumes a single-page scan; a
    # multipage document needs one image per page_id (the library refuses
    # a partial mapping rather than sending the wrong scan).
    assets = {
        page.page_id: build_image_asset(page.page_id, image, transform=transform)
        for page in doc.manifest.pages
    }
    if len(assets) > 1:
        print(
            f"warning: {len(assets)} pages share one scan — pass one image per "
            "page for a multipage document",
            file=sys.stderr,
        )

    client_cls, key_env, _default, max_images = PROVIDERS[args.provider]
    client = client_cls()
    api_key = os.environ.get(key_env, "")
    vision = VisionEditProducer(
        client,
        api_key,
        args.model,
        margin_ratio=args.margin,
        mask_polygon=args.mask_polygon,
        # The engine keeps each call within this many crops; without it a
        # dense page (566 lines is a real BnF page) is one impossible
        # request the provider refuses outright.
        capabilities=ModelCapabilities(
            text=True,
            vision=True,
            structured_output=True,
            max_images=max_images,
        ),
    )

    kwargs: dict = {}
    if args.hybrid:
        kwargs.update(
            producer=RulesProducer(default_french_ocr_rules()),
            escalation_producer=vision,
            qe_scorer=HeuristicQEScorer(),
            routing_policy=RoutingPolicy(
                skip_at_or_below=args.skip_below,
                escalate_at_or_above=args.escalate_above,
            ),
        )
    else:
        kwargs.update(producer=vision)

    pipeline = lidenbrock.CorrectionPipeline(
        observer=_Progress(),
        # A VLM reads the image, not the OCR — the text guard's
        # source-similarity floor would reject correct heavy corrections.
        guard_config=GuardConfig.vision(),
        **kwargs,
    )

    print(
        f"provider={args.provider}  model={args.model}  "
        f"mode={'hybrid' if args.hybrid else 'vision'}"
    )
    result = await pipeline.run(
        document_manifest=doc.manifest,
        source_files=doc.source_paths,
        page_images=assets,
    )

    written = result.write(args.out)
    print(
        f"\nlines={result.report.total_lines} "
        f"fallbacks={result.fallback_lines} "
        f"producer_calls={result.producer_calls} "
        f"skipped={result.lines_skipped} escalated={result.escalated_lines}"
    )
    if result.usage.total_tokens:
        print(f"tokens in/out={result.usage.input_tokens}/{result.usage.output_tokens}")
    if client.dropped_temperature:
        print(
            f"note: {args.model} rejects `temperature`, so the engine's retry "
            "ramp was dropped — retries are byte-identical on this model."
        )
    for path in written:
        print("  écrit:", path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", help="ALTO or PAGE XML file")
    parser.add_argument("--image", help="the page scan")
    parser.add_argument("--out", default="./vision_out", help="output directory")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="anthropic")
    parser.add_argument(
        "--model", default=None, help="defaults to the provider's vision model"
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="list the models this key can reach, then exit (Mistral only)",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=None,
        help="scan DPI, for ALTO in mm10 units (transform = dpi/254)",
    )
    parser.add_argument("--margin", type=float, default=0.05, help="crop margin ratio")
    parser.add_argument(
        "--mask-polygon", action="store_true", help="mask PAGE polygons"
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="route lines by QE: skip clean ones, escalate risky ones to the VLM",
    )
    parser.add_argument("--skip-below", type=float, default=0.1)
    parser.add_argument("--escalate-above", type=float, default=0.3)
    args = parser.parse_args(argv)

    client_cls, key_env, default_model, _max_images = PROVIDERS[args.provider]
    if args.model is None:
        args.model = default_model
    key = os.environ.get(key_env, "")

    if args.list_models:
        lister = getattr(client_cls(), "list_models", None)
        if lister is None:
            parser.error(f"--list-models is not supported for {args.provider}")
        if not key:
            parser.error(f"--list-models needs {key_env} in the environment")
        for model_id in asyncio.run(lister(key)):
            print(model_id)
        return 0

    if not args.xml or not args.image:
        parser.error("--xml and --image are required (unless --list-models)")

    if not key:
        print(
            f"note: {key_env} is unset. Export it in your shell — do NOT pass a "
            "key as a command-line flag (it would land in shell history and in "
            "the process list).",
            file=sys.stderr,
        )
    if not supports_temperature(args.model):
        print(
            f"note: {args.model} rejects `temperature`; the retry ramp will be "
            "dropped (retries are byte-identical).",
            file=sys.stderr,
        )
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
