"""The aligner had to stop materialising what it only reads once.

`align_tokens` is used at one line's scale today — a handful of tokens, and
the exact alignment is instant. Its docstring said ``O(n × m) token pairs``,
which reads as a statement about time and says nothing about the memory. Both
were measured on 2026-08-19, and the second is the one that bites:

    tokens      time      similarity matrix
        50    0.005 s
       200    0.095 s
       800    1.83 s
      2000   14.25 s               128 MB

Measured on the 28 real Gallica pages rather than extrapolated: the median
page carries **6 157** tokens and the heaviest **9 730**. At that size the
exact algorithm needs roughly 2.4 GB for the similarity matrix alone, and as
much again for the cost matrix. Page-scale alignment would not have been
slow — it would have run out of memory before finishing.

After the rewrite, the same 28 pages banded at 50: **4.48 s** on the heaviest,
**74.5 s** for all 168 270 tokens, **31 MB** peak. From impossible to
affordable, against a page mode whose API calls cost minutes anyway.

Two costs, removed for different reasons:

- The **similarity matrix** was pure waste. The DP reads each token pair
  exactly once, so keeping the value bought nothing at all.
- The **cost matrix** is genuinely needed to backtrack, so it stays — but a
  band restricts it to a corridor around the diagonal, which is sound here
  for a reason particular to this problem: a corrected text is the source
  with words fixed, so its alignment is nearly diagonal by construction.

And where it is not — the model reordered a passage, or dropped one — the
path leaves the corridor. That is reported as `band_exhausted`, never
approximated away. The band is what makes page scale affordable AND what
tells a caller its answer cannot be trusted; the two are the same mechanism.

A third quadratic hid in `source_for_target`, which scanned the pairs and was
called once per target token — so reading one alignment back was O(pairs²)
on top of the DP.
"""

from __future__ import annotations

import random

import pytest

from saknussemm.core.alignment import align_tokens, char_similarity


