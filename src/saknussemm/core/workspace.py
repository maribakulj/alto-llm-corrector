"""Les trois index qu'une page consulte, réunis en une valeur.

``line_by_id`` (les lignes de cette page, par id nu), ``cross_page_partners``
(les membres de césure qu'elle emprunte à d'autres pages, page-qualifiés) et
``traces`` (les enregistrements d'audit du run) voyagent ensemble et n'ont de
sens qu'ensemble : un appelant ne peut pas recevoir l'un sans les autres, ni
le workspace d'une autre page.

**Ce que ce type ne fait pas.** Il ne rend rien immuable : la dataclass est
gelée, mais les dicts qu'elle porte sont les index VIVANTS du run —
``core.decide`` écrit dans ``traces`` et les manifestes de ``line_by_id`` sont
l'état de travail muté.

**Ce n'est pas un sac.** Il porte des INDEX qu'une page lit, jamais ce qu'un
run accumule ; l'état du run est :class:`~saknussemm.core.context.RunContext`.
``tests/test_page_workspace_is_not_a_bag.py`` refuse un quatrième champ, donc
le prochain à vouloir en ajouter un doit faire l'argument à voix haute.

**Origine, et la décision de le garder.** Ce type est né d'une métrique :
`_descend_granularity` atteignait douze arguments et le plafond d'arité
demandait de descendre. L'audit du 2026-08-25 l'a relevé comme une abstraction
créée pour un compteur, et la vague `RS` a tranché de le GARDER — le retirer
rendrait ses douze arguments à une fonction qui n'en a pas besoin, pour un
gain qui serait de principe. Ce qui change plutôt, c'est le compteur : depuis
`RS-4.2`, inscrire une fonction longue ou large demande d'écrire pourquoi, ce
qui retire l'incitation à fabriquer un objet pour faire baisser un nombre.
"""

from __future__ import annotations

from dataclasses import dataclass

from saknussemm.core.identity import LineRef
from saknussemm.core.schemas import LineManifest, LineTrace


@dataclass(frozen=True)
class PageWorkspace:
    """The indices one page's correction reads, travelling together."""

    #: This page's lines, by bare ``line_id``. Page-scoped: bare ids are
    #: unique within a file, never document-wide (ADR-007), which is why
    #: the next field is keyed differently.
    line_by_id: dict[str, LineManifest]

    #: Hyphen members this page needs from OTHER pages, page-qualified
    #: (ADR-009). ``None`` when the page has no cross-page unit — the
    #: distinction between "none needed" and "an empty map" is what the
    #: lookup helpers read, so it is preserved rather than normalised.
    cross_page_partners: dict[LineRef, LineManifest] | None

    #: The run's per-line audit records, document-wide. ``None`` when the
    #: host opted out of tracing; every writer already no-ops on that.
    traces: dict[LineRef, LineTrace] | None


__all__ = ["PageWorkspace"]
