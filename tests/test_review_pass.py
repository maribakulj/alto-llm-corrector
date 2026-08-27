"""Ce que le renvoi en revue fait à un run réel, et ce qu'il ne fait pas.

`review_required` est une quatrième valeur de statut, et une valeur de
statut est ce qu'un consommateur lit en premier. La quasi-totalité de sa
correction tient dans deux propriétés qui n'ont rien d'évident et que rien
d'autre ne vérifie :

**la correction est LIVRÉE.** Un renvoi n'est pas un repli. La ligne garde
le texte que le producteur a proposé, le fichier le porte, et le script
d'édition porte son opération. C'est la moitié qu'un lecteur presse
d'ajouter un état risque d'oublier — et le site qui l'aurait oubliée
existait : ``report._build_final_edit_script`` filtrait sur
``status is CORRECTED``.

**aucun octet ne bouge.** La passe n'écrit pas de texte, donc activer ou
désactiver les règles doit rendre exactement le même fichier. C'est ce qui
autorise `enabled=True` par défaut : le défaut change ce que le run DIT,
jamais ce qu'il livre. Assertée ici en comparant les octets des deux runs
plutôt qu'en le promettant dans une docstring.

Le reste tient l'ordre (la passe est la dernière, donc une ligne reprise
par une passe antérieure n'est jamais renvoyée), l'atomicité de l'unité de
césure, et le refus de ``decide.refer_for_review`` sur une ligne qui ne
porte pas de correction.
"""

from __future__ import annotations

import pytest

from saknussemm.core import decide
from saknussemm.core.identity import LineRef
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.schemas import (
    HyphenRole,
    LineManifest,
    LineStatus,
    ReviewPolicy,
)
from saknussemm.formats.loader import build_document_manifest

from tests._paths import EXAMPLES
from tests._pipeline_harness import DictProvider, RecordingObserver

_FIXTURE = "X0000002.xml"


def _run(
    corrections: dict[str, str],
    *,
    review_policy: ReviewPolicy | None = None,
):
    path = EXAMPLES / _FIXTURE
    doc = build_document_manifest([(path, _FIXTURE)])
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(corrections),
        api_key="k",
        model="m",
        observer=RecordingObserver(),
        **({} if review_policy is None else {"review_policy": review_policy}),
    )
    return doc, pipeline.run_sync(document_manifest=doc, source_files={_FIXTURE: path})


def _codes(reasons: tuple[str, ...]) -> set[str]:
    """``LineDecision`` carries raw ``"code: detail"`` strings; the report's
    ``DecisionStage`` carries them split. Both are on purpose — the split is
    the report's job — so a test that reads the decision splits here."""
    return {reason.split(":", 1)[0].strip() for reason in reasons}


def _first_changed_line(doc) -> LineManifest:
    """A line with enough text to carry a rule's evidence."""
    for page in doc.pages:
        for lm in page.lines:
            if len(lm.ocr_text) > 25 and lm.hyphen_role is HyphenRole.NONE:
                return lm
    raise AssertionError("fixture carries no ordinary line long enough")


def test_a_referred_line_still_carries_its_correction() -> None:
    """La propriété principale, et celle qu'un état « à relire » se fait
    voler en premier : la correction est LIVRÉE."""
    doc, _ = _run({})
    line = _first_changed_line(doc)
    proposal = f"{line.ocr_text} en 1789"

    _, result = _run({line.line_id: proposal})
    decision = result.decisions.by_ref[
        LineRef(page_id=line.page_id, line_id=line.line_id)
    ]
    assert decision.status is LineStatus.REVIEW_REQUIRED
    assert decision.final_text == proposal, (
        "une ligne renvoyée en revue a perdu sa correction : le renvoi est "
        "devenu un repli, ce qui est exactement ce que l'état existe pour "
        "ne pas être"
    )
    assert decision.carries_a_correction
    assert "digits_changed" in _codes(decision.review_reasons)


def test_a_referred_line_keeps_its_op_in_the_edit_script() -> None:
    """Le site qui aurait sauté le renvoi, tenu par une assertion.

    ``_build_final_edit_script`` demandait ``status is CORRECTED``. Avec
    une quatrième valeur, cette question cesse d'être « cette ligne
    porte-t-elle une correction ? », et un consommateur qui rejoue le
    script obtiendrait un fichier différent de celui que le même run a
    écrit.
    """
    doc, _ = _run({})
    line = _first_changed_line(doc)
    _, result = _run({line.line_id: f"{line.ocr_text} en 1789"})

    assert (
        result.decisions.by_ref[
            LineRef(page_id=line.page_id, line_id=line.line_id)
        ].status
        is LineStatus.REVIEW_REQUIRED
    )
    assert any(op.line_id == line.line_id for op in result.edit_script.ops), (
        "l'opération de la ligne renvoyée a disparu du script d'édition : "
        "rejouer le script ne reproduit plus le fichier livré"
    )


