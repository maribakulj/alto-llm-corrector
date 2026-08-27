"""Les deux dernières lectures de champs pointeurs, comparées aux primitives.

`core/pairing.py` détient la carte rôle→slot : `PART1` continue par le slot
PAIR, `BOTH` par le slot FORWARD, `PART2` et `NONE` ne continuent nulle part.
Deux fonctions la rejouent à la main au lieu de la lui demander :

* ``reconcile._build_hyphen_pairs`` — la carte bidirectionnelle que le
  VALIDATEUR consulte pour vérifier qu'une proposition n'a pas fusionné une
  paire ;
* ``indexing._cross_page_partners`` — les manifestes qu'une page doit
  emprunter aux autres pour résoudre une unité à cheval.

Ce module est le contrôle qui rend leur réécriture sûre : il affirme que les
deux répondent **exactement** ce que les primitives répondent. Il passe avant
la réécriture — les deux dérivations sont d'accord aujourd'hui — et c'est
précisément ce qui en fait une preuve après.

**Pourquoi il fallait l'écrire.** Aucun fichier de test ne nommait ces deux
fonctions, et le filet d'octets ne les voit pas : neutralisées, elles ne font
tomber aucune des 64 empreintes de
``tests/test_byte_parity_all_fixtures.py`` (mesuré). La raison est
instructive et vaut d'être retenue plutôt que le chiffre :

* ``_build_hyphen_pairs`` alimente une GARDE, pas une transformation. Une
  garde retirée ne change les octets que le jour où un producteur propose ce
  qu'elle interdit.
* ``_cross_page_partners`` ne rend quelque chose que sur une unité à cheval
  sur deux pages, et les quinze fixtures du dépôt sont chargées un fichier à
  la fois.

Un défaut sur l'une des deux serait donc invisible à toute la suite jusqu'au
jour où il coûte un mot coupé dans un fichier livré.
"""

from __future__ import annotations

import pytest

from saknussemm.core.indexing import _cross_page_partners
from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.pairing import forward_partner_id, forward_ref, pair_ref
from saknussemm.core.reconcile import _build_hyphen_pairs
from saknussemm.core.schemas import (
    BlockManifest,
    HyphenRole,
    LineManifest,
    PageManifest,
)

from tests.hyphenation._lines import _line


# ---------------------------------------------------------------------------
# Les dérivations de référence — les primitives, et rien d'autre
# ---------------------------------------------------------------------------


def _pairs_via_primitives(lines: list[LineManifest]) -> dict[str, str]:
    """Ce que ``_build_hyphen_pairs`` doit rendre, dérivé des primitives.

    Même forme de sortie : bidirectionnelle, clés en ``line_id`` NU. Le
    caractère nu de la clé est contraire à `ADR-001` et sûr uniquement parce
    que les chunks sont page-scopés ; la forme est reproduite ici telle
    quelle, parce que ce module compare deux dérivations et ne change pas le
    contrat du validateur.
    """
    pairs: dict[str, str] = {}
    for lm in lines:
        partner = forward_partner_id(lm)
        if partner is None:
            continue
        pairs[lm.line_id] = partner
        pairs[partner] = lm.line_id
    return pairs


def _cross_page_via_primitives(
    page: PageManifest, lines: dict[LineRef, LineManifest]
) -> dict[LineRef, LineManifest] | None:
    """Ce que ``_cross_page_partners`` doit rendre, dérivé des primitives.

    Les deux slots, dans les deux sens : une page peut porter l'un ou l'autre
    bout d'une unité qui enjambe une coupure. ``pair_ref``/``forward_ref``
    qualifient un pointeur sans ``page_id`` par la page de la ligne qui le
    porte, ce que la version manuelle exprime en exigeant un ``page_id``
    non vide — les deux se rejoignent puisque la boucle écarte ensuite les
    partenaires de cette page-ci, et c'est cette équivalence que le test
    ci-dessous vérifie plutôt que de la raisonner.
    """
    partners: dict[LineRef, LineManifest] = {}
    for lm in page.lines:
        for ref in (pair_ref(lm), forward_ref(lm)):
            if ref is None or ref.page_id == page.page_id:
                continue
            partner = lines.get(ref)
            if partner is not None:
                partners[ref] = partner
    return partners or None


# ---------------------------------------------------------------------------
# Les documents — un par forme que les pointeurs peuvent prendre
# ---------------------------------------------------------------------------


