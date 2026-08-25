"""Format-agnostic hyphen-pair linking (§6.3 parity).

Once a parser has set each line's ``hyphen_role`` (from ALTO's explicit
``SUBS_TYPE``/``HYP`` markup or PAGE's terminal-character heuristic), the
*second pass* that links PART1/BOTH lines to their forward partners is
identical across formats: it reasons purely about ``LineManifest`` roles
and a ``PairingPolicy``, never about XML. It lived in
``formats/alto/parser.py`` until PAGE support needed the exact same
behaviour; hoisting it into the pure core keeps the two format parsers
from drifting and makes ``§6.3`` ("same DocumentManifest regardless of
format") true by construction rather than by discipline.

Nothing here imports lxml or any format module — the import-contract test
keeps it that way.
"""

from __future__ import annotations

from collections.abc import Iterable

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.schemas import (
    DEFAULT_PAIRING_POLICY,
    HyphenRole,
    LineManifest,
    PageManifest,
    PairingPolicy,
)

#: Terminal characters a heuristic parser treats as a word-break hyphen.
#: ALTO relies on explicit ``SUBS_TYPE``/``HYP`` markup and only falls back
#: to a plain ``-``; PAGE has no such markup, so it scans this repertoire.
#:
#: Widening it is not a free act — a new member makes lines pair that did
#: not, on real documents — so each one is here on evidence. Measured over
#: the 40 ALTO/PAGE files in ``examples/`` and ``corpus/``, text content
#: only: 119 line-final ``-``, 25 line-final ``⸗``, zero of everything
#: else.
#:
#: - ``-``  U+002D HYPHEN-MINUS — the common case.
#: - ``¬``  U+00AC — what Transkribus emits for a break.
#: - ``⸗``  U+2E17 DOUBLE OBLIQUE HYPHEN — Fraktur; 25 of the corpus's 144
#:   line-final marks, and its absence here was a real defect (542c783).
#: - ``­``  U+00AD SOFT HYPHEN — emitted by some engines as a hyphen
#:   variant. See ``formats/alto/_text._DEDUP_MARKS`` for the one place it
#:   is deliberately treated differently.
#: - ``‐``  U+2010 HYPHEN and ``‑`` U+2011 NON-BREAKING HYPHEN — the
#:   unambiguous Unicode hyphens. Zero occurrences in the corpora, so they
#:   are latent coverage for a producer that uses them: no measurable risk
#:   either way, and nothing else these characters can mean.
#:
#: Deliberately EXCLUDED, and both for the same reason — they carry other
#: meanings and the corpora give no evidence they are needed here:
#:
#: - ``=`` U+003D — the equals sign of a table or a formula.
#: - ``–`` U+2013 EN DASH — a dialogue dash or a range. The alphabetic-char
#:   requirement in :func:`trailing_hyphen_char` rejects ``1789–`` but not
#:   a line ending on a dash of dialogue.
#:
#: Admitting either needs measurement on a corpus that contains them (M7),
#: not a tuple edit.
HYPHEN_CHARS: tuple[str, ...] = ("-", "¬", "⸗", "­", "‐", "‑")


def preserve_break_char(source_text: str, corrected: str) -> str:
    """P5 — if the source line ends in a word-break character and the
    corrected text ends in a DIFFERENT one, force the corrected text to
    end in the SOURCE's character (no ``-`` ↔ ``¬`` drift; trailing
    whitespace preserved). Idempotent; a no-op when either side carries
    no word-break hyphen.

    Applied BEFORE the decisions materialize. Enforced by the rewriter
    alone, AFTER the decision is recorded, the artefact can diverge from
    the decision and trip ``_verify_projection`` (OCR17+ corpus,
    2026-07-23: source ``tou-`` / oracle ``tou¬``). The rewriter keeps its
    call as
    defence in depth (idempotent).
    """
    src_h = trailing_hyphen_char(source_text, HYPHEN_CHARS)
    if src_h is None:
        return corrected
    stripped = corrected.rstrip()
    trailing_ws = corrected[len(stripped) :]
    for ch in HYPHEN_CHARS:
        if stripped.endswith(ch):
            if ch != src_h:
                stripped = stripped[:-1] + src_h
            break
    return stripped + trailing_ws


#: The repertoire as a character SET, for ``str.rstrip``. Derived, never
#: retyped: a hardcoded ``"-"`` is how five call sites came to guard the ASCII
#: hyphen alone while 32 of the 363 hyphenated lines in the repo's own corpora
#: end in ``⸗`` or ``¬`` (L5).
_BREAK_MARK_CHARS = "".join(HYPHEN_CHARS)


