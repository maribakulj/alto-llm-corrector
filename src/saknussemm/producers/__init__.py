"""Edition producers (§3) — the concrete :class:`EditProducer` implementations.

Never lxml, never a format module (``tests/test_import_contract.py``).
Beyond ``saknussemm.core`` these may reach ``saknussemm.integrations``
for the vendor vocabulary a producer needs — the LLM prompt contract and
its output schema. The line that used to stand here said "Import only
``saknussemm.core``" and two of the three modules already contradicted
it; ``tests/test_import_contract.py`` now holds the rule so it cannot go
stale again.

The frontier with ``integrations/`` is mechanical: a class that fills
``produce`` implements ``EditProducer`` and belongs HERE, whatever it
needs to do so. ``VisionEditProducer`` lived next door until 2026-08-25
under a criterion — "what exists only because the producer is an LLM" —
that did not discriminate, since it holds for ``LLMEditProducer`` too.
"""
