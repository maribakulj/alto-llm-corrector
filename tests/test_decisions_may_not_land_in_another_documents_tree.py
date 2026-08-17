"""A run may not write one file's decisions into another file's markup.

This is the most serious thing the 2026-08-17 audit found, and the reason
is not the mistake itself but that **nothing could see it**.

`ADR-007` states that ``line_id`` is unique only WITHIN a source file, so
two files of one document normally both carry ``TL1…TLn``. The rewriter
indexes by bare ``line_id``. Give a run a ``source_files`` mapping whose
name→path bindings are swapped, keep the ``page_id``\\ s distinct so the
cross-file uniqueness guard is satisfied, and every lookup matches — the
wrong line, in the wrong tree.

Measured before the fix:

    run SUCCEEDED with swapped name->path bindings
      artefact 'vol_a.xml' says HISTOIRE (text of A)?   True
      artefact 'vol_a.xml' says GEOGRAPHIE (text of B)? False
      page ids in artefact 'vol_a.xml': [b'PB1']

The file delivered under the first name carried **the second file's tree,
geometry and page ids** with the first file's decided text. The second
file's own text was destroyed. No exception, no counter, no reason.

**And the projection invariant cannot catch this, structurally.** It
compares the delivered artefact to the decisions — and the artefact was
*made* by writing those decisions into a tree. Whatever tree that was, the
comparison succeeds. Any defence of the form "the projection check covers
it" is refuted by this file.

What closes it is the parse-time digest: the parser records the bytes each
page came from, and the run refuses at preflight if a path no longer holds
them. That also closes a file replaced between parse and write, which is
the same mistake with the clock instead of a caller.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.errors import ConfigurationError
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer

from tests._pipeline_harness import RecordingObserver

_A_TEXT = "HISTOIRE"
_B_TEXT = "GEOGRAPHIE"


def _alto(page_id: str, text: str) -> str:
    """One page, one line, and the line id is ``TL1`` in both files.

    Sharing the line id is the point rather than a shortcut: it is what
    `ADR-007` says a real two-file document looks like, and it is what
    makes every lookup match under a swapped binding.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>'
        f'<Page ID="{page_id}" WIDTH="1000" HEIGHT="200"><PrintSpace>'
        f'<TextBlock ID="B_{page_id}" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="100">'
        '<TextLine ID="TL1" HPOS="0" VPOS="10" WIDTH="900" HEIGHT="40">'
        f'<String ID="S_{page_id}" CONTENT="{text}" HPOS="0" VPOS="10" '
        'WIDTH="900" HEIGHT="40"/>'
        "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
    )


def _two_file_document() -> tuple[Path, Path, object]:
    directory = Path(tempfile.mkdtemp())
    first = directory / "vol_a.xml"
    first.write_text(_alto("PA1", _A_TEXT), encoding="utf-8")
    second = directory / "vol_b.xml"
    second.write_text(_alto("PB1", _B_TEXT), encoding="utf-8")
    manifest = build_document_manifest([(first, "vol_a.xml"), (second, "vol_b.xml")])
    return first, second, manifest


def _run(manifest: object, source_files: dict[str, Path]) -> object:
    return CorrectionPipeline(
        producer=RulesProducer([]), observer=RecordingObserver()
    ).run_sync(document_manifest=manifest, source_files=source_files)  # type: ignore[arg-type]


def test_the_two_files_really_share_a_line_id() -> None:
    """Otherwise the swap below would be caught by identity, not by bytes.

    If the line ids differed, the rewriter would find no line to write and
    fail for an unrelated reason — and this file would be testing that
    instead of what it claims.
    """
    _, _, manifest = _two_file_document()
    ids = [line.line_id for page in manifest.pages for line in page.lines]  # type: ignore[attr-defined]
    assert ids == ["TL1", "TL1"], f"expected a shared line id, got {ids}"
    pages = [page.page_id for page in manifest.pages]  # type: ignore[attr-defined]
    assert len(set(pages)) == 2, (
        f"page ids {pages} collide, so the cross-file uniqueness guard would "
        "refuse this document for a different reason than the one under test."
    )


def test_a_swapped_name_to_path_binding_is_refused() -> None:
    first, second, manifest = _two_file_document()
    with pytest.raises(ConfigurationError, match="vol_a.xml"):
        _run(manifest, {"vol_a.xml": second, "vol_b.xml": first})


def test_the_honest_binding_still_runs() -> None:
    """The control: the refusal must be about the swap, not about two files.

    And it checks the outcome rather than the absence of an exception —
    each artefact must carry its own text, which is the property the swap
    destroyed.
    """
    first, second, manifest = _two_file_document()
    result = _run(manifest, {"vol_a.xml": first, "vol_b.xml": second})
    delivered = {
        name: xml.decode("utf-8")
        for name, xml in result.corrected_files.items()  # type: ignore[attr-defined]
    }
    assert _A_TEXT in delivered["vol_a.xml"] and _B_TEXT not in delivered["vol_a.xml"]
    assert _B_TEXT in delivered["vol_b.xml"] and _A_TEXT not in delivered["vol_b.xml"]
