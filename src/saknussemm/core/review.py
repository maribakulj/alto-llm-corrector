"""What the library cannot establish about a correction it delivered.

The stage-C guards compare characters. They have no notion of meaning,
and no threshold gives them one: on twelve counter-examples put through
the real :func:`guards.check_line`, all twelve were accepted at both
threshold settings — a removed negation scored 0.8955, a changed date
0.9388, a truncated amount 0.9643, a neighbouring line copied verbatim
0.8852. Tightening the similarity bound far enough to catch those
rejects the ordinary OCR fixes the library exists to make. The family is
a property of the design, not a defect in the numbers.

So this module does not try to decide. It **refers**: it names the
corrections whose rightness the run has no means of establishing, and
:func:`decide.refer_for_review` moves them to ``REVIEW_REQUIRED``
without touching a single character of the delivered text. A referral is
a statement about the CHECK, never a verdict on the correction — on the
real run this feature was measured against, the great majority of the
flagged changes were good ones, which is exactly why they ship.

Two families of rule, and the second is why this runs once over the
whole document rather than line by line:

``per line``
    the evidence is in the pair (source, correction): a digit that
    changed, a negation that appeared or vanished, a proper noun that
    was respelled.

``run level``
    the evidence exists only in the aggregate. The measured case: a
    model that removed ``⸗`` on **34 of its 34** occurrences and
    normalised ``’`` on **69 of 69**. Line by line each is an
    unremarkable one-character edit; over a run it is a systematic
    rewriting of the document's typography, which is not correction and
    which no per-line check can see.

Pure functions over ``(ref, source, final)`` triples: no manifest, no
trace, no policy read off the engine. The pass that applies them lives
in ``core/acceptance.py`` with the other document-wide passes.

**Three referral rules are deliberately absent**, and each is absent for
a reason about the engine rather than about the effort. A declared
reason nothing can emit is a promise a consumer never collects — the
discipline ``tests/test_the_fallback_reasons_are_a_closed_set.py``
already enforces for the fallback vocabulary, applied here before the
fact:

*A line that was already correct and got modified anyway.* Written and
measured, then withdrawn. Judging a source line undamaged without a
lexicon comes down to structural signals — a character outside ordinary
punctuation, a token mixing letters and digits, a double space — and
heritage OCR damage leaves none of them: ``fciences`` for ``ſciences``
is letters throughout. On the ground-truth corpus the rule referred 30
of the 47 changed lines, 23 of them on its own evidence alone, and what
it caught was plain ``f`` → ``ſ`` fixes. It was not detecting lines that
were already correct; it was detecting corrections outside a
twelve-entry confusion table, which is nearly all of them. The honest
form needs a lexicon — which this library does not carry, and which
``confidence.HeuristicScorer`` lets a host inject.

*Text producer versus vision producer disagreement.* No run ever asks
two producers the same line: escalation REPLACES the producer for a
chunk, it does not second it. The rule needs a routing mode that
consults both and keeps both answers — a routing policy, not a rule.

*Uncalibrated confidence below a threshold.* The confidence aggregate is
built in ``core/report.py``, after the ``DecisionSet`` has materialised
and become immutable (ADR-011); a referral cannot read it without either
moving that computation or performing it twice, and two accounting sites
for one number is a defect this repository has already paid for once.
The second obstacle outlives the first: ``core/confidence.py`` states
its own values are not calibrated probabilities, so the threshold would
be exactly the magic number this module exists to say does not work.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from difflib import SequenceMatcher

from saknussemm.core.identity import LineRef
from saknussemm.core.schemas import ReviewPolicy

#: Runs of digits. Dates and amounts are not parsed, deliberately: every
#: notation this library will meet — ``1er janvier 1890``, ``12 fr. 50``,
#: ``MDCCCXC`` — would need its own grammar, and a referral only has to
#: be right about the evidence it names. "The digits are not the same"
#: needs no grammar and covers the year, the page number, the price and
#: the article number at once. What it does not cover is a month spelled
#: out: ``janvier`` → ``février`` changes no digit, and unless the name
#: is capitalised no rule here refers it.
_DIGIT_RUN = re.compile(r"\d+")

#: Letter runs, apostrophes and inner hyphens kept together so that
#: ``aujourd'hui`` and ``Saint-Denis`` are one token each.
_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)

#: Bare letter runs — the tokenisation the negation test needs, because
#: French elides its negation onto the next word (``n'est``) and the
#: particle has to come out as a token of its own.
_LETTERS = re.compile(r"[^\W\d_]+", re.UNICODE)

#: Negation particles, French and English. ``n`` is the elided ``ne``
#: (``n'est``, ``n'a``) and is in the set for that reason; it also
#: matches the ``n`` of ``n° 5``, a false positive the rule accepts,
#: because it can only fire when the COUNT changed and a correction that
#: leaves ``n°`` alone never trips it.
#:
#: ``plus``, ``point``, ``personne`` and ``rien`` are ordinary words as
#: often as they are negations, and they are here for the same reason: a
#: model that adds or removes one of them changed something worth a
#: human's eye whichever sense it carried.
_NEGATIONS = frozenset(
    {
        # français
        "ne",
        "n",
        "pas",
        "plus",
        "jamais",
        "rien",
        "personne",
        "aucun",
        "aucune",
        "aucuns",
        "aucunes",
        "ni",
        "nul",
        "nulle",
        "nullement",
        "sans",
        "non",
        "point",
        "guère",
        # english
        "not",
        "no",
        "never",
        "none",
        "nor",
        "neither",
        "without",
        "nothing",
        "nobody",
        "cannot",
    }
)

#: What a systematic-substitution detail shows when the character was
#: removed rather than replaced.
_NOTHING = "∅"


def _edits(source: str, final: str) -> tuple[tuple[str, str], ...]:
    """The character-level edits turning *source* into *final*, as
    ``(removed, added)`` pairs.

    ``autojunk=False`` for the reason ``guards._similarity`` documents:
    past difflib's 200-element threshold the default treats the common
    characters as junk, and on a long line the opcodes stop describing
    the change.
    """
    matcher = SequenceMatcher(None, source, final, autojunk=False)
    return tuple(
        (source[i1:i2], final[j1:j2])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )


def _difference(before: Counter[str], after: Counter[str], code: str) -> str | None:
    """``"code: what left → what arrived"``, or ``None`` if nothing moved.

    The three per-line rules differ only in what they count, so they
    share how they say it: a reader comparing a ``digits_changed`` line
    with a ``proper_noun_changed`` one reads the same shape twice.
    """
    if before == after:
        return None
    removed = sorted((before - after).elements())
    added = sorted((after - before).elements())
    return f"{code}: {', '.join(removed) or _NOTHING} → {', '.join(added) or _NOTHING}"


def _digit_runs(text: str) -> Counter[str]:
    """Rule 1's evidence — the digit groups the line carries."""
    return Counter(_DIGIT_RUN.findall(text))


