"""Tests for how a line's terminal decision gets written (`RM-01`).

Grouped by the invariant they protect rather than by the wave that found
them (`RM-05b`): everything here is about the moment a line stops being
a proposal and becomes a decision — which pass writes it, in what order,
and whose reason survives.
"""
