"""Tests for the hyphen unit, grouped by the invariant they protect.

The second directory organised by invariant rather than by the wave that
found the case (`RM-05b`, after `tests/decision/`), and the one that
matters most: `S1` has to move the hyphen unit from pointer fields to a
derived unit, and that is not attemptable while the cases which would
catch a regression are scattered across three files named after
remediation waves.

Everything here is about one object — a word broken across two physical
lines — asked four ways:

  ``test_pair_vetting``         which candidate pairs are pairs at all
  ``test_pair_reconciliation``  what the two lines are allowed to become
  ``test_unit_atomicity``       the whole unit lives or falls back together
  ``test_fusion_detection``     the producer must not have merged them

Every case moved here kept its name, its docstring and its body to the
character (P5). Nothing was added, nothing was dropped, and the only edit
to a moved line is one helper call renamed to its alias in
``test_unit_atomicity``, where two files' ``_line`` builders met.
"""
