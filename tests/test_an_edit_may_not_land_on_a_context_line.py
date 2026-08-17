"""A producer may not correct a line it was only shown for context.

`E1` reads *"``line_id`` dans le chunk visé"* — in the **targeted** chunk. Its
check in ``apply_edit_script`` has two clauses joined by ``or``: the line is
not in ``chunk_line_ids``, or the line is unknown to ``canonical_by_id``.
``docs/promises.md`` graded the row **partielle**, on the grounds that *"the
only test conflates 'outside the chunk' with 'unknown'; removing the first
clause leaves the suite green"*.

Measured on 2026-08-17, and the grading was right about the symptom and wrong
about the cause. **The first clause is unreachable.** Its only caller is
``core/attempt.py``, which builds ``canonical = {lm.line_id: lm.ocr_text for
lm in chunk_lines}`` and then passes ``chunk_line_ids=set(canonical)`` — the
same set. So clause 1 is true only when clause 2 already is, and no test
could exercise it however well written. Deleting it leaves **1626 tests
green** and this file's behavioural probe byte-identical.

**So what does hold the promise up?** Not `E1`. Measured on
``examples/X0000002.xml``, 566 lines, WINDOW granularity:

* the plan makes **52 chunks**, and **68 lines** are the target of one chunk
  and the *context* of another;
* **13 of the 52** payloads open with a context line;
* ``CorrectionRequest`` carries ``lines: list[LineContext]`` and **nothing
  marks which are targets**, so a producer cannot tell what it is being asked
  to correct;
* ``validate_llm_response`` says so on purpose — *"context lines (present but
  not targets) are accepted when present"*.

A producer that edits the first line of every payload therefore proposes 13
edits to lines it does not own. **None of them reaches a decision** — 52
stamps in, 39 changed lines out, and 39 = 52 − 13 exactly. The protection is
real; it is downstream target filtering, and it is nowhere named. A property
held by a coincidence of two unrelated mechanisms is a property one refactor
away from being lost, which is what this file is for.

**What is still missing, and why it is not fixed here.** The context edit is
*dropped*, not *refused*: nothing records that a producer proposed something
the engine declined. That is the family the rest of this effort has been
closing — the report must say what it turned down — and the field for it,
``edit_rejections``, is in `#108`, still open on a public-surface arbitration.
Making `E1`'s first clause real (passing the **target** set rather than every
chunk line) turns the silent drop into an attributable refusal, and it wants
that field to exist first. Named here rather than half-done.
"""

from __future__ import annotations

from saknussemm.core.editing import EditScript, RangeAnchor, ReplaceSpan
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.planner import plan_page
from saknussemm.core.schemas import ChunkPlannerConfig
from saknussemm.formats.loader import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import RecordingObserver

_SOURCE = EXAMPLES / "X0000002.xml"

#: A character no OCR line in the corpus carries, so its arrival anywhere is
#: proof rather than inference.
_MARK = "¤"


class _EditsThePayloadsFirstLine:
    """Proposes one span edit per payload, on its first line, always.

    Not a contrivance: the payload does not say which of its lines are
    targets, so this is what a producer does when it takes the request at
    face value. A language model shown a window and asked to fix it returns
    the window.
    """

    requires_full_coverage = False

    def __init__(self) -> None:
        self.stamped: list[str] = []

    async def produce(self, payload, *, options):  # noqa: ANN001, ANN202
        first = payload.lines[0]
        self.stamped.append(first.line_id)
        if not first.ocr_text:
            return EditScript(ops=[]), None
        return (
            EditScript(
                ops=[
                    ReplaceSpan(
                        line_id=first.line_id,
                        page_id=payload.page_id,
                        anchor=RangeAnchor(start=0, end=1),
                        text=_MARK,
                    )
                ]
            ),
            None,
        )


def _plan():
    page = build_document_manifest([(_SOURCE, _SOURCE.name)]).pages[0]
    return plan_page(page, "doc", ChunkPlannerConfig())


def _context_first_chunks() -> list:
    """Chunks whose payload opens with a line they do not target."""
    return [
        chunk
        for chunk in _plan().chunks
        if chunk.line_ids and chunk.line_ids[0] not in set(chunk.targets())
    ]