def _reference(source: list[str], target: list[str]):
    """The exact algorithm as it stood before the rewrite, as the oracle.

    Kept here rather than in the module because the module has one
    implementation on purpose. A rewrite that changes what the aligner SAYS
    is a different change from one that changes what it costs, and only a
    side-by-side comparison can tell them apart.
    """
    n, m = len(source), len(target)
    sim = [[char_similarity(source[i], target[j]) for j in range(m)] for i in range(n)]
    gap = 1.0
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i * gap
    for j in range(1, m + 1):
        cost[0][j] = j * gap
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(
                cost[i - 1][j] + gap,
                cost[i][j - 1] + gap,
                cost[i - 1][j - 1] + 2.0 * (1.0 - sim[i - 1][j - 1]),
            )
    pairs = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            sub = cost[i - 1][j - 1] + 2.0 * (1.0 - sim[i - 1][j - 1])
            if abs(cost[i][j] - sub) < 1e-9 and sim[i - 1][j - 1] > 0.0:
                pairs.append((i - 1, j - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and abs(cost[i][j] - (cost[i - 1][j] + gap)) < 1e-9:
            pairs.append((i - 1, None))
            i -= 1
            continue
        pairs.append((None, j - 1))
        j -= 1
    pairs.reverse()
    return pairs


_WORDS = "le la des un une mot texte ligne page livre France Frauce lll Ill 0 o".split()


def _corrupt(rng: random.Random, tokens: list[str]) -> list[str]:
    """A plausible correction: substitutions, a deletion, an insertion."""
    out = []
    for token in tokens:
        roll = rng.random()
        if roll < 0.08:
            continue  # dropped word
        if roll < 0.16:
            out.append(rng.choice(_WORDS))  # inserted word
        out.append(token if roll > 0.30 else token.replace("l", "I"))
    return out


@pytest.mark.parametrize("seed", range(40))
def test_the_unbanded_alignment_is_unchanged(seed: int) -> None:
    """Without a band it must say EXACTLY what it always said.

    Forty seeded pairs over a repertoire chosen so the interesting cases
    actually occur: `Frauce`/`France` (a near match), `0`/`o` and `lll`/`Ill`
    (the shape the fast-path guard exists for), and repeated tokens, which are
    where a tie-break can quietly differ.
    """
    rng = random.Random(seed)
    source = [rng.choice(_WORDS) for _ in range(rng.randint(1, 30))]
    target = _corrupt(rng, source)
    got = [(p.source_index, p.target_index) for p in align_tokens(source, target).pairs]
    assert got == _reference(source, target)


def test_a_band_wide_enough_agrees_with_no_band_at_all() -> None:
    """A corridor wider than the sequence searches everything.

    If these two ever disagreed, the band would be changing the ANSWER rather
    than the cost, which is the one thing it must never do.
    """
    rng = random.Random(7)
    source = [rng.choice(_WORDS) for _ in range(60)]
    target = _corrupt(rng, source)
    wide = align_tokens(source, target, band=200)
    exact = align_tokens(source, target)
    assert wide.pairs == exact.pairs
    assert wide.band_exhausted is False


def test_a_band_narrower_than_the_length_difference_still_has_a_path() -> None:
    """`band=0` on sequences of different length has NO corner-to-corner path.

    The answer would not merely be approximate — it would not exist, and the
    backtrack would walk off an all-infinity row. The band widens to the
    length difference rather than pretending.
    """
    source = ["a", "b", "c", "d", "e"]
    target = ["a", "e"]
    alignment = align_tokens(source, target, band=0)
    assert alignment.pairs, "an impossible band must widen, not return nothing"
    covered = {p.source_index for p in alignment.pairs if p.source_index is not None}
    assert covered == set(range(5))


def test_an_excursion_the_corridor_forbids_is_reported() -> None:
    """What the flag actually detects, measured rather than assumed.

    A block transposition whose two halves share NO character: the diagonal
    reading is worth nothing, so the true path has to travel 30 columns
    sideways, and a corridor narrower than that cannot contain it. Fires at
    bands 3, 10, 20 and 29; goes quiet at 40, which is wide enough to hold
    the excursion. That is the flag saying exactly what it means — "I did not
    search where the answer was" — and nothing more.
    """
    import itertools

    head = [
        "".join(c) for c in itertools.islice(itertools.product("bcdf", repeat=3), 30)
    ]
    tail = [
        "".join(c) for c in itertools.islice(itertools.product("wxyz", repeat=3), 30)
    ]
    for narrow in (3, 10, 20, 29):
        assert (
            align_tokens(head + tail, tail + head, band=narrow).band_exhausted is True
        )
    assert align_tokens(head + tail, tail + head, band=40).band_exhausted is False


def test_a_transposition_of_SIMILAR_tokens_does_not_trip_it_and_should_not() -> None:
    """The correction that first version of this test got wrong.

    `w0` and `w40` share their `w` and a digit, so a mediocre diagonal match
    (cost 2 × 0.33) beats a deletion paired with an insertion (cost 2.0). The
    path therefore stays in the corridor, and the flag is RIGHT to stay quiet:
    it reports where the search went, not whether the reading is good.

    Pinned because it is the boundary of what the flag is worth. Reading it as
    "no reordering happened" would be reading it as something it never says.
    """
    source = [f"w{i}" for i in range(60)]
    assert (
        align_tokens(source, source[40:] + source[:40], band=3).band_exhausted is False
    )


def test_a_large_deletion_does_not_trip_it_either_and_that_is_deliberate() -> None:
    """The limit of the flag, pinned so nobody builds a guard on it by mistake.

    A model that drops 80 of 200 tokens does not push the path out of the
    corridor: the corridor WIDENS to the length difference, because a band
    narrower than it leaves no corner-to-corner path at all. So the most
    obvious page-scale failure — a chunk silently missing — is invisible here.

    It is not undetectable, it is detectable *elsewhere*: a dropped chunk
    shows up as a run of deletions in the pairs, and a shifted line collapses
    `min_source_similarity` on every line after it (measured: 100% of 1 736
    shifted lines refused, three corpora, 2026-08-18). Two different
    measurements for two different failures. Conflating them into this flag
    would give page mode a guard that is quiet exactly when it matters.
    """
    source = [f"w{i}" for i in range(200)]
    target = source[:80] + source[160:]
    assert align_tokens(source, target, band=5).band_exhausted is False


def test_an_ordinary_correction_never_trips_the_band() -> None:
    """The other half: the flag must not cry wolf on the normal case.

    A guard that fires on ordinary corrections gets widened until it is
    silent, and then it guards nothing.
    """
    rng = random.Random(11)
    source = [rng.choice(_WORDS) for _ in range(200)]
    target = _corrupt(rng, source)
    assert align_tokens(source, target, band=50).band_exhausted is False


def test_no_band_never_reports_exhaustion() -> None:
    """Nothing was left unsearched, so nothing can have been missed."""
    source = [f"w{i}" for i in range(30)]
    assert align_tokens(source, list(reversed(source))).band_exhausted is False


def test_reading_an_alignment_back_is_not_a_second_quadratic() -> None:
    """`source_for_target` is asked once per target token by the rewriter.

    Scanning the pairs each time made reading a whole alignment O(pairs²).
    Indexing it is invisible at one line's scale and is the difference
    between usable and not at a page's.
    """
    source = [f"w{i}" for i in range(400)]
    alignment = align_tokens(source, list(source), band=10)
    assert [alignment.source_for_target(j) for j in range(400)] == list(range(400))