def ends_with_break_mark(text: str) -> bool:
    """Does ``text`` end in a word-break mark from the repertoire?

    Trailing whitespace is ignored. Deliberately WITHOUT
    :func:`trailing_hyphen_char`'s requirement of an alphabetic character
    before the mark: callers of this predicate have already established that
    the line breaks a word (its ROLE says so, from an explicit ``SUBS_TYPE``
    or from that very check), and re-imposing the heuristic here would make
    an explicit ``1789-`` PART1 stop being guarded.
    """
    return text.rstrip().endswith(HYPHEN_CHARS)


def strip_trailing_break_marks(text: str) -> str:
    """``text`` without its trailing break marks, whatever spells them.

    The faithful generalisation of the ``rstrip("-")`` these call sites used
    to do — same "strip every trailing mark" semantics, whole repertoire.
    """
    return text.rstrip(_BREAK_MARK_CHARS)


def trailing_hyphen_char(text: str, hyphen_chars: tuple[str, ...]) -> str | None:
    """Return the trailing hyphen character of ``text``, or ``None``.

    A genuine word-break hyphen is signalled by the last non-space token
    ending in one of ``hyphen_chars`` **with an alphabetic character
    immediately before it** — the same narrowing the ALTO heuristic uses
    to reject year ranges (``1789-``) and list markers (``n°5-``). Returns
    the matched hyphen character (so the caller can preserve it verbatim,
    per P5) or ``None`` when no word-break hyphen is present.
    """
    tokens = text.split()
    if not tokens:
        return None
    last = tokens[-1]
    for ch in hyphen_chars:
        if last.endswith(ch):
            bare = last[: -len(ch)]
            if bare and bare[-1].isalpha():
                return ch
    return None


# ---------------------------------------------------------------------------
# The directed link — ONE place that reads the pointer fields (ADR-010)
# ---------------------------------------------------------------------------
#
# A line carries two link slots, and their names are a trap:
#
#   ``hyphen_pair_*``     the PAIR slot
#   ``hyphen_forward_*``  the FORWARD slot
#
# "Forward" names the SLOT, not the reading direction. A PART1 line's word
# continues onto the line in its PAIR slot; only a BOTH line — tail of one
# hyphenated word and head of the next — uses the FORWARD slot for that.
# Every place that re-derived "which slot holds my continuation?" from the
# role got a chance to get this backwards, and the pipeline's reconciler had
# it spelled out inline, next to a helper that already knew.
#
# So: two functions read a slot, one function maps a role to a slot, and
# nothing else touches these fields.


def pair_ref(lm: LineManifest) -> LineRef | None:
    """The PAIR slot's link, page-qualified — or ``None`` when empty.

    Qualification matters: two ALTO files may declare the same TextLine ID,
    so a bare-id lookup finds the wrong manifest for a cross-page link. An
    unset ``hyphen_pair_page_id`` means "same page as me".
    """
    if not lm.hyphen_pair_line_id:
        return None
    return LineRef(
        page_id=lm.hyphen_pair_page_id or lm.page_id,
        line_id=lm.hyphen_pair_line_id,
    )


def forward_ref(lm: LineManifest) -> LineRef | None:
    """The FORWARD slot's link, page-qualified — or ``None`` when empty.

    See :func:`pair_ref` on qualification, and the note above on why
    "forward" here is a slot name and not a direction.
    """
    if not lm.hyphen_forward_pair_id:
        return None
    return LineRef(
        page_id=lm.hyphen_forward_pair_page_id or lm.page_id,
        line_id=lm.hyphen_forward_pair_id,
    )


def forward_partner_ref(lm: LineManifest) -> LineRef | None:
    """The line this line's word continues ONTO, page-qualified.

    The role→slot map, and the only one: ``PART1`` continues through its
    PAIR slot, ``BOTH`` through its FORWARD slot, ``PART2``/``NONE``
    continue nowhere.

    This is the strictly *directed* edge. Anything that needs the whole
    unit — the window-target assignment, the cross-block union-find, the
    router's escalation set, a fallback that must take partners with it —
    asks :func:`~saknussemm.core.units.derive_hyphen_groups` or
    :func:`~saknussemm.core.units.units_containing` instead: those walk
    both slots and report whether what they found is the complete unit.
    The two notions are deliberately distinct, and conflating them is what
    produced the parallel resolvers ADR-010 is retiring.
    """
    if lm.hyphen_role == HyphenRole.PART1:
        return pair_ref(lm)
    if lm.hyphen_role == HyphenRole.BOTH:
        return forward_ref(lm)
    return None


