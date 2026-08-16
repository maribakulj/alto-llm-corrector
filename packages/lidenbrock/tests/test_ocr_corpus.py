"""Real-OCR sidecar generator (scripts/ocr_corpus.py).

Self-skips when Tesseract is absent (it is not a project dependency — the
sidecar is generated once, offline, by whoever builds the corpus). The
Tesseract-gated test renders text with Pillow and checks the engine reads
it back, which is what the tool relies on: crop → single-line OCR.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from tests._paths import REPO

_REPO_ROOT = REPO
_SCRIPT = _REPO_ROOT / "scripts" / "ocr_corpus.py"

_spec = importlib.util.spec_from_file_location("ocr_corpus", _SCRIPT)
assert _spec and _spec.loader
oc = importlib.util.module_from_spec(_spec)
sys.modules["ocr_corpus"] = oc
_spec.loader.exec_module(oc)

_HAS_TESSERACT = shutil.which("tesseract") is not None


def test_module_exposes_the_two_seams():
    assert callable(oc.ocr_image)
    assert callable(oc.ocr_corpus)


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract not installed")
def test_ocr_image_reads_a_rendered_line(tmp_path: Path):
    """The single-line contract (--psm 7): given one line of text as an
    image, the engine returns that line."""
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 90), (255, 255, 255))
    ImageDraw.Draw(img).text((10, 25), "le cabinet de Vienne", fill=(0, 0, 0))
    png = tmp_path / "line.png"
    img.save(png)

    reading = oc.ocr_image(png, lang="fra")
    # Default PIL font is tiny/bitmap: assert the engine found the words,
    # not a byte-exact match (that is what a real scan is for).
    assert "cabinet" in reading or "Vienne" in reading


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract not installed")
def test_ocr_image_raises_on_missing_file(tmp_path: Path):
    with pytest.raises(RuntimeError):
        oc.ocr_image(tmp_path / "nope.png", lang="fra")