def test_the_case_is_actually_reachable() -> None:
    """The control, because a zero measured on nothing is not a result.

    If the planner stopped putting a context line first — a window policy
    change would do it — the assertion below would pass over an empty set and
    report that context edits are refused.
    """
    chunks = _context_first_chunks()
    assert len(chunks) >= 5, (
        f"only {len(chunks)} of the plan's chunks open with a context line "
        "(measured 2026-08-17: 13 of 52). The producer below would then be "
        "proposing edits it is entitled to make, and this file checks nothing."
    )


def test_lines_are_target_of_one_chunk_and_context_of_another() -> None:
    """The overlap that makes the question worth asking at all.

    `RM-01` — one decision writer per line — is what would be at stake if a
    context edit landed: the line's own chunk decides it too. Also asserted:
    no line is TARGETED twice, which is `RM-01` holding on the side that is
    already guarded.
    """
    targets_of: dict[str, int] = {}
    context_of: dict[str, int] = {}
    for chunk in _plan().chunks:
        owned = set(chunk.targets())
        for line_id in chunk.line_ids:
            counter = targets_of if line_id in owned else context_of
            counter[line_id] = counter.get(line_id, 0) + 1

    twice_targeted = {k: v for k, v in targets_of.items() if v > 1}
    assert not twice_targeted, (
        f"{len(twice_targeted)} line(s) are the target of more than one chunk: "
        f"{list(twice_targeted)[:3]}. Two chunks deciding one line is `RM-01` "
        "broken at the source, before any question of context arises."
    )
    both = set(targets_of) & set(context_of)
    assert len(both) >= 20, (
        f"only {len(both)} line(s) are a target here and context there "
        "(measured 2026-08-17: 68). Without the overlap, a context edit could "
        "not collide with anything and the guard below is uninteresting."
    )


def test_an_edit_to_a_context_line_never_reaches_a_decision() -> None:
    """The property itself, on a real page and through the whole pipeline.

    Checked against the plan's own target sets rather than against the run's
    chunk ids, so the assertion does not depend on the engine agreeing with
    itself about who owned what.
    """
    context_first = {chunk.line_ids[0] for chunk in _context_first_chunks()}
    assert context_first, "guarded by test_the_case_is_actually_reachable"

    producer = _EditsThePayloadsFirstLine()
    manifest = build_document_manifest([(_SOURCE, _SOURCE.name)])
    result = CorrectionPipeline(
        producer=producer, observer=RecordingObserver()
    ).run_sync(document_manifest=manifest, source_files={_SOURCE.name: _SOURCE})

    marked = {
        ref.line_id
        for ref, decision in result.decisions.by_ref.items()
        if _MARK in (decision.final_text or "")
    }
    landed_on_context = sorted(marked & context_first)
    assert not landed_on_context, (
        f"{len(landed_on_context)} line(s) were corrected by a chunk that only "
        f"had them as CONTEXT: {landed_on_context[:3]}. Each of those lines is "
        "also the target of its own chunk, so two chunks decided one line — "
        "`RM-01`. `E1` is not what stops this today: its first clause is "
        "unreachable, and the protection is downstream target filtering."
    )

    # Vacuity: the producer must have been able to change ANYTHING at all.
    assert marked, (
        "no line carries the mark, so the run refused every edit and the "
        "assertion above holds for the wrong reason. Check that a one-character "
        "span replacement still clears the acceptance guards."
    )
    delivered = result.corrected_files[_SOURCE.name].decode("utf-8")
    assert delivered.count(_MARK) == len(marked), (
        f"{delivered.count(_MARK)} mark(s) in the delivered file against "
        f"{len(marked)} in the decisions. The report and the bytes must agree "
        "about which lines changed, whoever proposed the change."
    )


def test_the_payload_does_not_tell_a_producer_which_lines_it_owns() -> None:
    """Named as a fact, because it is why the case above exists.

    ``CorrectionRequest`` carries its lines undifferentiated. A producer
    cannot restrict itself to targets, so "the producer should not have edited
    that line" is not an available answer — the engine has to be the one that
    declines, and it should say that it did (`#108`).

    If a target marker is ever added, this test fails and is the right place
    to record the decision.
    """
    from saknussemm.core.schemas import CorrectionRequest

    fields = set(CorrectionRequest.model_fields)
    assert not {name for name in fields if "target" in name}, (
        f"CorrectionRequest now has a target-related field: {fields}. A "
        "producer can finally tell which lines it is asked to correct, which "
        "changes this file's premise — and makes it reasonable to hold a "
        "producer to it rather than only the engine."
    )