def forward_break_is_explicit(lm: LineManifest) -> bool:
    """Is THIS line's end-of-line break marked up in the source?

    The same role→slot map as :func:`forward_partner_ref`, applied to the
    explicitness flags: ``PART1`` reads ``hyphen_source_explicit`` (its
    forward link is the PAIR slot), ``BOTH`` reads
    ``hyphen_forward_explicit``.

    The distinction is load-bearing and a real BnF line depends on it.
    ``PAG_00000002_TL000454`` of ``examples/X0000002.xml`` opens with an
    explicit ``SUBS_TYPE="HypPart2"`` and ends on a bare heuristic dash
    (``Wal-``) with no ``<HYP>``: backward explicit, forward heuristic, on
    one line. Reading ``hyphen_source_explicit`` to decide about the
    FORWARD break answered "explicit", so the writer dropped the dash from
    the String expecting a HYP element to render it — and there is none.
    The mark vanished from the artefact.
    """
    if lm.hyphen_role == HyphenRole.BOTH:
        return lm.hyphen_forward_explicit
    return lm.hyphen_source_explicit


def backward_partner_ref(lm: LineManifest) -> LineRef | None:
    """The line whose word continues ONTO this one, page-qualified.

    The mirror of :func:`forward_partner_ref`: ``PART2`` and ``BOTH`` are
    continued into, through their PAIR slot; ``PART1``/``NONE`` are not.

    That this direction had no name until now is not a detail — it is why
    a join could only ever be owned by its TAIL. An intra-page pair does
    not care: both members are in scope together. A CROSS-PAGE pair does,
    because the tail always sits on the earlier page and is decided
    before the head exists, so tail-ownership froze the head on raw OCR
    (`docs/PLAN.md` L3). Naming the incoming edge is what lets the head —
    the only point at which both sides exist — own that join instead.
    """
    if lm.hyphen_role in (HyphenRole.PART2, HyphenRole.BOTH):
        return pair_ref(lm)
    return None


def forward_partner_id(lm: LineManifest) -> str | None:
    """Bare line_id of :func:`forward_partner_ref` — for lookups already
    scoped to one page (the LINE-chain planner, the same-chunk predicate).

    Prefer ``forward_partner_ref`` anywhere a document-wide lookup is in
    play: a bare id is ambiguous across files.
    """
    ref = forward_partner_ref(lm)
    return None if ref is None else ref.line_id


def unpaired_break_refs(pages: Iterable[PageManifest]) -> list[LineRef]:
    """Lines that announce a hyphen break with no partner this run can see.

    A line's ROLE is read off its own text — a trailing break mark makes it
    PART1 — while the LINK is a second pass that can end up with nobody:
    the pairing policy refused the candidate (`PairingPolicy.can_pair`
    returns False and the loop simply moves on), the partner sits on a page
    this run does not have, the pointer dangles.

    Every one of those was silent. The line still ends mid-word, still gets
    corrected alone, and never reaches the reconciler — so its Stage-B
    pair-drift guards never run either. A host reading "0 fallback" had no
    way to learn that N words were split across a seam nobody sewed.

    Counted here rather than reported at each rejection site, because the
    causes are several and the consequence is one: this line's word has no
    continuation in this run. The count belongs on the report next to the
    other things a run admits it could not do.
    """
    known = {line_ref(lm) for page in pages for lm in page.lines}
    orphans: list[LineRef] = []
    for page in pages:
        for lm in page.lines:
            ref = line_ref(lm)
            wants_forward = lm.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
            wants_backward = lm.hyphen_role in (HyphenRole.PART2, HyphenRole.BOTH)
            forward = forward_partner_ref(lm)
            backward = backward_partner_ref(lm)
            missing_forward = wants_forward and (
                forward is None or forward not in known
            )
            missing_backward = wants_backward and (
                backward is None or backward not in known
            )
            if missing_forward or missing_backward:
                orphans.append(ref)
    return orphans


