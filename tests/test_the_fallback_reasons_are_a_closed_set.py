"""Le vocabulaire des raisons de repli est clos, et il faut le prouver.

Un repli est ce qu'un consommateur lit en premier quand une ligne n'a pas été
corrigée. `CorrectionResult.fallback_reasons` l'agrège par code — le préfixe
avant le ``:`` — donc un tableau de bord affiche ces codes, et un code
inconnu y est un défaut de la bibliothèque plutôt qu'une raison inédite.

L'ensemble était **ouvert** : vingt littéraux dispersés sur huit modules, et
rien ne disait combien il y en avait. La liste de ce module a été
reconstituée par `grep` à l'audit du 2026-08-25, ce qui est exactement le
genre de connaissance qui se perd.

`core.decide.FALLBACK_REASON_CODES` la ferme ; ce module vérifie les deux
directions et la documentation avec.

**Pourquoi statiquement plutôt qu'à l'exécution.** Une validation dans
``decide.fall_back`` serait plus courte et refuserait un code inconnu partout.
Elle refuserait aussi ``tests/decision/test_fallback_reason_precedence.py``,
qui passe des raisons synthétiques (« second_reason », « pulled_by_unit »)
pour exercer la PRÉCÉDENCE et non le vocabulaire — et un test qui n'a pas le
droit d'inventer une raison ne peut plus tester ce mécanisme-là.

**La limite, dite plutôt que tue.** Le scan lit six formes syntaxiques,
listées ci-dessous et closes à la main. Une raison construite autrement — un
code assemblé à l'exécution, une constante importée d'ailleurs — lui
échapperait. Ce sont les quatre formes que le paquet emploie aujourd'hui, et
la cinquième devra être ajoutée ici.
"""

from __future__ import annotations

import ast
import re

from saknussemm.core.decide import FALLBACK_REASON_CODES

from tests._paths import PKG, SRC

#: Un code : minuscules et soulignés. La forme ne sert qu'à écarter les
#: chaînes ordinaires là où le contexte ne suffit pas — c'est-à-dire sur les
#: cartes de reverts, dont la valeur n'est pas nommée « reason ». Un mot-clé
#: `reason=` ne porte jamais autre chose qu'une raison, donc il n'est pas
#: filtré : `rejected` n'a pas de souligné et resterait invisible.
_CODE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

#: Les mots-clés dont la valeur EST un code de repli — que ce soit un
#: argument nommé ou une valeur par défaut de paramètre.
#:
#: ``sanitised_msg`` n'y est PAS : ce que `_apply_chunk_fallback` reçoit sous
#: ce nom est le DÉTAIL, pas le code. Il finit derrière le ``:`` de
#: ``all_attempts_exhausted: …``, où aucun consommateur ne l'agrège.
_REASON_KEYWORDS = {"reason", "atomicity_reason"}

#: Les variables dont un élément est une raison — les cartes de reverts que
#: `guards.check_adjacent_duplicates` et `check_boundary_migration` rendent,
#: et que `acceptance._apply_unit_reverts` déballe vers `decide.fall_back`.
_REVERT_MAPS = {"revert", "reverts", "gate_reverts"}


def _codes_in_source() -> dict[str, set[str]]:
    """``code → modules qui l'émettent``, sur les six formes reconnues."""
    found: dict[str, set[str]] = {}

    def note(code: str, where: str, *, filtered: bool = False) -> None:
        code = code.split(":")[0].strip()
        if code and (not filtered or _CODE.match(code)):
            found.setdefault(code, set()).add(where)

    def head_of(value: ast.expr) -> str | None:
        """Le préfixe littéral d'une expression de raison, s'il y en a un.

        Couvre le littéral nu et la f-string — y compris la concaténation
        implicite ``"code: " f"{détail}"``, que Python replie en une seule
        ``JoinedStr`` dont le premier fragment porte le code.
        """
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        if isinstance(value, ast.JoinedStr) and value.values:
            head = value.values[0]
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                return head.value
        return None

    for path in sorted(SRC.rglob("*.py")):
        where = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # 1. reason="literal" / atomicity_reason=... / sanitised_msg=...
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg not in _REASON_KEYWORDS:
                        continue
                    # 1. reason="literal" et 2. reason=f"code: {détail}"
                    head = head_of(kw.value)
                    if head is not None:
                        note(head, where)
                    # 3. reason=<expr> or "literal" — le défaut
                    elif isinstance(kw.value, ast.BoolOp):
                        for operand in kw.value.values:
                            operand_head = head_of(operand)
                            if operand_head is not None:
                                note(operand_head, where)
            # 4. def f(*, atomicity_reason="literal") — la valeur par défaut
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                names = [a.arg for a in (*args.posonlyargs, *args.args)]
                defaults = [None] * (len(names) - len(args.defaults)) + list(
                    args.defaults
                )
                for name, default in zip(
                    names + [a.arg for a in args.kwonlyargs],
                    defaults + list(args.kw_defaults),
                ):
                    if name in _REASON_KEYWORDS and default is not None:
                        head = head_of(default)
                        if head is not None:
                            note(head, where)
            # 5. reason = "a" if cond else "b" — l'aiguillage local
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in _REASON_KEYWORDS
                for target in node.targets
            ):
                value = node.value
                branches = (
                    [value.body, value.orelse]
                    if isinstance(value, ast.IfExp)
                    else [value]
                )
                for branch in branches:
                    head = head_of(branch)
                    if head is not None:
                        note(head, where)
            # 6. revert[x] = "literal" / f"code: …" — les cartes de reverts
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id in _REVERT_MAPS
                for target in node.targets
            ):
                head = head_of(node.value)
                if head is not None:
                    note(head, where, filtered=True)
    return found


