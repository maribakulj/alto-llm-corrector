"""`run()` returns its input exactly as it received it — all of it.

ADR-011 promises the engine works on its own deep copy and never writes to
the manifest it was handed. The promise is load-bearing: a caller reads its
outcomes off ``result.decisions``, and an instance is reentrant only if
running once leaves nothing behind.

**It was checked on a six-field slice.** The strongest existing test
compared coordinates, status and corrected text, line by line, under an
identity producer. That leaves out everything else a run touches, and one
omission was pointed at by name: the planner rewrites hyphen pointer fields
on its copy when a pair has to be severed, which is exactly the place a
leak would be both plausible and invisible — the fields are internal, no
consumer reads them, and nothing would look wrong until a second run on the
same manifest paired differently from the first.

So this compares the whole object, by value, and the source bytes with it.
Two dumps or none: a slice can only prove that the fields someone thought
of are safe.

Proven by mutation on 2026-08-16, since a guard that duplicates an existing
one is worth nothing. Dropping the deep copy, and weakening it to a shallow
one, are caught here *and* by ``test_reentrancy_guard.py`` — no gain. The
gain is the third mutation: a run that writes one hyphen pointer onto the
caller's manifest and touches nothing else leaves that test **green** and
fails this one. The fourth, a run that writes to a source file, is caught
only here.
"""

from __future__ import annotations

import hashlib

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.formats.loader import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import DictProvider, RecordingObserver

#: Both formats. PAGE could not be run through a harness at all until
#: 2026-08-16, and its rewriter has its own post-decision passes.
_CORPORA = [
    "X0000002.xml",
    "page/Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
]


def _corrections_that_do_real_work(manifest: object) -> dict[str, str]:
    """Corrections that change word counts, so the run takes its slow paths.

    An identity run is the easy case: nothing downstream has a reason to
    write anything. Changing the word count pulls in reconciliation, the
    loss counters and the slow rewriter path — more of the engine, more
    chances for one of them to write through to the input.
    """
    out: dict[str, str] = {}
    for page in manifest.pages:  # type: ignore[attr-defined]
        for line in page.lines:
            if len(line.ocr_text.split()) > 3 and len(out) < 6:
                out[line.line_id] = f"{line.ocr_text} ajoute"
    return out


def _run(corpus: str) -> tuple[dict, dict, str, str]:
    """Dump the manifest and hash the source, either side of a real run."""
    path = EXAMPLES / corpus
    manifest = build_document_manifest([(path, corpus)])
    before = manifest.model_dump()
    source_before = hashlib.sha256(path.read_bytes()).hexdigest()

    # Built here rather than through ``run_pipeline``: that helper ends by
    # projecting the decisions back onto its manifest, which would mutate
    # the very object under test and make the comparison vacuous-red.
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(_corrections_that_do_real_work(manifest)),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
    )
    pipeline.run_sync(document_manifest=manifest, source_files={corpus: path})

    return (
        before,
        manifest.model_dump(),
        source_before,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_the_run_really_exercises_the_engine() -> None:
    """Otherwise the comparisons below hold over a run that did nothing."""
    for corpus in _CORPORA:
        manifest = build_document_manifest([(EXAMPLES / corpus, corpus)])
        corrections = _corrections_that_do_real_work(manifest)
        assert len(corrections) >= 3, (
            f"{corpus}: only {len(corrections)} line(s) long enough to "
            "correct; the run would barely leave its fast path."
        )


def test_the_input_manifest_is_byte_for_byte_what_it_was() -> None:
    for corpus in _CORPORA:
        before, after, _, _ = _run(corpus)
        assert after == before, (
            f"{corpus}: the run wrote through to its input. ADR-011 says it "
            "works on its own deep copy; a caller reads outcomes off "
            "result.decisions, and an instance is reentrant only if running "
            "once leaves nothing behind. Comparing whole dumps rather than "
            "a chosen slice is the point — the hyphen pointer fields the "
            "planner rewrites are internal, unread by any consumer, and "
            "would go unnoticed until a second run paired differently."
        )


def test_the_source_file_on_disk_is_untouched() -> None:
    """The other half nobody was checking: the engine writes no file.

    The engine has no writer (ADR-011) — persistence is the caller's move,
    through ``result.write()``. Nothing asserted that a run leaves the
    documents it was pointed at alone.
    """
    for corpus in _CORPORA:
        _, _, source_before, source_after = _run(corpus)
        assert source_after == source_before, (
            f"{corpus}: the source file changed on disk during a run. The "
            "engine has no writer; the rewrite happens in memory and the "
            "caller decides what to persist."
        )