def _negations(text: str) -> Counter[str]:
    """Rule 2's evidence.

    The counter-example that motivates the rule scored 0.8955 against
    its source: dropping ``ne`` and ``pas`` changes four characters and
    reverses the sentence.
    """
    return Counter(
        word
        for word in (token.lower() for token in _LETTERS.findall(text))
        if word in _NEGATIONS
    )


def _capitalised(text: str) -> Counter[str]:
    """Rule 3's evidence — tokens shaped like a proper noun: an initial
    capital, at least two characters, and NOT the first token of the line.

    Excluding position 0 is the one concession to noise: a printed line
    begins with a capital because it begins. Capitals after a full stop
    are kept, and so are acronyms — a changed acronym is exactly as
    unverifiable as a changed surname.

    This rule fires most, and that is not something to tune away.
    ``Bcaumarchais`` → ``Beaumarchais`` is very probably right, and the
    library has no means whatsoever of establishing it: no lexicon holds
    the names in a nineteenth-century newspaper, and the guards see a
    one-character edit at similarity 0.99. Delivering it while saying so
    is the whole design.
    """
    tokens = _WORD.findall(text)
    return Counter(t for t in tokens[1:] if len(t) >= 2 and t[0].isupper())


def _systematic_map(
    changed: Sequence[tuple[LineRef, str, str, tuple[tuple[str, str], ...]]],
    *,
    min_occurrences: int,
) -> dict[str, str]:
    """``character → what replaced it, everywhere`` over the whole run.

    A character qualifies when it occurs at least *min_occurrences* times
    across the corrected lines' SOURCES, when every one of those
    occurrences was edited, and when every edit sent it to the same
    place — another character, or nothing at all.

    "Every occurrence" is the load-bearing half. A model that turns some
    ``’`` into ``'`` is making choices about a text; a model that turns
    all sixty-nine of them is applying a rule of its own, and only this
    tally tells the two apart.

    Multi-character edits are skipped rather than split: ``rn`` → ``m``
    says nothing about ``r`` alone, and attributing it to either half
    would invent evidence.
    """
    occurrences: Counter[str] = Counter()
    touched: Counter[str] = Counter()
    targets: dict[str, set[str]] = {}
    for _ref, source, _final, edits in changed:
        occurrences.update(source)
        for removed, added in edits:
            if len(removed) != 1:
                continue
            touched[removed] += 1
            targets.setdefault(removed, set()).add(added)

    systematic: dict[str, str] = {}
    for char, total in occurrences.items():
        if total < min_occurrences or touched[char] != total:
            continue
        destinations = targets.get(char, set())
        if len(destinations) == 1:
            systematic[char] = next(iter(destinations))
    return systematic


