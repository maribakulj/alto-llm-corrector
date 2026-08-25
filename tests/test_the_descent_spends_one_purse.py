"""La descente de granularité dépense une seule bourse.

`core/driver.py` porte la boucle interne du moteur — planifier, router,
appeler, réessayer, descendre d'un cran quand réessayer à ce grain-là est
sans espoir — et **aucun fichier de test ne le nommait**. Ses propriétés
n'étaient exercées qu'en bout de chaîne, par `test_downgrade.py`, qui vérifie
qu'une descente a lieu et qu'elle récupère : deux choses vraies d'une
descente qui coûterait dix fois trop cher.

Ce qui manquait est la propriété qui donne son sens au mécanisme. Un chunk
qui échoue est replanifié un grain plus fin, et chaque sous-chunk peut à son
tour échouer et descendre : sans bourse commune, une PAGE de 500 lignes qui
part en LIGNE produit 500 × `max_attempts` appels au producteur, facturés.
`ChunkBudget` est ce qui l'interdit, et son unique garantie est que le
sous-chunk dépense de la MÊME bourse que le chunk qui l'a engendré.

Trois assertions, trois chemins :

1. la bourse borne le coût de toute la descente, quelle que soit sa
   profondeur ;
2. bourse épuisée en cours de descente, les sous-chunks restants tombent sur
   la source — ils n'empruntent pas ;
3. un refus permanent du fournisseur ne descend pas et ne se replie pas : il
   fait échouer le run, parce que le replier ferait terminer le run « en
   succès » avec du texte silencieusement non corrigé (ADR-008).

Le compteur observable est `result.producer_calls`, qui compte chaque
invocation de `produce`, retries inclus.

**Sensibilité mesurée**, sur les 8 assertions du module :

  ===============================================  =========
  mutation                                         tombent
  ===============================================  =========
  le sous-chunk ouvre une bourse neuve                 2
  la dépense n'est plus débitée de la bourse           5
  un refus permanent est absorbé comme les autres      1
  le garde ``budget.exhausted`` mi-descente sauté      0
  ===============================================  =========

La dernière est un mutant **équivalent**, et c'est un constat sur le code
plutôt que sur le test : quand la bourse est vide,
``ChunkBudget.attempts_allowed`` rend déjà 0, donc la boucle d'essais ne
tourne pas et le chunk se replie de toute façon. Le garde explicite ne change
que le DÉTAIL du message (« per_chunk_budget exhausted » au lieu de la
dernière erreur), pas la décision ni le coût. Noté ici pour qu'il ne soit ni
repris pour un trou de test, ni retiré sans qu'on sache ce qu'on perd.
"""

from __future__ import annotations

from typing import Any

import pytest

from saknussemm.core.editing import EditScript
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.protocols import (
    ProducerOptions,
    ProviderPermanentError,
)
from saknussemm.core.schemas import (
    ChunkPlannerConfig,
    CorrectionRequest,
    RetryPolicy,
    Usage,
)
from saknussemm.formats.alto.parser import build_document_manifest

from tests._paths import EXAMPLES

_SAMPLE = EXAMPLES / "sample.xml"


class _AlwaysMalformed:
    """Un producteur qui répond toujours hors contrat.

    ``ValueError`` est la famille « sortie malformée » de l'ADR-008 : elle
    est réessayable, donc elle mène à la descente — c'est le seul chemin qui
    exerce la bourse.
    """

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self) -> None:
        self.calls = 0

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        self.calls += 1
        raise ValueError("mock: malformed producer output")


