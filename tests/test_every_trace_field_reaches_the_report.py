"""Tout ce qu'une trace enregistre doit atteindre le rapport, ou être écarté
pour une raison écrite.

Le parcours d'une ligne est encodé quatre fois : `LineManifest` (l'état de
travail, muté), `LineTrace` (la piste d'audit, mutée), `LineDecision` (la
décision terminale, immuable) et `LineOutcome` avec ses trois étages (la
projection publique, versionnée). `decisions.build_line_outcomes` recopie la
troisième et la deuxième dans la quatrième, champ par champ, à la main.

**Rien ne vérifiait ce recopiage.** Un champ ajouté à `LineTrace` et oublié
dans le traducteur produit un rapport silencieusement incomplet : aucun type
ne s'y oppose, aucun test ne le voit, et le consommateur lit un rapport qui a
l'air entier. Le dépôt a déjà payé cette forme une fois —
``word_order_suspected`` a voyagé dans ``losses``, où sommer les compteurs
ajoutait un non-perte au total.

Ce module ne fusionne rien : la séparation muable/immuable est une propriété
acquise (`ADR-011`) et `LineOutcome` est une surface publique versionnée. Il
rend le recopiage **vérifiable**, ce qui est le remède proportionné.

La méthode est celle de ``test_public_surface_is_the_closure.py`` : recalculer
plutôt que lister. On lit dans l'AST du traducteur quels champs de la trace
il consulte réellement, et on exige que l'ensemble des champs de `LineTrace`
soit couvert par cette lecture, par une identité portée par le `LineRef`, ou
par une exclusion justifiée nommément.
"""

from __future__ import annotations

import ast
import inspect

from saknussemm.core.decisions import build_line_outcomes
from saknussemm.core.schemas import LineTrace

#: Champs que le traducteur ne lit PAS, et pourquoi chacun. Une exclusion
#: sans raison redevient un oubli au premier relecteur.
_NOT_PROJECTED: dict[str, str] = {
    "line_id": (
        "porté par le LineRef de la décision, pas par la trace — c'est "
        "l'autorité d'identité (ADR-001) et la trace n'en est qu'une copie"
    ),
    "page_id": "même raison que line_id",
    "source_ocr_text": (
        "le rapport prend `source_text` sur la DÉCISION. La trace en garde "
        "une copie pour l'audit ; s'il fallait choisir entre les deux, la "
        "décision est celle qui a été projetée dans le fichier"
    ),
    "projected_text": (
        "état de travail : la valeur qu'une passe a posée à un instant du "
        "run. La valeur TERMINALE est `DecisionStage.final_text`, et faire "
        "voyager les deux inviterait à les croire d'accord"
    ),
    "validation_status": (
        "même raison : le statut terminal est `DecisionStage.status`, lu sur "
        "le DecisionSet. La trace porte le statut provisoire du chunk, qui "
        "peut encore changer aux passes document-wide"
    ),
    "review_reasons": (
        "atteint le rapport, mais par la DÉCISION "
        "(`d.review_reasons` → `DecisionStage.review_reasons`), pour la "
        "même raison que `fallback_reason` juste en dessous : ce qui "
        "qualifie une décision est porté par le DecisionSet, qui est "
        "l'autorité, et pas par la trace, qui en garde une copie"
    ),
    "fallback_reason": (
        "atteint le rapport, mais par la DÉCISION (`d.fallback_reason` → "
        "`_structured_reason`), parce que la précédence d'attribution est "
        "une propriété du DecisionSet (ADR-013) et non de la trace"
    ),
}


def _fields_the_translator_reads() -> set[str]:
    """Les attributs de ``trace`` que ``build_line_outcomes`` consulte."""
    tree = ast.parse(inspect.getsource(build_line_outcomes))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "trace"
    }


def test_every_trace_field_is_projected_or_justified() -> None:
    """La clôture. Un champ ajouté à la trace doit être routé ou motivé."""
    declared = set(LineTrace.model_fields)
    read = _fields_the_translator_reads()
    unaccounted = declared - read - set(_NOT_PROJECTED)
    assert not unaccounted, (
        f"{sorted(unaccounted)} : ces champs de `LineTrace` n'atteignent "
        f"aucun étage de `LineOutcome` et ne figurent pas dans "
        f"`_NOT_PROJECTED`. Un champ enregistré mais jamais rapporté est du "
        f"travail d'audit que personne ne peut lire ; le router ou écrire "
        f"pourquoi il reste interne."
    )


def test_the_exclusion_list_names_only_real_fields() -> None:
    """Une exclusion pour un champ disparu masque un champ arrivé.

    Sans cette assertion, renommer un champ de la trace laisserait son
    ancienne exclusion en place et le nouveau nom serait couvert par… rien,
    tout en gardant la liste verte.
    """
    declared = set(LineTrace.model_fields)
    stale = sorted(set(_NOT_PROJECTED) - declared)
    assert not stale, (
        f"{stale} ne sont plus des champs de `LineTrace` : retirer leur "
        f"exclusion, sans quoi elle couvre un champ qui n'existe pas pendant "
        f"qu'un champ qui existe passe au travers."
    )


def test_the_exclusion_list_does_not_cover_a_field_the_translator_reads() -> None:
    """Le contrôle croisé : une exclusion et une lecture se contredisent.

    Si le traducteur se met à lire un champ déclaré « interne », c'est
    l'exclusion qui est périmée — et sa raison, écrite, est devenue fausse.
    """
    contradicted = sorted(_fields_the_translator_reads() & set(_NOT_PROJECTED))
    assert not contradicted, (
        f"{contradicted} sont lus par `build_line_outcomes` ET déclarés non "
        f"projetés. La raison écrite dans `_NOT_PROJECTED` ne décrit plus le "
        f"code."
    )


def test_the_scanner_can_still_see_a_field() -> None:
    """Un scan vide satisfait la clôture ci-dessus par le mauvais bout.

    Si ``_fields_the_translator_reads`` cessait de voir quoi que ce soit,
    ``unaccounted`` deviendrait « tout sauf les exclusions » et le premier
    test tomberait — mais il tomberait aussi si le traducteur était
    réellement vidé, et les deux causes ne se ressemblent pas au débogage.
    Celle-ci les sépare.
    """
    read = _fields_the_translator_reads()
    assert {
        "model_input_text",
        "model_corrected_text",
        "projection_fidelity",
    } <= read, (
        f"le scanner ne voit que {sorted(read)} ; il devrait voir au moins "
        f"les trois champs que les étages `proposal` et `projection` portent "
        f"de façon certaine"
    )
