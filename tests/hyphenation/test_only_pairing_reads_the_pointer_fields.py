"""Qui a le droit de lire un champ pointeur de césure, et combien de fois.

`CLAUDE.md` pose la règle : « Hyphen-partner resolution has exactly two
encodings and must keep exactly two » — les primitives dirigées de
`core/pairing.py` et la dérivation d'unité de `core/units.py`. Toute autre
lecture des quatre champs est une troisième réponse à la question « qui est
mon partenaire ? », et c'est la famille de défaut qui a coûté cinq résolveurs
parallèles.

**La règle était écrite et rien ne la vérifiait.** La garde qui existait,
``test_the_unit_projections_are_not_duplicates.py``, itère sur DEUX fonctions
nommées à la main. Elle passe, et pendant qu'elle passait,
``reconcile._build_hyphen_pairs`` rejouait la carte rôle→slot six lignes
durant et ``indexing._cross_page_partners`` lisait les quatre champs
directement. Une liste de deux noms ne dit rien du troisième.

Ce module remplace la liste par un recensement. Il ne se prononce pas sur la
qualité d'un site : il compte, par module, et refuse que le compte monte.

Deux catégories, parce qu'elles n'ont pas le même statut :

``lectures``
    résoudre un partenaire. C'est la dette. Zéro est la cible partout sauf
    dans les deux modules qui DÉTIENNENT la question.

``écritures``
    poser ou retirer un lien. Ce n'est pas de la résolution et ce n'est pas
    une dette : `pairing.link_hyphen_pairs` établit les liens au parse,
    `units.split_forward_link` en sectionne un quand le planificateur y est
    contraint. Comptées séparément pour qu'un travail sur les unes ne se
    cache pas derrière les autres — et parce que le refactor qui rendra
    l'unité autoritaire déplacera les écritures sans toucher aux lectures.

Sémantique du cliquet, celle de
``tests/decision/test_decision_write_exclusivity.py`` : une entrée peut
baisser, jamais monter ; un module absent de la table ne peut pas apparaître.

La distinction lecture/écriture est celle de ``tests/_ast_writes.py``, et
elle est load-bearing : ``pairs[lm.hyphen_pair_line_id] = lm.line_id`` porte
l'attribut à l'intérieur de la CIBLE sans rien lui écrire. Un recensement
naïf le compte comme une écriture et rate donc deux des six lectures de
``_build_hyphen_pairs`` — mesuré en écrivant ce fichier.
"""

from __future__ import annotations

import ast
from collections import Counter

from tests._ast_writes import written_attributes
from tests._paths import SRC

#: Les quatre champs qui portent un lien de césure sur un ``LineManifest``.
#: `hyphen_role` n'y est PAS : le rôle est lu partout légitimement (le
#: rewriter, le planificateur, le rapport), et ce qui fait un résolveur n'est
#: pas de connaître un rôle mais de le traduire en slot.
_POINTER_FIELDS = frozenset(
    {
        "hyphen_pair_line_id",
        "hyphen_pair_page_id",
        "hyphen_forward_pair_id",
        "hyphen_forward_pair_page_id",
    }
)

#: ``module → (lectures, écritures)``. Mesuré le 2026-08-25.
#:
#: ``core/pairing.py`` et ``core/units.py`` sont exemptés par CONSTRUCTION,
#: pas par tolérance : le premier détient la carte rôle→slot, le second la
#: dérivation d'unité, et ce sont les deux encodages que `CLAUDE.md` autorise.
#: Leurs chiffres sont quand même inscrits — un détenteur qui double ses
#: lectures est un détenteur qui s'est mis à répondre deux fois.
#:
#: ``core/schemas/manifest.py`` n'apparaît pas : la déclaration des champs
#: n'est ni une lecture ni une écriture au sens de l'AST.
_ACCESS: dict[str, tuple[int, int]] = {
    # -- les deux détenteurs ------------------------------------------------
    "core/pairing.py": (10, 10),
    "core/units.py": (4, 10),
    # -- la dette, et ce qu'elle vaut --------------------------------------
    # `_build_hyphen_pairs` rejoue la carte rôle→slot pour la carte de paires
    # que le validateur consulte. Elle est le sixième résolveur.
    "core/reconcile.py": (6, 0),
    # `_cross_page_partners` lit les deux slots au lieu de demander
    # `pair_ref`/`forward_ref`.
    "core/indexing.py": (4, 0),
}

