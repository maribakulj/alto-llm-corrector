"""The bytes a file gets back do not depend on where it sat in the list.

A metamorphic property (`T1`), and the transformation is the cheapest one a
caller can apply by accident: hand the same documents in a different order.
Nothing in the contract makes position meaningful, so every file must come
back byte-identical either way.

It is worth a test because the repository has already been bitten by this
exact family once. `F4`: ``_producer_ops`` was keyed by bare ``line_id``,
so two files legitimately reusing ``L1`` overwrote each other and the second
file's edit span leaked into the first — the defect only appears when more
than one document is in flight, and it is invisible to any single-file test.
`ADR-009` answers it with ``LineRef``; this asserts the answer holds from
the outside, on delivered bytes rather than on an internal key.

The fixture is deliberately hostile in the way real exports are: both files
declare page ``P1`` and line ``L1``. That is legitimate — ids are unique
within a file, never across one — and it is precisely the shape that makes
a bare-id key look correct in testing.
"""

from __future__ import annotations

from pathlib import Path

from lidenbrock import CorrectionPipeline
from lidenbrock.core.protocols import ProducerMetadata
from lidenbrock.formats.alto.parser import build_document_manifest
from lidenbrock.producers.rules import RulesProducer, SubstitutionRule

from tests._docs import _ALTO_ONE_LINE
from tests._pipeline_harness import RecordingObserver


def _write_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two documents sharing every id, differing only in their text.

    The rule below matches at a DIFFERENT offset in each, so a key that
    collapses the two produces visibly wrong bytes rather than a subtle
    tie.
    """
    first = tmp_path / "a.xml"
    second = tmp_path / "b.xml"
    first.write_text(_ALTO_ONE_LINE.format(text="la frauce entiere"), "utf-8")
    second.write_text(_ALTO_ONE_LINE.format(text="grande frauce unie"), "utf-8")
    return first, second


def _run(order: list[tuple[Path, str]]) -> tuple[dict[str, bytes], list[tuple]]:
    doc = build_document_manifest(order)
    pipeline = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("frauce", "france")]),
        observer=RecordingObserver(),
        producer_metadata=ProducerMetadata(name="rules", implementation="fr-ocr-v1"),
    )
    result = pipeline.run_sync(
        document_manifest=doc,
        source_files={name: path for path, name in order},
    )
    # Everything the run HANDS BACK, not just the rewritten bytes — `F4`
    # corrupted the edit_script deliverable while leaving the XML correct.
    #
    # Which assertion catches what, checked by reintroducing the bare-id key:
    # the ORDER comparison does not fire (both orders lose the same op, so
    # they still agree), and the op COUNT in the vacuity test does. That is
    # why the count is an assertion and not a comment.
    ops = sorted(
        (op.line_id, type(op).__name__, getattr(op.anchor, "start", None), op.text)
        for op in result.edit_script.ops
    )
    return dict(result.corrected_files), ops


def test_the_delivered_bytes_do_not_depend_on_input_order(tmp_path: Path) -> None:
    first, second = _write_pair(tmp_path)

    forward, forward_ops = _run([(first, "a.xml"), (second, "b.xml")])
    backward, backward_ops = _run([(second, "b.xml"), (first, "a.xml")])

    assert forward_ops == backward_ops, (
        "the edit script depends on input order. Each file's op must carry "
        "ITS OWN span; a key that is only unique within one file lets the "
        "last document parsed overwrite the first — `F4` exactly."
    )
    assert set(forward) == set(backward) == {"a.xml", "b.xml"}
    for name in ("a.xml", "b.xml"):
        assert forward[name] == backward[name], (
            f"{name} came back different depending on whether it was parsed "
            "first or second. Position is not part of the contract, so "
            "something is keyed on an identity that is only unique within "
            "one file — the shape of `F4`."
        )


def test_the_property_is_not_vacuous(tmp_path: Path) -> None:
    """Both files must actually be corrected, or the test above compares two
    documents nobody touched and passes for the wrong reason.

    The op count carries more weight than a vacuity guard usually does: it
    is the assertion that fails when the producer-op index is keyed on a
    bare ``line_id``, because an overwrite is symmetric — both orders lose
    the same op and go on agreeing with each other.
    """
    first, second = _write_pair(tmp_path)
    delivered, ops = _run([(first, "a.xml"), (second, "b.xml")])
    assert len(ops) == 2, (
        f"expected one op per file, got {ops}. With fewer, the ordering "
        "assertion above compares two runs that both lost the same op."
    )

    assert b"france" in delivered["a.xml"], "a.xml was not corrected at all"
    assert b"france" in delivered["b.xml"], "b.xml was not corrected at all"
    assert delivered["a.xml"] != delivered["b.xml"], (
        "the two files came back identical — the fixture stopped differing, "
        "and a collision would no longer be visible."
    )