def _link(tail: LineManifest, head: LineManifest, *, forward: bool = False) -> None:
    """Poser un lien dirigé tail → head, dans le slot que le rôle impose."""
    if forward:
        tail.hyphen_forward_pair_id = head.line_id
        tail.hyphen_forward_pair_page_id = head.page_id
    else:
        tail.hyphen_pair_line_id = head.line_id
        tail.hyphen_pair_page_id = head.page_id
    if head.hyphen_role in (HyphenRole.PART2, HyphenRole.BOTH):
        head.hyphen_pair_line_id = tail.line_id
        head.hyphen_pair_page_id = tail.page_id


def _simple_pair() -> list[LineManifest]:
    """`PART1` → `PART2`, la forme de loin la plus fréquente."""
    a = _line("A", "plu-", role=HyphenRole.PART1)
    b = _line("B", "sieurs et le reste", role=HyphenRole.PART2)
    _link(a, b)
    return [a, b]


def _chain() -> list[LineManifest]:
    """`PART1` → `BOTH` → `PART2` : la seule forme où les DEUX slots d'une
    même ligne portent un lien, et donc la seule où intervertir la carte
    rôle→slot produit une carte différente au lieu d'une carte vide."""
    a = _line("A", "com-", role=HyphenRole.PART1)
    b = _line("B", "men-", role=HyphenRole.BOTH)
    c = _line("C", "cement du livre", role=HyphenRole.PART2)
    _link(a, b)
    _link(b, c, forward=True)
    return [a, b, c]


def _no_hyphen() -> list[LineManifest]:
    return [_line("A", "une ligne ordinaire"), _line("B", "une autre")]


def _dangling() -> list[LineManifest]:
    """Une ligne qui annonce une coupure vers un partenaire absent."""
    a = _line("A", "orphe-", role=HyphenRole.PART1)
    a.hyphen_pair_line_id = "ABSENT"
    return [a]


def _unqualified_pointer() -> list[LineManifest]:
    """Un pointeur intra-page sans ``page_id``.

    C'est la seule différence de forme entre les deux dérivations de
    ``_cross_page_partners`` : la version manuelle exige un ``page_id``
    non vide, les primitives le remplacent par celui de la ligne porteuse.
    Sans ce cas, l'équivalence serait affirmée sans être exercée.
    """
    a = _line("A", "plu-", role=HyphenRole.PART1)
    b = _line("B", "sieurs", role=HyphenRole.PART2)
    a.hyphen_pair_line_id = "B"
    a.hyphen_pair_page_id = None
    b.hyphen_pair_line_id = "A"
    b.hyphen_pair_page_id = None
    return [a, b]


_SHAPES = {
    "simple_pair": _simple_pair,
    "chain_part1_both_part2": _chain,
    "no_hyphen": _no_hyphen,
    "dangling": _dangling,
    "unqualified_pointer": _unqualified_pointer,
}


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_the_pair_map_is_what_the_primitives_say(shape: str) -> None:
    lines = _SHAPES[shape]()
    assert _build_hyphen_pairs(lines) == _pairs_via_primitives(lines), (
        f"{shape} : la carte de paires du validateur n'est plus celle que "
        f"`pairing.forward_partner_id` dérive. Les deux doivent répondre la "
        f"même chose ou le validateur garde une autre unité que le reste du "
        f"moteur."
    )


def test_the_chain_is_where_a_swapped_slot_map_would_show() -> None:
    """Le contrôle négatif : sans lui, l'égalité ci-dessus serait tenue par
    deux dérivations également fausses.

    Sur une chaîne, `BOTH` continue par son slot FORWARD. Une carte qui
    lirait le slot PAIR répondrait ``B → A`` au lieu de ``B → C`` — donc ce
    test échoue si la carte rôle→slot est inversée quelque part, ce que
    l'égalité seule ne garantit pas.
    """
    pairs = _build_hyphen_pairs(_chain())
    assert pairs["A"] == "B"
    assert pairs["B"] == "C", (
        "un BOTH continue par son slot FORWARD ; lire son slot PAIR le "
        "renvoie vers la ligne qui le PRÉCÈDE"
    )
    assert pairs["C"] == "B"


# ---------------------------------------------------------------------------
# Les partenaires inter-pages
# ---------------------------------------------------------------------------


