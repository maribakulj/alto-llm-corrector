"""Generate REAL raw OCR beside a ground-truth corpus, line by line.

Both the vision benchmark and the QE calibration were left with one
synthetic ingredient: their "OCR" was a scripted substitution table
(``m→rn``, ``l→1``…). Real OCR fails differently — it merges words
(``On me`` → ``Oume``), drops and invents characters (``aujourd'hui`` →
``aujourd'hut``), normalises apostrophes, hallucinates leading glyphs.
No substitution table reproduces that distribution.

This runs a REAL OCR engine (Tesseract) over the ground truth's own line
images and pairs each reading with its GT line. The trick that makes the
pairing exact: rather than OCR-ing the page and aligning two different
segmentations, it OCRs **one crop per GT line**, cut with the library's
own :func:`~corrigenda.integrations.vision.crop_region` from the GT
geometry (``--psm 7``, single-line mode). Every reading therefore belongs
to a known ``(file, line_id)`` — no alignment, no drift.

Quality tiers, so a benchmark can span the range real material shows:

* ``--lang fra`` — a correct engine on French: good OCR, the errors a
  modern pipeline actually leaves behind;
* ``--lang spa`` / ``deu`` / ``eng`` — a DELIBERATELY WRONG language
  model on French text. Still a real engine making real decisions, just
  with the wrong lexicon and character priors, so it degrades the way bad
  OCR degrades (``l'entente`` → ``Ventente``, ``qu'il`` → ``Qw'il``)
  rather than the way a substitution table does.

Output is a sidecar JSON — ``{source_file: {line_id: raw_ocr_text}}`` plus
a metadata block — consumed by ``vision_benchmark.py --ocr``. The GT ALTO
stays untouched and remains the reference: this only adds the missing
INPUT side.

Usage::

    python scripts/ocr_corpus.py --corpus /path/to/"37 GT BNL" \\
        --lang fra --out ocr_fra.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "packages" / "corrigenda" / "src"))

from corrigenda.core.schemas import ImageAsset, ImageTransform  # noqa: E402
from corrigenda.formats.alto.parser import build_document_manifest  # noqa: E402

#: ALTO ``mm10`` → pixels (see vision_benchmark): ``px = mm10 * dpi / 254``.
_MM10_PER_INCH = 254.0


def ocr_image(png_path: Path, *, lang: str, psm: int = 7) -> str:
    """Return Tesseract's reading of a single-line image (whitespace
    collapsed). ``psm 7`` tells it the image IS one text line, which is
    exactly what a GT line crop is."""
    proc = subprocess.run(
        ["tesseract", str(png_path), "stdout", "-l", lang, "--psm", str(psm)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed on {png_path}: {proc.stderr[:200]}")
    return " ".join(proc.stdout.split())


def ocr_corpus(
    corpus_dir: Path,
    *,
    lang: str,
    dpi: float = 300.0,
    margin_ratio: float = 0.08,
    limit: int | None = None,
) -> dict:
    """OCR every GT line crop and return the paired sidecar payload."""
    scale = dpi / _MM10_PER_INCH
    by_file: dict[str, dict[str, str]] = {}
    gt_by_file: dict[str, dict[str, str]] = {}
    lines_done = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        crop_path = Path(tmpdir) / "line.png"
        for xml in sorted(corpus_dir.glob("*.xml")):
            png = xml.with_suffix(".png")
            if not png.exists():
                continue
            doc = build_document_manifest([(xml, xml.name)])
            readings: dict[str, str] = {}
            truths: dict[str, str] = {}
            for page in doc.pages:
                asset = ImageAsset(
                    page_id=page.page_id,
                    uri=str(png),
                    transform=ImageTransform(scale_x=scale, scale_y=scale),
                )
                for line in page.lines:
                    if limit is not None and lines_done >= limit:
                        break
                    from corrigenda.integrations.vision import crop_region

                    crop = crop_region(asset, line.coords, margin_ratio=margin_ratio)
                    crop_path.write_bytes(crop.data)
                    readings[line.line_id] = ocr_image(crop_path, lang=lang)
                    truths[line.line_id] = line.ocr_text
                    lines_done += 1
            if readings:
                by_file[xml.name] = readings
                gt_by_file[xml.name] = truths
            if limit is not None and lines_done >= limit:
                break

    return {
        "engine": "tesseract",
        "lang": lang,
        "dpi": dpi,
        "margin_ratio": margin_ratio,
        "lines": lines_done,
        "ocr": by_file,
        "gt": gt_by_file,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--lang",
        default="fra",
        help="tesseract language; a WRONG one (spa/deu/eng on French) "
        "yields realistically bad OCR",
    )
    parser.add_argument("--dpi", type=float, default=300.0)
    parser.add_argument("--margin-ratio", type=float, default=0.08)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = ocr_corpus(
        args.corpus,
        lang=args.lang,
        dpi=args.dpi,
        margin_ratio=args.margin_ratio,
        limit=args.limit,
    )
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    print(f"{payload['lines']} lines OCR'd with tesseract/{args.lang} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
