"""Rules producer tests (spec §5.3) — deterministic ReplaceSpan emission."""

from __future__ import annotations

import asyncio

from saknussemm.core.protocols import ProducerOptions
from saknussemm.core.editing import RangeAnchor, ReplaceSpan, apply_edit_script
from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.producers.rules import (
    RulesProducer,
    SubstitutionRule,
    default_french_ocr_rules,
)

from tests._paths import EXAMPLES

_EXAMPLES = EXAMPLES


# ---------------------------------------------------------------------------
# Literal substitution + exact offsets
# ---------------------------------------------------------------------------


def test_long_s_offsets_and_replacement():
    prod = RulesProducer(default_french_ocr_rules())
    script = prod.build_edit_script({"l1": "ſciences"})
    assert len(script.ops) == 1
    op = script.ops[0]
    assert isinstance(op, ReplaceSpan)
    assert op.anchor == RangeAnchor(start=0, end=1)
    assert op.text == "s"
    # Applying it yields the corrected word.
    res = apply_edit_script(script, {"l1": "ſciences"})
    assert res.text_by_id == {"l1": "sciences"}
    assert res.rejected == []


def test_multiple_matches_same_line_all_emitted_nonoverlapping():
    prod = RulesProducer(default_french_ocr_rules())
    text = "ſuccès du ſavoir"
    script = prod.build_edit_script({"l1": text})
    assert len(script.ops) == 2  # two long-s
    res = apply_edit_script(script, {"l1": text})
    assert res.text_by_id == {"l1": "succès du savoir"}
    assert res.rejected == []  # never overlaps → nothing rejected


def test_no_op_substitution_not_emitted():
    prod = RulesProducer([SubstitutionRule("a", "a")])
    assert prod.build_edit_script({"l1": "banana"}).ops == []


# ---------------------------------------------------------------------------
# Regex + lexicon guard
# ---------------------------------------------------------------------------


def test_lexicon_guarded_rule_fires_only_when_word_becomes_known():
    rule = SubstitutionRule("rn", "m", regex=True, lexicon_guarded=True, name="rn_m")
    prod = RulesProducer([rule], lexicon={"moderne"})
    # "modeme" is a typo for "moderne"? no — rn->m on "moderne" gives "modeme".
    # Test the correcting direction: source has the confusion, lexicon has target.
    prod2 = RulesProducer(
        [SubstitutionRule("rn", "m", regex=True, lexicon_guarded=True)],
        lexicon={"homme"},
    )
    # "horneme" -> apply rn->m at pos1 -> "homeme" (not in lexicon) rejected;
    # use a word that becomes known:
    prod3 = RulesProducer(
        [SubstitutionRule("rn", "m", regex=True, lexicon_guarded=True)],
        lexicon={"femme"},
    )
    script = prod3.build_edit_script({"l1": "la fernme"})
    res = apply_edit_script(script, {"l1": "la fernme"})
    assert res.text_by_id == {"l1": "la femme"}

    # Same rule, no matching lexicon entry → no op emitted.
    prod_empty = RulesProducer(
        [SubstitutionRule("rn", "m", regex=True, lexicon_guarded=True)],
        lexicon={"autre"},
    )
    assert prod_empty.build_edit_script({"l1": "la fernme"}).ops == []


# ---------------------------------------------------------------------------
# Determinism + validity
# ---------------------------------------------------------------------------


def test_determinism_same_input_same_script():
    prod = RulesProducer(default_french_ocr_rules())
    text = {"a": "ſoleil", "b": "ﬁn de ﬂamme"}
    s1 = prod.build_edit_script(text)
    s2 = prod.build_edit_script(text)
    assert s1.model_dump() == s2.model_dump()


def test_target_ids_restrict_emission():
    prod = RulesProducer(default_french_ocr_rules())
    script = prod.build_edit_script({"a": "ſa", "b": "ſb"}, target_ids={"a"})
    assert {op.line_id for op in script.ops} == {"a"}


def test_produce_contract_shape_returns_no_usage():
    """§5.1 — produce(payload, *, options) over an CorrectionRequest."""
    from saknussemm.core.schemas import (
        ChunkGranularity,
        LineContext,
        CorrectionRequest,
    )

    prod = RulesProducer(default_french_ocr_rules())
    assert prod.requires_full_coverage is False  # no op == no edit
    payload = CorrectionRequest(
        granularity=ChunkGranularity.LINE,
        document_id="d",
        page_id="p",
        lines=[LineContext(line_id="l1", ocr_text="ſi")],
    )
    script, usage = asyncio.run(prod.produce(payload, options=ProducerOptions()))
    assert usage is None
    assert script.ops[0].text == "s"