def link_hyphen_pairs(
    lines: list[LineManifest],
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> None:
    """
    Second pass: link PART1/BOTH lines to their forward partners.

    A line with role PART1 or BOTH has a forward PART1 relationship.
    The next line is linked as PART2/BOTH (backward side).

    For PART1:  pair_line_id = forward partner, subs_content = pair subs
    For BOTH:   forward_pair_id = forward partner, forward_subs_content = pair subs
                (backward fields were already set by a previous iteration)

    ``pairing_policy`` (F7) gates each candidate: when it rejects a pair
    (e.g. the candidate sits too far below, or is an implausible reading
    continuation in another block), the link is skipped and the PART1 line
    is left unpaired for the downstream guards to handle. The default
    policy vets *heuristic* pairs geometrically and always trusts
    engine-asserted (explicit) ones; ``PairingPolicy(geometric_checks=
    False)`` restores the historical accept-every-next-line behaviour.
    """
    # L5 — an empty line is skipped OVER, not treated as a wall, and this is
    # the same sentence the cross-page walk already lives by: a line that
    # carries no text can say nothing about a word that spans it; it is a
    # fact about the scan, not about the sentence. Taking `lines[i + 1]`
    # blindly made a blank line the PART2 of the word above it and left the
    # real continuation unlinked — no reconciliation, no pair-drift guards,
    # no atomicity in the planner. Latent on this repo's corpora (0 empty
    # lines in 1711), which is exactly why it needs a test.
    substantive = [line for line in lines if line.ocr_text.strip()]
    for i, line in enumerate(substantive):
        # Skip lines that don't have a forward (PART1) role
        if line.hyphen_role not in (HyphenRole.PART1, HyphenRole.BOTH):
            continue
        if i + 1 >= len(substantive):
            continue

        candidate = substantive[i + 1]

        # Every role can be a forward partner. PART2/BOTH already carry a
        # backward side; NONE is promoted to PART2 below; and a PART1
        # candidate is the MIDDLE of a chain — it ends with its own hyphen
        # AND continues this line's word.
        #
        # The last case must be admitted: rejecting it loses whole chains.
        # A PART2 role is set at parse time solely from an explicit
        # SUBS_TYPE="HypPart2", so in a file with no SUBS_TYPE (the common
        # case — the whole BNL ground-truth corpus, any engine that does
        # not mark hyphenation) BOTH was unreachable and every link of a
        # chain but the last was dropped. An unpaired PART1 is not
        # cosmetic: the hyphen reconciler never runs on it, so neither do
        # the Stage-B pair-drift guards, and it loses its atomicity
        # guarantee in the chunk planner. A real VLM duly re-split
        # `l'orga-`/`nisation` into `l'organi-`/`sation`, moving text
        # across a line boundary with nothing to stop it.

        # F7 — injectable pairing seam. Default policy always accepts.
        if not pairing_policy.can_pair(line, candidate):
            continue

        if candidate.hyphen_role == HyphenRole.PART1:
            # Promote to BOTH. The candidate's own PART1 detection lives in
            # the pair fields (see the parser's `elif is_part1` branch), so
            # it must MOVE to the forward fields before the backward fields
            # are claimed by the link being made here — otherwise this
            # line's trailing hyphen would be silently overwritten.
            candidate.hyphen_forward_explicit = candidate.hyphen_source_explicit
            candidate.hyphen_forward_subs_content = candidate.hyphen_subs_content
            candidate.hyphen_subs_content = None
            candidate.hyphen_role = HyphenRole.BOTH
            candidate.hyphen_source_explicit = (
                line.hyphen_forward_explicit
                if line.hyphen_role == HyphenRole.BOTH
                else line.hyphen_source_explicit
            )

        # Mark NONE candidate as PART2
        if candidate.hyphen_role == HyphenRole.NONE:
            if line.hyphen_role == HyphenRole.BOTH:
                candidate.hyphen_role = HyphenRole.PART2
                candidate.hyphen_source_explicit = line.hyphen_forward_explicit
            else:
                candidate.hyphen_role = HyphenRole.PART2
                candidate.hyphen_source_explicit = line.hyphen_source_explicit

        # Determine subs_content and set links for this pair
        if line.hyphen_role == HyphenRole.BOTH:
            # Forward side of a BOTH line
            subs = (
                line.hyphen_forward_subs_content
                or candidate.hyphen_subs_content
                or None
            )

            # Set forward link on the BOTH line
            line.hyphen_forward_pair_id = candidate.line_id
            line.hyphen_forward_pair_page_id = candidate.page_id
            if subs:
                line.hyphen_forward_subs_content = subs

            # Set backward link on the candidate
            candidate.hyphen_pair_line_id = line.line_id
            candidate.hyphen_pair_page_id = line.page_id
            if subs:
                candidate.hyphen_subs_content = subs
        else:
            # Regular PART1 line
            subs = line.hyphen_subs_content or candidate.hyphen_subs_content

            # Bidirectional link (page_id qualifies for cross-page disambiguation)
            line.hyphen_pair_line_id = candidate.line_id
            line.hyphen_pair_page_id = candidate.page_id
            candidate.hyphen_pair_line_id = line.line_id
            candidate.hyphen_pair_page_id = line.page_id

            if subs:
                line.hyphen_subs_content = subs
                candidate.hyphen_subs_content = subs


def disambiguate_page_ids(
    parsed: list[tuple[str, list[PageManifest]]],
) -> None:
    """Prefix colliding Page IDs with their source filename.

    Multiple transcription files commonly declare the same Page ID
    (``"Page1"``, ``"P1"``…) — a per-scan workflow practically guarantees
    this. Without disambiguation, the pipeline's cross-page hyphen partner
    lookup picks the wrong page, intra-page hyphen pair_page_id refs become
    ambiguous, and the trace/diff/layout endpoints emit duplicate page_id
    values to the frontend.

    This is called BEFORE cross-page hyphen linking so that the qualified
    IDs flow into ``hyphen_pair_page_id`` naturally.
    """
    counts: dict[str, int] = {}
    for _, pages in parsed:
        for p in pages:
            counts[p.page_id] = counts.get(p.page_id, 0) + 1

    colliding = {pid for pid, n in counts.items() if n > 1}
    if not colliding:
        return

    for source_name, pages in parsed:
        for p in pages:
            old_pid = p.page_id
            if old_pid not in colliding:
                continue
            new_pid = f"{source_name}::{old_pid}"
            p.page_id = new_pid
            for b in p.blocks:
                b.page_id = new_pid
            for lm in p.lines:
                lm.page_id = new_pid
                # Intra-page hyphen partner refs were set to the old page_id
                # by link_hyphen_pairs during parsing. Rewrite them to the
                # qualified id so downstream lookups stay consistent.
                if lm.hyphen_pair_page_id == old_pid:
                    lm.hyphen_pair_page_id = new_pid
                if lm.hyphen_forward_pair_page_id == old_pid:
                    lm.hyphen_forward_pair_page_id = new_pid


def _substantive(page: PageManifest) -> list[LineManifest]:
    """The page's lines that carry text.

    One definition, used by both walks — the intra-page link pass and the
    cross-page one — so "an empty line carries nothing" cannot come to mean
    two different things.
    """
    return [line for line in page.lines if line.ocr_text.strip()]


def link_cross_page_hyphens(
    all_pages: list[PageManifest],
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> None:
    """Link a PART1/BOTH line at the bottom of page N to the top of page N+1.

    ``link_hyphen_pairs`` works on any list of consecutive lines, so a
    2-element ``[last_line, first_line]`` list is enough. Only fires when
    the last line looks like an unlinked PART1/BOTH.

    Pages with no lines are **skipped over**, not treated as a wall. A walk
    that compares adjacent pages and ``continue``s on an empty one never
    links a word broken from page 1 onto page 3 when page 2 happens to
    carry no text: the pair is silently lost and both fragments corrected
    as unrelated lines. An empty page carries
    nothing and can say nothing about a word that spans it; it is a fact
    about the scan, not about the sentence.
    """
    with_lines = [page for page in all_pages if _substantive(page)]
    for earlier, later in zip(with_lines, with_lines[1:]):
        # The same rule inside the page as across pages: a blank line at the
        # foot of one page or the head of the next is a fact about the scan.
        # Taking `lines[-1]`/`lines[0]` blindly let one blank line hide a
        # word that spans the seam.
        last_line = _substantive(earlier)[-1]
        first_line = _substantive(later)[0]
        needs_forward_link = (
            last_line.hyphen_role == HyphenRole.PART1
            and not last_line.hyphen_pair_line_id
        ) or (
            last_line.hyphen_role == HyphenRole.BOTH
            and not last_line.hyphen_forward_pair_id
        )
        if needs_forward_link:
            link_hyphen_pairs([last_line, first_line], pairing_policy)


__all__ = [
    "HYPHEN_CHARS",
    "ends_with_break_mark",
    "strip_trailing_break_marks",
    "trailing_hyphen_char",
    "pair_ref",
    "forward_ref",
    "forward_partner_ref",
    "backward_partner_ref",
    "forward_break_is_explicit",
    "forward_partner_id",
    "link_hyphen_pairs",
    "unpaired_break_refs",
    "disambiguate_page_ids",
    "link_cross_page_hyphens",
]