def test_referral_moves_no_byte() -> None:
    """Ce qui rend le défaut `enabled=True` défendable.

    Deux runs identiques, l'un avec les règles et l'autre sans : le
    fichier livré doit être le MÊME. Si un jour cette assertion tombe,
    ce n'est pas la comparaison qui a vieilli, c'est que la passe s'est
    mise à écrire du texte — et le défaut devrait alors être rediscuté,
    pas l'assertion relâchée.
    """
    doc, _ = _run({})
    line = _first_changed_line(doc)
    corrections = {line.line_id: f"{line.ocr_text} en 1789"}

    _, loud = _run(corrections)
    _, silent = _run(corrections, review_policy=ReviewPolicy.silent())

    assert loud.corrected_files == silent.corrected_files
    assert loud.corrected_files, "le run n'a rendu aucun fichier"
    assert [d.final_text for d in loud.decisions.decisions] == [
        d.final_text for d in silent.decisions.decisions
    ]


def test_silent_policy_leaves_every_line_corrected() -> None:
    """Le commutateur, et le fait qu'il ne déplace rien d'autre."""
    doc, _ = _run({})
    line = _first_changed_line(doc)
    _, result = _run(
        {line.line_id: f"{line.ocr_text} en 1789"},
        review_policy=ReviewPolicy.silent(),
    )
    assert result.review_lines == 0
    assert result.review_reasons == {}
    assert all(
        d.status is not LineStatus.REVIEW_REQUIRED for d in result.decisions.decisions
    )


def test_the_run_counters_agree_with_the_decisions() -> None:
    """Les agrégats de ``CorrectionResult`` sont lus sur le DecisionSet.

    Et ils ne se somment PAS l'un dans l'autre : une ligne peut porter
    plusieurs raisons, donc les compteurs par code totalisent au moins le
    nombre de lignes renvoyées, jamais moins.
    """
    doc, _ = _run({})
    line = _first_changed_line(doc)
    _, result = _run({line.line_id: f"{line.ocr_text} en 1789 chez Bcaumarchais"})

    assert result.review_lines == result.decisions.review_lines
    assert result.review_reasons == result.decisions.review_reason_counts()
    assert result.review_lines >= 1
    assert sum(result.review_reasons.values()) >= result.review_lines
    # Les deux familles sont disjointes : un statut par ligne.
    assert result.review_lines + result.fallback_lines <= len(
        result.decisions.decisions
    )


def test_a_hyphen_unit_is_referred_whole() -> None:
    """Une moitié de mot n'est pas relisable (ADR-010).

    La correction est portée par UN membre ; l'autre suit avec
    ``hyphen_unit_review`` sans avoir déclenché aucune règle lui-même.
    """
    doc, _ = _run({})
    part1 = next(
        (
            lm
            for page in doc.pages
            for lm in page.lines
            if lm.hyphen_role is HyphenRole.PART1 and lm.hyphen_pair_line_id
        ),
        None,
    )
    if part1 is None:  # pragma: no cover - the fixture carries pairs
        pytest.skip("fixture carries no hyphen pair")
    partner_id = part1.hyphen_pair_line_id

    _, result = _run({part1.line_id: f"1789 {part1.ocr_text}"})
    by_ref = result.decisions.by_ref
    flagged = by_ref[LineRef(page_id=part1.page_id, line_id=part1.line_id)]
    partner = by_ref[LineRef(page_id=part1.page_id, line_id=partner_id)]

    if flagged.status is not LineStatus.REVIEW_REQUIRED:
        pytest.skip("the pair reconciler refused this proposal before referral")
    assert partner.status is LineStatus.REVIEW_REQUIRED, (
        "un membre d'unité de césure est renvoyé et son partenaire ne "
        "l'est pas : le relecteur reçoit une moitié de mot"
    )
    assert _codes(partner.review_reasons) == {"hyphen_unit_review"}


def test_referral_refuses_a_line_that_carries_no_correction() -> None:
    """Un renvoi qualifie une CORRECTION. Sur une ligne repliée il n'y en
    a plus, et la poser ressusciterait une décision déjà défaite."""
    from saknussemm.core.schemas import Coords

    line = LineManifest(
        line_id="L1",
        page_id="P1",
        block_id="B1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=0, width=10, height=10),
        ocr_text="source",
        corrected_text="source",
    )
    line.status = LineStatus.FALLBACK
    with pytest.raises(RuntimeError, match="carries none"):
        decide.refer_for_review(line, reason="digits_changed")


def test_referral_accumulates_reasons_without_repeating_them() -> None:
    """Plusieurs règles peuvent voir la même ligne pour des causes
    indépendantes, et le relecteur a besoin de toutes."""
    doc, _ = _run({})
    line = _first_changed_line(doc)
    _, result = _run({line.line_id: f"{line.ocr_text} en 1789 chez Bcaumarchais"})
    decision = result.decisions.by_ref[
        LineRef(page_id=line.page_id, line_id=line.line_id)
    ]
    codes = [reason.split(":", 1)[0].strip() for reason in decision.review_reasons]
    assert len(codes) == len(set(codes)), f"raisons répétées : {codes}"
    assert {"digits_changed", "proper_noun_changed"} <= set(codes)