class _PermanentlyRefusing:
    """Un fournisseur qui rejette la requête pour de bon (identifiants,
    modèle inconnu). Réessayer est sans objet et se replier serait mentir."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self) -> None:
        self.calls = 0

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]:
        self.calls += 1
        raise ProviderPermanentError("mock: model rejected", status_code=401)


class _Silent:
    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        pass


def _pipeline(producer: Any, *, budget: int, attempts: int = 3) -> CorrectionPipeline:
    return CorrectionPipeline(
        producer=producer,
        observer=_Silent(),
        # Un grain de départ volontairement grossier et des fenêtres
        # minuscules : la descente PAGE → BLOCK → WINDOW → LIGNE a de quoi
        # produire beaucoup de sous-chunks, ce qui est exactement la
        # situation que la bourse existe pour borner.
        config=ChunkPlannerConfig(
            max_input_chars_per_request=10_000,
            max_lines_per_request=64,
            line_window_size=2,
            line_window_overlap=1,
        ),
        retry_policy=RetryPolicy(
            max_attempts=attempts,
            temperatures=(0.0,),
            transient_backoff_base=0.0,
            output_backoff_base=0.0,
            per_chunk_budget=budget,
        ),
    )


async def _run(producer: Any, *, budget: int, attempts: int = 3) -> Any:
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    return await _pipeline(producer, budget=budget, attempts=attempts).run(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [1, 2, 3, 6, 12])
async def test_a_descent_never_spends_more_than_its_purse(budget: int) -> None:
    """La propriété centrale, sur cinq bourses.

    Le document de test tient en deux pages, donc deux chunks de premier
    niveau, donc au plus ``2 × budget`` appels — quelle que soit la
    profondeur que la descente atteint. Sans bourse partagée, chaque
    sous-chunk rouvrirait ``max_attempts`` et le compte exploserait avec le
    nombre de lignes.
    """
    producer = _AlwaysMalformed()
    result = await _run(producer, budget=budget)
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    top_level_chunks = len(doc.pages)

    assert producer.calls == result.producer_calls, (
        "le rapport ne compte pas les mêmes appels que le producteur en a "
        "reçu ; `producer_calls` est le compteur de coût de la bibliothèque"
    )
    assert result.producer_calls <= top_level_chunks * budget, (
        f"bourse {budget} : {result.producer_calls} appels pour "
        f"{top_level_chunks} chunks de premier niveau. Un sous-chunk dépense "
        f"de la MÊME bourse que le chunk qui l'a engendré ; au-delà, il en a "
        f"ouvert une nouvelle et la descente multiplie le coût par sa "
        f"profondeur."
    )


@pytest.mark.asyncio
async def test_a_bigger_purse_buys_more_attempts_and_a_smaller_one_fewer() -> None:
    """Le contrôle positif, sans lequel la borne ci-dessus serait tenue par
    une bourse qui n'achète rien.

    Une assertion « ≤ » est satisfaite par zéro appel. Celle-ci dit que le
    plafond est bien celui qui mord : doubler la bourse augmente
    effectivement le nombre d'essais consentis.
    """
    small = await _run(_AlwaysMalformed(), budget=2)
    large = await _run(_AlwaysMalformed(), budget=12)
    assert small.producer_calls > 0
    assert large.producer_calls > small.producer_calls, (
        f"bourse 2 → {small.producer_calls} appels, bourse 12 → "
        f"{large.producer_calls}. La bourse ne gouverne plus rien."
    )


@pytest.mark.asyncio
async def test_an_exhausted_purse_falls_back_instead_of_borrowing() -> None:
    """Bourse épuisée, tout le monde revient à la source — et le dit.

    Le repli n'est pas silencieux : chaque ligne porte
    ``all_attempts_exhausted``, qui est la raison que
    `docs/la-vie-d-une-ligne.md` documente pour ce chemin.
    """
    result = await _run(_AlwaysMalformed(), budget=1)
    assert result.fallback_lines == len(result.decisions.decisions)
    assert all(d.final_text == d.source_text for d in result.decisions.decisions), (
        "une ligne a gardé une correction qu'aucun essai n'a produite"
    )
    codes = set(result.fallback_reasons)
    assert codes == {"all_attempts_exhausted"}, (
        f"raisons de repli {codes} ; la bourse épuisée doit produire "
        f"`all_attempts_exhausted` et rien d'autre"
    )


@pytest.mark.asyncio
async def test_a_permanent_refusal_fails_the_run_without_descending() -> None:
    """ADR-008 : un 4xx toucherait chaque sous-chunk à l'identique.

    Le convertir en replis par chunk ferait terminer le run EN SUCCÈS avec du
    texte silencieusement non corrigé. Il doit donc remonter — et sans avoir
    dépensé une descente pour l'apprendre.
    """
    producer = _PermanentlyRefusing()
    with pytest.raises(ProviderPermanentError):
        await _run(producer, budget=12)
    assert producer.calls == 1, (
        f"{producer.calls} appels avant de renoncer : un refus permanent ne "
        f"se réessaie pas et ne descend pas d'un grain"
    )
