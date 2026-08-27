"""Le vocabulaire des renvois en revue est clos, et il l'est dès l'écriture.

`docs/la-vie-d-une-ligne.md` promet deux listes closes à un lecteur :
les raisons de repli, et — depuis l'état ``review_required`` — les raisons
de renvoi. ``core.decide.REVIEW_REASON_CODES`` ferme la seconde pour un
programme, et ce module vérifie les deux directions plus la documentation,
comme ``test_the_fallback_reasons_are_a_closed_set.py`` le fait pour la
première.

**Ce qui change de méthode, et pourquoi.** Le module jumeau scanne l'AST
sur six formes syntaxiques parce que ses vingt littéraux sont dispersés sur
huit modules : il n'a pas le choix. Ici les codes ont un seul domicile,
``core/review.py``, alors la clôture est vérifiée dans l'autre sens et bien
plus fort — **en exerçant les règles**. Chaque code déclaré doit sortir
d'un appel réel à ``find_review_referrals``, et rien d'autre ne doit en
sortir. Un scan dit « ce littéral existe » ; un exercice dit « cette règle
rend ce code », ce qui est la propriété qu'un consommateur lit.

Deux trous que l'exercice seul laisserait, et les deux assertions qui les
bouchent :

- une règle NEUVE dont le code n'est pas déclaré ne serait jamais
  exercée par ce fichier et passerait donc inaperçue → un scan des
  littéraux de ``core/review.py`` refuse tout code non déclaré, quelle que
  soit la règle qui le porte ;
- ``hyphen_unit_review`` n'est pas rendu par ``find_review_referrals`` du
  tout : c'est la passe de ``core/acceptance.py`` qui l'appose en tirant
  l'unité de césure. Il est donc exempté nommément de l'exercice, et
  ``tests/test_review_pass.py`` est ce qui le produit pour de bon.
"""

from __future__ import annotations

import ast
import re

from saknussemm.core.decide import REVIEW_REASON_CODES
from saknussemm.core.identity import LineRef
from saknussemm.core.review import find_review_referrals
from saknussemm.core.schemas import ReviewPolicy

from tests._paths import PKG, SRC

#: La forme d'un code : minuscules, chiffres, soulignés, au moins deux
#: segments. Le second segment écarte les mots isolés — le répertoire de
#: négations de ``core/review.py`` en contient trente et un.
_CODE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")

#: Émis ailleurs que par les règles, avec où. Une exemption sans adresse
#: redevient un oubli au premier relecteur.
_EMITTED_ELSEWHERE = {
    "hyphen_unit_review": (
        "apposé par `acceptance._review_pass` sur les membres d'une unité "
        "de césure tirés par un membre renvoyé (ADR-010) ; ce n'est pas "
        "une règle, c'est une conséquence"
    ),
}


def _referrals(cases: list[tuple[str, str]]) -> dict[LineRef, tuple[str, ...]]:
    lines = [
        (LineRef(page_id="P1", line_id=f"L{i}"), source, final)
        for i, (source, final) in enumerate(cases)
    ]
    return find_review_referrals(lines, policy=ReviewPolicy())


#: Un cas par règle, écrit pour la déclencher SEULE autant que possible.
#: Le cas systématique demande trois occurrences — c'est le défaut de
#: ``min_systematic_occurrences``, et le fait qu'il faille trois lignes
#: pour l'obtenir est la propriété même de la règle.
_ONE_CASE_PER_RULE: dict[str, list[tuple[str, str]]] = {
    "digits_changed": [("en l'an 1789 dit-il", "en l'an 1780 dit-il")],
    "negation_changed": [("il ne vient pas ici", "il vient ici")],
    "proper_noun_changed": [("chez Bcaumarchais", "chez Beaumarchais")],
    "systematic_removal": [
        ("premier⸗ mot", "premier mot"),
        ("second⸗ mot", "second mot"),
        ("troisieme⸗ mot", "troisieme mot"),
    ],
    "systematic_substitution": [
        ("l’un", "l'un"),
        ("d’eux", "d'eux"),
        ("qu’il", "qu'il"),
    ],
}


def _codes_the_rules_emit() -> set[str]:
    emitted: set[str] = set()
    for cases in _ONE_CASE_PER_RULE.values():
        for reasons in _referrals(cases).values():
            emitted |= {reason.split(":", 1)[0].strip() for reason in reasons}
    return emitted


def test_no_rule_emits_a_code_outside_the_declared_set() -> None:
    """La direction qui compte : un septième code est refusé."""
    stray = sorted(_codes_the_rules_emit() - REVIEW_REASON_CODES)
    assert not stray, (
        f"{stray} : ces codes de renvoi n'existent pas dans "
        f"`core.decide.REVIEW_REASON_CODES`. Un consommateur agrège sur ce "
        f"code ; en ajouter un étend le vocabulaire que lit son tableau de "
        f"bord, ce n'est pas un littéral de plus."
    )


