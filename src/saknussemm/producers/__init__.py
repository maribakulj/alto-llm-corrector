"""Edition producers (§3) — the concrete :class:`EditProducer` implementations.

Never lxml, never a format module (``tests/test_import_contract.py``).
Beyond ``saknussemm.core`` these may reach ``saknussemm.integrations``
for the vendor vocabulary a producer needs — the LLM prompt contract
and its output schema. The line that used to stand here said "Import
only ``saknussemm.core``" and two of the three modules already
contradicted it.
"""