#: Les modules dont le compte de LECTURES doit tomber à zéro. Le distinguer
#: des exemptions par construction est ce qui empêche la table de se lire
#: comme une liste d'autorisations.
_MUST_REACH_ZERO = frozenset({"core/reconcile.py", "core/indexing.py"})


def _census() -> dict[str, tuple[int, int]]:
    """``module → (lectures, écritures)`` sur tout ``src/saknussemm``."""
    reads: Counter[str] = Counter()
    writes: Counter[str] = Counter()
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _POINTER_FIELDS:
                reads[rel] += 1
            for name in written_attributes(node):
                if name in _POINTER_FIELDS:
                    writes[rel] += 1
    # Une écriture a d'abord été comptée comme occurrence : la retirer.
    return {
        rel: (reads[rel] - writes[rel], writes[rel])
        for rel in sorted(set(reads) | set(writes))
    }


def test_no_module_outside_the_table_touches_a_pointer_field() -> None:
    """La propriété principale : un septième site ne peut pas apparaître.

    C'est ce qu'une liste de deux fonctions nommées à la main ne pouvait pas
    dire, et c'est le seul énoncé qui vaut pour un refactor à venir.
    """
    measured = _census()
    unlisted = sorted(set(measured) - set(_ACCESS))
    assert not unlisted, (
        f"{unlisted} touche(nt) un champ pointeur de césure sans figurer dans "
        f"la table. Résoudre un partenaire se fait par `core/pairing.py` ou "
        f"`core/units.py` ; si ce site a une raison de ne pas pouvoir, il "
        f"faut l'écrire ici avec elle."
    )


def test_the_count_may_only_go_down() -> None:
    """Le cliquet. Une entrée peut baisser, jamais monter."""
    measured = _census()
    grown = {
        rel: (measured.get(rel, (0, 0)), pinned)
        for rel, pinned in _ACCESS.items()
        if measured.get(rel, (0, 0))[0] > pinned[0]
        or measured.get(rel, (0, 0))[1] > pinned[1]
    }
    assert not grown, (
        f"le nombre d'accès aux champs pointeurs a AUGMENTÉ : {grown} "
        f"(mesuré, épinglé). Une lecture de plus est une réponse de plus à "
        f"« qui est mon partenaire ? »."
    )


def test_an_entry_that_reached_its_target_leaves_the_table() -> None:
    """Sinon la table cesse de décrire la dette restante.

    Un module de ``_MUST_REACH_ZERO`` tombé à zéro lecture doit sortir des
    deux ensembles dans le même commit — c'est la règle « une entrée qui
    atteint sa cible s'en va » de ``test_orchestrator_budget.py``, appliquée
    ici.
    """
    measured = _census()
    finished = {
        rel
        for rel in _MUST_REACH_ZERO
        if measured.get(rel, (0, 0))[0] == 0 and rel in _ACCESS
    }
    assert not finished, (
        f"{sorted(finished)} ne lit plus aucun champ pointeur : retirer "
        f"l'entrée de `_ACCESS` et de `_MUST_REACH_ZERO`, et corriger la "
        f"docstring du module concerné, qui décrit encore la dette."
    )


def test_the_scanner_can_still_see_a_read() -> None:
    """Un scan vide est la bonne réponse ET ce que rend un scan cassé.

    Les trois assertions ci-dessus sont toutes satisfaites par un
    recensement qui ne trouve rien. Celle-ci est ce qui les rend
    interprétables : elle affirme que le compteur voit une lecture, une
    écriture, et la forme qui les distingue.
    """
    source = (
        "def f(lm, pairs, a, b):\n"
        "    x = lm.hyphen_pair_line_id\n"  # 1 lecture
        "    lm.hyphen_forward_pair_id = None\n"  # 1 écriture
        "    pairs[lm.hyphen_pair_page_id] = 1\n"  # 1 lecture, DANS une cible
        "    lm.hyphen_pair_line_id, lm.hyphen_pair_page_id = a, b\n"  # 2 écritures
        "    return x\n"
    )
    tree = ast.parse(source)
    reads = sum(
        1
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr in _POINTER_FIELDS
    )
    writes = sum(
        1
        for n in ast.walk(tree)
        for name in written_attributes(n)
        if name in _POINTER_FIELDS
    )
    assert (reads - writes, writes) == (2, 3), (
        "le recensement ne distingue plus une lecture d'une écriture, ne voit "
        "plus un attribut situé dans le SLICE d'une cible — la forme exacte "
        "que `_build_hyphen_pairs` emploie deux fois — ou ne voit plus une "
        "affectation par dépaquetage, qui est précisément la forme pour "
        "laquelle `tests/_ast_writes.py` existe"
    )
