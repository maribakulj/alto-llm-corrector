"""Vendor-specific integration surfaces.

The pure core speaks the generic edit protocol; anything that exists
only because the producer is an LLM — the system prompt, the structured
output JSON schema — lives here, out of ``lidenbrock.core`` and
``lidenbrock.producers``'s generic vocabulary.
"""
