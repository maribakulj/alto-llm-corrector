"""The base install must not reach the research extras (`RM-04`).

Two modules are gated behind optional dependencies — ``integrations/qe.py``
(``saknussemm[qe]``: onnxruntime, tokenizers, a 545 MB model) and
``integrations/vision.py`` (``saknussemm[vision]``: Pillow). Both predate
this wave and both are already omitted from the coverage gate.

What did NOT exist is anything holding the boundary. The gate is a
``pyproject.toml`` entry and a coverage ``omit``; nothing stopped a module
on the base install path from importing one, and an import is all it takes
to turn an optional dependency into a required one at runtime — with the
failure landing on a user who installed exactly what the metadata told
them to.

Three rules, and the first is the one with teeth:

  1. no module reachable from ``import saknussemm`` imports a gated
     module, statically or at import time (subprocess-verified, same
     technique as ``test_import_contract.py``);
  2. a default correction run never loads one either — the check that
     catches a lazy import inside a function on the hot path;
  3. the paths the calibration scripts import from still resolve, so
     "gated" never quietly becomes "moved".

Rule 3 is the counterweight. ``integrations/`` is not dead code: it is the
measurement programme `M*` depends on, driven by ``scripts/qe_benchmark.py``,
``scripts/fit_qe_calibration.py``, ``scripts/vision_benchmark.py`` and
``scripts/ocr_corpus.py``. `RM-04`'s job is to keep it out of the published
surface, not to make it unusable.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests._paths import SRC

SRC = SRC
from tests._paths import EXAMPLES  # noqa: E402  (the arithmetic lives there)

#: Modules gated behind an optional dependency. Nothing on the base install
#: path may import these.
_GATED = ("saknussemm.integrations.qe", "saknussemm.integrations.vision")


def _import_probe(body: str) -> set[str]:
    """Run ``body`` in a fresh interpreter; return the gated modules loaded."""
    script = (
        "import sys\n"
        f"{body}\n"
        "print(','.join(m for m in sys.modules if m in "
        f"{_GATED!r}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, f"probe failed:\n{proc.stderr}"
    return {name for name in proc.stdout.strip().split(",") if name}


def test_importing_the_package_loads_no_gated_module() -> None:
    """``import saknussemm`` is the base install path."""
    loaded = _import_probe("import saknussemm")
    assert not loaded, (
        f"importing saknussemm pulled in {sorted(loaded)} — those are behind "
        "optional extras, so a base install would fail at import with a "
        "missing dependency the metadata never asked for."
    )


def test_a_default_run_loads_no_gated_module() -> None:
    """A static scan cannot see a lazy import inside a hot-path function.

    Runs a real correction over a real file with a stub producer and asks
    ``sys.modules`` afterwards.
    """
    sample = EXAMPLES / "sample.xml"
    loaded = _import_probe(
        "from pathlib import Path\n"
        "from saknussemm.core.pipeline import CorrectionPipeline\n"
        "from saknussemm.formats.loader import build_document_manifest\n"
        "class _P:\n"
        "    async def complete_structured(self, **kw):\n"
        "        return {'lines': [{'line_id': l['line_id'],"
        " 'corrected_text': l.get('ocr_text', '')}\n"
        "                          for l in kw['user_payload'].get('lines', [])]}, None\n"
        "class _O:\n"
        "    def on_event(self, t, p): pass\n"
        f"p = Path({str(sample)!r})\n"
        "doc = build_document_manifest([(p, p.name)])\n"
        "CorrectionPipeline.for_provider(_P(), api_key='k', model='m',"
        " observer=_O()).run_sync(document_manifest=doc,"
        " source_files={p.name: p})\n"
    )
    assert not loaded, (
        f"a default run loaded {sorted(loaded)} — a lazy import on the hot "
        "path makes an optional dependency mandatory in practice."
    )


@pytest.mark.parametrize(
    ("module", "symbol"),
    [
        # scripts/qe_benchmark.py, scripts/fit_qe_calibration.py
        ("saknussemm.core.quality", "HeuristicQEScorer"),
        ("saknussemm.core.quality", "RoutingPolicy"),
        ("saknussemm.core.schemas", "ConfidencePolicy"),
        # scripts/vision_benchmark.py, scripts/ocr_corpus.py
        ("saknussemm.core.schemas", "ImageAsset"),
        ("saknussemm.core.schemas", "ImageTransform"),
        ("saknussemm.core.schemas", "ModelCapabilities"),
    ],
)
def test_the_calibration_scripts_keep_their_import_paths(
    module: str, symbol: str
) -> None:
    """Gated is not moved.

    `RM-04` takes ``RoutingPolicy`` and ``ConfidencePolicy`` off the
    top-level surface; both stay importable from their own module, which is
    the demotion pattern ``docs/versioning.md`` documents. These are the
    exact paths the four calibration scripts use — if one of them breaks,
    the measurement programme `M*` breaks with it.
    """
    import importlib

    assert hasattr(importlib.import_module(module), symbol), (
        f"{module}.{symbol} no longer resolves — a calibration script "
        "imports it, and gating a module must never mean relocating it."
    )