# ---------------------------------------------------------------------------
# Real corpus — long-s pass applies cleanly, nothing rejected
# ---------------------------------------------------------------------------


def test_rules_pass_over_descartes_page_applies_cleanly():
    xml = (
        _EXAMPLES
        / "page"
        / "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml"
    )
    from saknussemm.formats.page.parser import build_document_manifest as page_doc

    doc = page_doc([(xml, xml.name)])
    canonical = {lm.line_id: lm.ocr_text for p in doc.pages for lm in p.lines}
    prod = RulesProducer(default_french_ocr_rules())
    script = prod.build_edit_script(canonical)
    assert script.ops, "expected long-s substitutions on a 17th c. page"

    res = apply_edit_script(script, canonical)
    # Deterministic engine emits only valid, non-overlapping spans.
    assert res.rejected == []
    # Every corrected line has no long-s left where the rule fired.
    for lid, txt in res.text_by_id.items():
        assert "ſ" not in txt


def test_alto_corpus_rules_are_byte_reproducible():
    xml = _EXAMPLES / "sample.xml"
    doc = build_document_manifest([(xml, xml.name)])
    canonical = {lm.line_id: lm.ocr_text for p in doc.pages for lm in p.lines}
    prod = RulesProducer([SubstitutionRule("e", "3")])
    a = prod.build_edit_script(canonical).model_dump_json()
    b = prod.build_edit_script(canonical).model_dump_json()
    assert a == b


# ---------------------------------------------------------------------------
# The lexicon guard: normalisation, and composition WITHIN a token
# (moved here from two wave-named files, `RM-05b`)
# ---------------------------------------------------------------------------


def test_lexicon_guard_matches_nfd_entry():
    import unicodedata

    # Lexicon supplied in DECOMPOSED (NFD) form; the token the rule produces
    # is composed (NFC, as the parser emits). The guard must still fire.
    nfd_word = unicodedata.normalize("NFD", "modérné")
    assert nfd_word != "modérné"  # sanity: genuinely decomposed
    prod = RulesProducer(
        [SubstitutionRule("rn", "rné", lexicon_guarded=True)],
        lexicon={nfd_word},
    )
    # OCR "modérn" → the guarded rule turns "rn" into "rné" giving the known
    # word "modérné"; the guard (NFC-folded) accepts it.
    script = prod.build_edit_script({"l1": "modérn"})
    assert script.ops, "guarded substitution should fire against an NFD lexicon"


def _rules_producer(lexicon: set[str]):
    from saknussemm.producers.rules import RulesProducer, SubstitutionRule

    return RulesProducer(
        [
            SubstitutionRule("rn", "m", lexicon_guarded=True),
            SubstitutionRule("ae", "a", lexicon_guarded=True),
        ],
        lexicon=lexicon,
    )


def test_f11_composed_token_out_of_lexicon_rejects_the_batch():
    """'cornae' with rn→m at [2,4) and ae→a at [4,6): each single-edit
    result ('comae', 'corna') is in the lexicon so both guards pass in
    isolation, but the composition 'coma' is NOT — pre-fix both were
    emitted, violating the guard's contract."""
    producer = _rules_producer({"comae", "corna"})
    script = producer.build_edit_script({"l1": "cornae"})
    assert script.ops == [], script.ops


def test_f11_composed_token_in_lexicon_still_accepted():
    producer = _rules_producer({"comae", "corna", "coma"})
    script = producer.build_edit_script({"l1": "cornae"})
    assert len(script.ops) == 2


def test_f11_edits_in_distinct_tokens_unaffected():
    """Composition only matters WITHIN a token: one guarded edit per
    word keeps the historical single-edit validation."""
    producer = _rules_producer({"bome", "cura"})
    script = producer.build_edit_script({"l1": "borne curae"})
    assert len(script.ops) == 2
    assert {op.text for op in script.ops} == {"m", "a"}


def test_f11_single_guarded_edit_behaviour_unchanged():
    from saknussemm.producers.rules import RulesProducer, SubstitutionRule

    producer = RulesProducer(
        [SubstitutionRule("rn", "m", lexicon_guarded=True)],
        lexicon={"moderne"},
    )
    script = producer.build_edit_script({"l1": "modeme moderne"})
    assert script.ops == []  # 'modeme' has no 'rn'; nothing to do
    script = RulesProducer(
        [SubstitutionRule("m", "rn", lexicon_guarded=True)],
        lexicon={"moderne"},
    ).build_edit_script({"l1": "modeme"})
    # modeme → moderne via the SECOND 'm' only ([4,5)); the first 'm'
    # ([0,1)) fails its guard. Exactly one op survives.
    assert len(script.ops) == 1
    assert script.ops[0].anchor.start == 4