def test_no_reason_escapes_the_declared_set() -> None:
    """La direction qui compte : un vingt-et-unième code est refusé."""
    emitted = _codes_in_source()
    stray = {c: sorted(w) for c, w in emitted.items() if c not in FALLBACK_REASON_CODES}
    assert not stray, (
        f"{stray} : ces codes de repli n'existent pas dans "
        f"`core.decide.FALLBACK_REASON_CODES`. Un consommateur agrège sur ce "
        f"code ; en ajouter un est une extension du vocabulaire que lit son "
        f"tableau de bord, pas un littéral de plus."
    )


def test_the_declared_set_names_only_codes_the_engine_emits() -> None:
    """L'autre direction. Un code déclaré que rien n'émet fait promettre au
    vocabulaire une raison qu'un consommateur n'obtiendra jamais.

    ``rejected`` est la seule exemption, et elle est nommée : c'est le défaut
    de ``check_line`` quand une branche de refus ne porte pas sa raison.
    Aucune ne le fait aujourd'hui, mais le site d'appel ne peut pas le
    prouver et écrit donc ``result.reason or "rejected"``.
    """
    emitted = set(_codes_in_source())
    unemitted = sorted(FALLBACK_REASON_CODES - emitted - {"rejected"})
    assert not unemitted, (
        f"{unemitted} sont déclarés et jamais émis : soit le code qui les "
        f"produisait a disparu, soit ils n'ont jamais existé. Les retirer, ou "
        f"nommer l'exemption comme `rejected` l'est."
    )


def test_the_scanner_sees_every_shape() -> None:
    """Un scan vide satisfait la première assertion par le mauvais bout.

    Les six formes syntaxiques sont exercées par des modules différents ;
    si l'une cesse d'être vue, le vocabulaire se rouvre en silence sur cette
    forme-là.
    """
    emitted = _codes_in_source()
    for code, shape in [
        ("hyphen_pair_fallback", "reason= littéral"),
        ("all_attempts_exhausted", "reason= f-string"),
        ("rejected", "reason= <expr> or littéral"),
        ("adjacent_duplicate_detected", "revert[...] = littéral"),
        ("adjacent_duplicate_pair_atomicity", "atomicity_reason= par défaut"),
        ("boundary_migration_forward", "reason = a if cond else b"),
        ("token_realign", "gate_reverts[...] = f-string"),
    ]:
        assert code in emitted, (
            f"le scan ne voit plus la forme « {shape} » : `{code}` devrait "
            f"être trouvé et ne l'est pas"
        )


def test_the_documented_list_is_the_declared_list() -> None:
    """`docs/la-vie-d-une-ligne.md` promet une liste CLOSE.

    Une documentation qui dit « la liste est close » et qui en oublie un est
    pire qu'une documentation qui n'en dit rien, parce qu'on la croit. Ce test
    est ce qui rend la promesse tenable.
    """
    doc = (PKG / "docs" / "la-vie-d-une-ligne.md").read_text(encoding="utf-8")
    missing = sorted(
        code for code in FALLBACK_REASON_CODES if code not in doc and code != "rejected"
    )
    assert not missing, (
        f"{missing} ne sont pas documentés dans `docs/la-vie-d-une-ligne.md`, "
        f"qui promet pourtant une liste close. Un consommateur qui lit ce "
        f"code dans son rapport n'a nulle part où chercher ce qu'il veut dire."
    )