def find_review_referrals(
    lines: Iterable[tuple[LineRef, str, str]],
    *,
    policy: ReviewPolicy,
) -> dict[LineRef, tuple[str, ...]]:
    """``line → the reasons its correction cannot be established``.

    *lines* is every line of the run as ``(ref, source, final)``. A line
    whose final text equals its source contributes nothing: there is no
    change to be unable to verify, which is also what keeps a run that
    corrected nothing free of referrals.

    The result names only referred lines. A line may carry several
    reasons — they are independent findings, and a reviewer needs all of
    them rather than whichever rule happened to run first.
    """
    if not policy.enabled:
        return {}

    changed = [
        (ref, source, final, _edits(source, final))
        for ref, source, final in lines
        if final != source
    ]
    referrals: dict[LineRef, list[str]] = {}

    def refer(ref: LineRef, reason: str) -> None:
        reasons = referrals.setdefault(ref, [])
        if reason not in reasons:
            reasons.append(reason)

    per_line = (
        (policy.digits_changed, _digit_runs, "digits_changed"),
        (policy.negation_changed, _negations, "negation_changed"),
        (policy.proper_noun_changed, _capitalised, "proper_noun_changed"),
    )
    for ref, source, final, _ in changed:
        for enabled, evidence, code in per_line:
            if enabled and (
                reason := _difference(evidence(source), evidence(final), code)
            ):
                refer(ref, reason)

    if policy.systematic_substitution:
        systematic = _systematic_map(
            changed, min_occurrences=policy.min_systematic_occurrences
        )
        for char, destination in sorted(systematic.items()):
            code = (
                "systematic_removal" if destination == "" else "systematic_substitution"
            )
            shown = repr(destination) if destination else _NOTHING
            reason = (
                f"{code}: {char!r} → {shown} on every one of its occurrences in the run"
            )
            for ref, source, _final, _ in changed:
                if char in source:
                    refer(ref, reason)

    return {ref: tuple(reasons) for ref, reasons in referrals.items()}


__all__ = ["find_review_referrals"]