def _two_page_document(
    *, forward_slot: bool = False, qualify: bool = True
) -> tuple[PageManifest, PageManifest, dict[LineRef, LineManifest]]:
    """Un mot coupé entre la fin de p1 et le début de p2."""
    tail_role = HyphenRole.BOTH if forward_slot else HyphenRole.PART1
    tail = _line("TL9", "conti-", page_id="p1", role=tail_role)
    head = _line("TL1", "nuation", page_id="p2", role=HyphenRole.PART2)
    if forward_slot:
        tail.hyphen_forward_pair_id = "TL1"
        tail.hyphen_forward_pair_page_id = "p2" if qualify else None
    else:
        tail.hyphen_pair_line_id = "TL1"
        tail.hyphen_pair_page_id = "p2" if qualify else None
    head.hyphen_pair_line_id = "TL9"
    head.hyphen_pair_page_id = "p1" if qualify else None

    def _page(pid: str, lm: LineManifest) -> PageManifest:
        return PageManifest(
            page_id=pid,
            source_file=f"{pid}.xml",
            page_index=0 if pid == "p1" else 1,
            page_width=1000,
            page_height=1000,
            blocks=[
                BlockManifest(
                    block_id="b1",
                    page_id=pid,
                    block_order=0,
                    coords=lm.coords,
                    line_ids=[lm.line_id],
                )
            ],
            lines=[lm],
        )

    p1, p2 = _page("p1", tail), _page("p2", head)
    index = {line_ref(lm): lm for page in (p1, p2) for lm in page.lines}
    return p1, p2, index


@pytest.mark.parametrize("forward_slot", [False, True])
def test_cross_page_partners_are_what_the_primitives_say(forward_slot: bool) -> None:
    """Les deux sens, et les deux slots : la page qui porte la queue doit
    voir la tête, et la page qui porte la tête doit voir la queue."""
    p1, p2, index = _two_page_document(forward_slot=forward_slot)
    for page in (p1, p2):
        assert _cross_page_partners(page, index) == _cross_page_via_primitives(
            page, index
        ), f"page {page.page_id}, slot {'forward' if forward_slot else 'pair'}"


def test_a_cross_page_partner_is_actually_found() -> None:
    """Le contrôle positif. Sans lui, l'égalité ci-dessus serait tenue par
    deux fonctions qui rendent ``None`` — ce qui est exactement l'état que la
    mutation de sensibilité a produit sans faire tomber une seule empreinte
    d'octets.
    """
    p1, p2, index = _two_page_document()
    from_tail = _cross_page_partners(p1, index)
    assert from_tail is not None and list(from_tail) == [
        LineRef(page_id="p2", line_id="TL1")
    ]
    from_head = _cross_page_partners(p2, index)
    assert from_head is not None and list(from_head) == [
        LineRef(page_id="p1", line_id="TL9")
    ]


def test_an_unqualified_cross_page_pointer_finds_nothing_either_way() -> None:
    """Un pointeur inter-pages sans ``page_id`` ne désigne personne.

    Les deux dérivations s'y prennent autrement — la version manuelle écarte
    le pointeur parce que sa page est vide, les primitives le qualifient par
    la page de la ligne porteuse et l'écartent ensuite comme local — et
    doivent arriver au même endroit. C'est la seule différence de FORME entre
    les deux, donc le seul endroit où la réécriture pourrait changer quelque
    chose sans que rien ne le dise.

    Mesuré : retirer le test ``not partner_page`` de ``_cross_page_partners``
    ne fait tomber aucune assertion de ce module, et c'est correct — le
    ``LineRef`` non qualifié ne résout dans aucun index, donc le mutant est
    équivalent. Le noter ici évite de le reprendre pour un trou.
    """
    p1, p2, index = _two_page_document(qualify=False)
    for page in (p1, p2):
        assert _cross_page_partners(page, index) is None
        assert _cross_page_via_primitives(page, index) is None


def test_a_page_whose_units_are_all_local_returns_none() -> None:
    """``None`` et ``{}`` disent deux choses différentes, et les helpers
    d'aval lisent la distinction : « rien à emprunter » n'est pas « une carte
    vide qu'il faut quand même faire voyager »."""
    lines = _simple_pair()
    page = PageManifest(
        page_id="p1",
        source_file="p1.xml",
        page_index=0,
        page_width=1000,
        page_height=1000,
        blocks=[
            BlockManifest(
                block_id="b1",
                page_id="p1",
                block_order=0,
                coords=lines[0].coords,
                line_ids=[lm.line_id for lm in lines],
            )
        ],
        lines=lines,
    )
    index = {line_ref(lm): lm for lm in lines}
    assert _cross_page_partners(page, index) is None
    assert _cross_page_via_primitives(page, index) is None