def test_every_declared_code_is_produced_by_a_real_call() -> None:
    """L'autre direction, et elle est plus forte qu'un scan de littéraux.

    Un code déclaré que rien ne rend fait promettre au vocabulaire une
    raison qu'un consommateur n'obtiendra jamais. Ici la preuve est un
    appel : la règle a tourné sur une entrée et a rendu ce code-là.
    """
    unproduced = sorted(
        REVIEW_REASON_CODES - _codes_the_rules_emit() - set(_EMITTED_ELSEWHERE)
    )
    assert not unproduced, (
        f"{unproduced} sont déclarés et jamais produits : soit la règle qui "
        f"les rendait a disparu, soit le cas de `_ONE_CASE_PER_RULE` ne la "
        f"déclenche plus. Retirer le code, corriger le cas, ou nommer "
        f"l'exemption comme `hyphen_unit_review` l'est."
    )


def test_each_case_triggers_the_rule_it_was_written_for() -> None:
    """Sans quoi le test ci-dessus se satisfait d'un cas qui déclenche
    autre chose. C'est le point faible d'un exercice, et il se boucle en
    exigeant que CHAQUE cas rende SON code."""
    for code, cases in _ONE_CASE_PER_RULE.items():
        produced = {
            reason.split(":", 1)[0].strip()
            for reasons in _referrals(cases).values()
            for reason in reasons
        }
        assert code in produced, (
            f"le cas écrit pour `{code}` rend {sorted(produced)} : la règle "
            f"ne le reconnaît plus, ou le cas a cessé de la déclencher"
        )


def test_no_undeclared_code_hides_in_the_rules_module() -> None:
    """Le filet de l'exercice : une règle neuve non exercée ici.

    ``find_review_referrals`` ne peut rendre que des codes littéraux de
    ``core/review.py``. Les recenser tous et exiger qu'ils soient déclarés
    attrape la règle que personne n'a pensé à exercer — ce que
    ``_codes_the_rules_emit`` ne peut structurellement pas faire.
    """
    tree = ast.parse((SRC / "core" / "review.py").read_text(encoding="utf-8"))
    # Les noms que le module DÉFINIT ont la forme d'un code sans en être
    # un — `find_review_referrals` figure dans son propre `__all__`.
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _CODE.match(node.value)
    }
    stray = sorted(literals - REVIEW_REASON_CODES - defined)
    assert not stray, (
        f"{stray} ont la forme d'un code de renvoi, vivent dans "
        f"`core/review.py` et ne sont pas déclarés. Soit c'est une règle "
        f"neuve — l'inscrire dans `REVIEW_REASON_CODES`, dans "
        f"`_ONE_CASE_PER_RULE` et dans `docs/la-vie-d-une-ligne.md` — soit "
        f"c'est un littéral qui ressemble à un code par accident, et il "
        f"vaut mieux le renommer."
    )


def test_the_documented_list_is_the_declared_list() -> None:
    """`docs/la-vie-d-une-ligne.md` promet une liste CLOSE.

    Une documentation qui dit « la liste est close » et qui en oublie un
    est pire qu'une documentation muette, parce qu'on la croit.
    """
    doc = (PKG / "docs" / "la-vie-d-une-ligne.md").read_text(encoding="utf-8")
    missing = sorted(code for code in REVIEW_REASON_CODES if code not in doc)
    assert not missing, (
        f"{missing} ne sont pas documentés dans `docs/la-vie-d-une-ligne.md`, "
        f"qui promet pourtant une liste close. Un consommateur qui lit ce "
        f"code dans son rapport n'a nulle part où chercher ce qu'il veut dire."
    )


def test_the_two_vocabularies_do_not_overlap() -> None:
    """Un code présent des deux côtés serait ambigu dans un rapport.

    ``fallback_reasons`` et ``review_reasons`` sont deux agrégats
    distincts sur ``CorrectionResult``, et un même code dans les deux
    obligerait un lecteur à savoir lequel il regarde pour savoir ce que le
    code veut dire. Les paires voisines sont volontairement nommées
    différemment : ``hyphen_unit_fallback`` contre ``hyphen_unit_review``.
    """
    from saknussemm.core.decide import FALLBACK_REASON_CODES

    shared = sorted(FALLBACK_REASON_CODES & REVIEW_REASON_CODES)
    assert not shared, (
        f"{shared} appartiennent aux deux vocabulaires. Un repli et un "
        f"renvoi disent des choses opposées sur une ligne — l'un a retiré "
        f"la correction, l'autre l'a gardée — et un code commun rend le "
        f"rapport indéchiffrable sans contexte."
    )
