"""Tests for the hyphen unit — all of them, in one place.

The second directory organised by invariant rather than by the wave that
found the case (`RM-05b`, after `tests/decision/`), and the one that
matters most: `S1` has to move the hyphen unit from pointer fields to a
derived unit, and that is not attemptable while the cases which would
catch a regression sit in twenty-two files spread across the suite, three
of them named after remediation waves.

Everything here is about one object — a word broken across two physical
lines — and the files answer five questions about it.

**Which candidates are pairs at all** — detection and linking:

  ``test_pair_vetting``            the injectable policy's two refusals
  ``test_pairing_core``            the linker's own rules
  ``test_pairing_policy``          ``PairingPolicy`` over real documents
  ``test_geometric_pairing``       the geometric vetting of heuristic pairs
  ``test_directed_link``           the directed primitives (ADR-010)
  ``test_link_symmetry``           forward and backward agree, over corpora

**How the break is spelled** — the mark, in the source and in the output:

  ``test_break_char_coherence``    the mark the parser reads and re-emits
  ``test_break_mark_reconstruction`` the mark survives the rewrite
  ``test_break_mark_repertoire_in_guards`` the whole repertoire, not ``-``
  ``test_double_dash``             HYP + trailing dash is one dash
  ``test_part1_double_hyphen``     …and the PART1 twin of it

**What the two lines may become** — reconciliation:

  ``test_hyphenation``             the reconciler, at length
  ``test_pair_reconciliation``     the boundary of acceptance
  ``test_chained_hyphenation``     three members and more
  ``test_cross_page_hyphen_decision`` the pair that leaves the page
  ``test_metamorphic_hyphenation`` properties that must survive any input

**The unit lives or falls back whole** — atomicity:

  ``test_units``                   the derivation itself
  ``test_unit_atomicity``          reverts and planner cuts reach the unit
  ``test_unit_fallback_atomicity`` a fallback covers every member
  ``test_chunking_keeps_units_whole`` no unit is split across chunks
  ``test_hyphen_pairing_invariant``   the invariant over a real document
  ``test_hyphen_splits_reach_the_report`` a severed link is reported

**The producer must not have merged them**:

  ``test_fusion_detection``        the validator refuses a fused response

Nothing here was rewritten to arrive. The four files with new names hold
cases moved out of wave-named files with their names, docstrings and
bodies character-identical (P5); the nineteen with their original names
are ``git mv`` and nothing else. File renames are deliberately NOT part
of this step — a rename is a separate decision from a move, and doing both
at once makes the diff unreadable.
"""
