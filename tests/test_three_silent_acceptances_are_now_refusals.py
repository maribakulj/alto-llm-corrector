"""Three places that accepted something impossible and said nothing.

They have nothing in common mechanically — one is an input mapping, one is
a second read of a file, one is an output filename. They have the same
shape: **the library could not do what it was asked, and reported success
anyway.** Measured 2026-08-17, all three:

1. A manifest parsed from ``a.xml`` + ``b.xml``, run with only ``a.xml``
   supplied. The run **succeeded**: ``report.total_lines`` counted both
   files' lines, ``projection_fidelity`` counted one file's. Half the
   decided lines existed in no artefact, and the only trace was that
   arithmetic — which nothing says should agree.
2. A source file removed between parse and render. ``FileNotFoundError``
   travelled out of ``run()`` unclassified, through ``asyncio.to_thread``,
   past the single-error-root contract of §8.4 / ADR-008. Truncation gave
   ``XMLSyntaxError``, a permission change gave ``PermissionError``. The
   *same* perturbations at parse time gave a proper ``ParseError``: the two
   rewriter reads were the only ``read_source_tree`` callers not wrapped.
3. ``result.write()`` on ``volume1/page.xml`` and ``volume2/page.xml``.
   It **returned three paths and left two files**, reporting that it wrote
   ``page.xml`` twice while the second silently overwrote the first.

None of the three is a missing feature. Each is a refusal that was
missing, and each failure mode is one a host discovers months later on
someone else's corpus.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.errors import ConfigurationError, ParseError, SaknussemmError
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer

from tests._pipeline_harness import RecordingObserver


def _alto(page_id: str, line_id: str, text: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>'
        f'<Page ID="{page_id}" WIDTH="1000" HEIGHT="200"><PrintSpace>'
        f'<TextBlock ID="B_{page_id}" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="100">'
        f'<TextLine ID="{line_id}" HPOS="0" VPOS="10" WIDTH="900" HEIGHT="40">'
        f'<String ID="S_{line_id}" CONTENT="{text}" HPOS="0" VPOS="10" '
        'WIDTH="900" HEIGHT="40"/>'
        "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
    )


def _write(directory: Path, name: str, page_id: str, line_id: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_alto(page_id, line_id, text), encoding="utf-8")
    return path


def _pipeline() -> CorrectionPipeline:
    return CorrectionPipeline(producer=RulesProducer([]), observer=RecordingObserver())


# ---------------------------------------------------------------------------
# 1. `source_files` must describe the same document as the manifest
# ---------------------------------------------------------------------------


def test_a_source_the_manifest_needs_may_not_be_missing() -> None:
    directory = Path(tempfile.mkdtemp())
    first = _write(directory, "a.xml", "P1", "TL1", "PREMIER")
    _write(directory, "b.xml", "P2", "TL2", "SECOND")
    manifest = build_document_manifest(
        [(directory / "a.xml", "a.xml"), (directory / "b.xml", "b.xml")]
    )
    with pytest.raises(ConfigurationError, match="b.xml"):
        _pipeline().run_sync(document_manifest=manifest, source_files={"a.xml": first})


def test_a_source_the_manifest_does_not_know_may_not_be_supplied() -> None:
    """The mirror case, and it is not symmetrical in consequence.

    An unknown key renders nothing, but it *is* read and hashed into
    ``RunProvenance.source_digests`` — so the provenance would declare an
    input file that contributed to no decision.
    """
    directory = Path(tempfile.mkdtemp())
    first = _write(directory, "a.xml", "P1", "TL1", "PREMIER")
    ghost = _write(directory, "ghost.xml", "P9", "TL9", "FANTOME")
    manifest = build_document_manifest([(directory / "a.xml", "a.xml")])
    with pytest.raises(ConfigurationError, match="ghost.xml"):
        _pipeline().run_sync(
            document_manifest=manifest,
            source_files={"a.xml": first, "ghost.xml": ghost},
        )


def test_the_decide_only_run_stays_legal() -> None:
    """An empty mapping means "decide, render nothing" and must keep working.

    This is the reason the check is conditional rather than an equality:
    the dry run is a documented mode and several test files depend on it.
    Without this test the refusal above could be tightened into breaking
    it, and the breakage would look like a stricter guard.
    """
    directory = Path(tempfile.mkdtemp())
    _write(directory, "a.xml", "P1", "TL1", "PREMIER")
    manifest = build_document_manifest([(directory / "a.xml", "a.xml")])
    result = _pipeline().run_sync(document_manifest=manifest, source_files={})
    assert result.corrected_files == {}
    assert result.report.total_lines == 1


# ---------------------------------------------------------------------------
# 2. The render-time read is classified like every other read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "perturbation",
    ["removed", "truncated"],
    ids=["source removed after parse", "source truncated after parse"],
)
def test_a_source_that_changes_under_the_run_fails_classified(
    perturbation: str,
) -> None:
    directory = Path(tempfile.mkdtemp())
    path = _write(directory, "x.xml", "P1", "TL1", "TEXTE")
    manifest = build_document_manifest([(path, "x.xml")])

    if perturbation == "removed":
        path.unlink()
    else:
        path.write_text("<?xml version=", encoding="utf-8")

    with pytest.raises(SaknussemmError) as caught:
        _pipeline().run_sync(document_manifest=manifest, source_files={"x.xml": path})
    assert isinstance(caught.value, ParseError), (
        f"the render path raised {type(caught.value).__name__}. §8.4 asks "
        "that a source read fail as a classified error; the two rewriter "
        "reads were the only ones outside that contract, so a file "
        "perturbed between parse and render escaped raw to the host."
    )


# ---------------------------------------------------------------------------
# 3. `write()` defends its own contract
# ---------------------------------------------------------------------------


def test_two_sources_that_flatten_to_one_filename_are_refused() -> None:
    directory = Path(tempfile.mkdtemp())
    first = _write(directory, "volume1/page.xml", "PA", "TLA", "HISTOIRE")
    second = _write(directory, "volume2/page.xml", "PB", "TLB", "GEOGRAPHIE")
    manifest = build_document_manifest(
        [(first, "volume1/page.xml"), (second, "volume2/page.xml")]
    )
    result = _pipeline().run_sync(
        document_manifest=manifest,
        source_files={"volume1/page.xml": first, "volume2/page.xml": second},
    )
    assert set(result.corrected_files) == {"volume1/page.xml", "volume2/page.xml"}

    target = directory / "out"
    with pytest.raises(ConfigurationError, match="page.xml"):
        result.write(target)
    assert not target.exists() or not list(target.iterdir()), (
        "the refusal left files behind. Checking before writing anything is "
        "the point: a half-populated directory is worse than a clean failure."
    )


def test_flattening_a_single_directory_part_still_works() -> None:
    """The scope: the path-traversal guard is not what changed.

    ``Path(name).name`` remains deliberate — a source name must never
    steer the write outside the target. One key with a directory part is
    still written, flattened, exactly as before.
    """
    directory = Path(tempfile.mkdtemp())
    path = _write(directory, "volume1/page.xml", "PA", "TLA", "HISTOIRE")
    manifest = build_document_manifest([(path, "volume1/page.xml")])
    result = _pipeline().run_sync(
        document_manifest=manifest, source_files={"volume1/page.xml": path}
    )
    target = directory / "out"
    written = result.write(target)
    assert [p.name for p in written if p.suffix == ".xml"] == ["page.xml"]
