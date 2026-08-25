"""§3 import-rule contract — the module graph is law, not convention.

Rules enforced:
  1. ``saknussemm.core`` (and ``errors``) never import lxml, formats or
     producers — statically NOR at import time (subprocess-verified: no
     ``lxml`` in ``sys.modules`` after importing every core module).
  2. Exactly TWO composition sites, NAMED — ``_render_outputs``
     (``core/rendering.py``, resolves the manifest's adapter) and
     ``for_provider`` (``core/pipeline.py``, wraps a client into an
     ``LLMEditProducer``) — each with function-local imports only.

     This used to be ``assert len(violations) == 3``, and `RM-07` replaced
     the count with the rule. A count is a ceiling: it says how much
     trespass is tolerated without saying by whom, so a new violation
     anywhere in ``core`` was legal as long as an old one vanished in the
     same commit. The pin is on function NAMES, not files — ``S2`` had
     already shown why, by moving a site between modules and breaking a
     test about import purity for a reason unrelated to import purity.

     `RM-07` also took one entry OFF the list: the adapter resolver moved
     to ``formats/loader.py``, next to the parser dispatch that answers
     the same question, so ``core`` no longer enumerates ALTO and PAGE
     anywhere.
  3. ``formats`` never imports producers; ``producers`` never imports
     formats or lxml.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from tests._paths import SRC

SRC = SRC

FORBIDDEN_IN_CORE = ("lxml", "saknussemm.formats", "saknussemm.producers")


def _imports(tree: ast.AST) -> list[tuple[str, int]]:
    """Every imported module name in the tree, with its line number."""
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, node.lineno))
    return out


def _violations(path: Path, forbidden: tuple[str, ...]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        f"{path.name}:{lineno} imports {name}"
        for name, lineno in _imports(tree)
        if any(name == f or name.startswith(f + ".") for f in forbidden)
    ]


#: The ONLY functions in ``core`` allowed to reach a format or producer
#: module, and each may do so only with a function-local import.
#:
#: A NAMED rule, not a count. It used to be ``assert len(violations) == 3``,
#: which is a ceiling: it said how much trespass was tolerated without
#: saying by whom, so a new violation anywhere in ``core`` was legal as long
#: as an old one disappeared in the same commit. `RM-07` replaced it with
#: this list and, in the same move, took one of the two entries off it —
#: the adapter resolver went to ``formats/loader.py``, beside the parser
#: dispatch that answers the same question.
#:
#: ``_render_outputs`` is what remains: the engine has to reach SOME format
#: to write a file, and this is the seam where it does. It no longer knows
#: WHICH formats exist — it asks ``formats.loader.adapter_for_format`` and
#: that module owns the enumeration.
_LAZY_COMPOSITION_SITES = {
    "_render_outputs": "core/rendering.py — resolves the manifest's adapter",
    "for_provider": "core/pipeline.py — wraps a client into an LLMEditProducer",
}


def _core_files() -> list[Path]:
    return sorted((SRC / "core").glob("*.py")) + [SRC / "errors.py"]


def _functions_reaching_out(path: Path) -> set[str]:
    """Functions in ``path`` with a function-local formats/producers import."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            name
            for name, _ in _imports(node)
            if name.startswith(("saknussemm.formats", "saknussemm.producers"))
        )
    }


def test_only_the_named_sites_reach_a_format_or_producer():
    """The rule: these functions, and nothing else in ``core``."""
    reaching = set()
    for f in _core_files():
        reaching |= _functions_reaching_out(f)
    unexpected = reaching - set(_LAZY_COMPOSITION_SITES)
    assert not unexpected, (
        f"{sorted(unexpected)} import a format or producer module from core. "
        "Only the named composition sites may, and adding one is a design "
        f"decision, not a diff: {_LAZY_COMPOSITION_SITES}"
    )
    missing = set(_LAZY_COMPOSITION_SITES) - reaching
    assert not missing, (
        f"{sorted(missing)} no longer reach out — drop them from "
        "_LAZY_COMPOSITION_SITES so the list keeps naming what is real."
    )


def test_no_core_module_reaches_out_at_import_time():
    """Every allowed import is function-local. A module-level one would
    make the whole of ``core`` depend on lxml, which is the property
    :func:`test_importing_core_never_loads_lxml` checks at runtime — this
    is the same fact, stated statically and with a file name attached."""
    module_level: list[str] = []
    for f in _core_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        # Top-level import STATEMENTS only. Deliberately not `_imports`,
        # which walks into function bodies — that is where every allowed
        # site lives, so using it here would flag exactly the imports this
        # rule permits.
        for node in tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for name, lineno in _imports(node):
                if any(
                    name == forbidden or name.startswith(forbidden + ".")
                    for forbidden in FORBIDDEN_IN_CORE
                ):
                    module_level.append(f"{f.name}:{lineno} imports {name}")
    assert not module_level, (
        f"module-level forbidden imports in core: {module_level}. The "
        "composition sites are lazy so that importing a core module never "
        "loads lxml."
    )


#: ``core`` modules that import the package root. This is a real cycle —
#: ``saknussemm/__init__`` imports ``core.pipeline`` imports ``core.rendering``
#: imports ``saknussemm`` — broken only by the imports being function-local.
#:
#: `RM-07` looked at closing it and decided NOT to, on the merits rather
#: than on effort. The cycle carries one symbol, ``__version__``, a module
#: level string; a lazy import of it cannot deadlock and cannot partially
#: initialise anything the caller then uses. Closing it means moving
#: ``__version__`` to its own module, which means editing
#: ``[tool.hatch.version] path`` (the wheel's version source) and the CI
#: job that greps ``__init__.py`` for it — the release toolchain, for zero
#: behavioural gain. And it is not what `RM-07` is about: the item is
#: "core does not know the FORMATS", and a version string is not a format.
#:
#: What the decision buys by being written here instead of in a document is
#: that it stays BOUNDED. A third site cannot appear quietly.
_SELF_IMPORT_SITES = {
    "core/provenance.py": "_build_run_provenance — stamps the lib version",
    "core/rendering.py": "_rewrite_and_verify — stamps the processingStep",
}


def test_the_package_self_import_stays_where_it_was_measured():
    """A known cycle, held at two sites (`RM-07`).

    Not a violation of the §3 rule — ``saknussemm`` is not ``formats`` or
    ``producers`` — which is exactly why nothing was watching it. Decided
    open, so it is pinned open: the point is that "we know about it" and
    "it cannot grow" are different properties, and only the second one
    survives a busy month.
    """
    found: dict[str, set[str]] = {}
    for f in _core_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "saknussemm":
                rel = f.relative_to(SRC).as_posix()
                found.setdefault(rel, set()).update(a.name for a in node.names)
    assert set(found) == set(_SELF_IMPORT_SITES), (
        f"the package self-import moved: {sorted(found)} vs the pinned "
        f"{sorted(_SELF_IMPORT_SITES)}. Adding one deepens a cycle that is "
        "currently harmless only because it carries a single constant; "
        "removing one means the entry should go."
    )
    carried = {name for names in found.values() for name in names}
    assert carried == {"__version__"}, (
        f"the self-import now carries {sorted(carried)}. It was decided "
        "harmless because it is one module-level string — a second symbol "
        "is a different decision, not the same one."
    )


def test_importing_core_never_loads_lxml():
    """Runtime guarantee, not just static: a consumer that only wants the
    pure algorithms (guards, planner, schemas, reconciliation, pipeline)
    pays zero lxml import cost — and can run where lxml isn't installed."""
    code = (
        "import sys; "
        "import saknussemm.core.pipeline, saknussemm.core.schemas, "
        "saknussemm.core.guards, saknussemm.core.validator, "
        "saknussemm.core.hyphenation, saknussemm.core.planner, "
        "saknussemm.core.protocols, saknussemm.errors; "
        "sys.exit(1 if 'lxml' in sys.modules else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, f"importing core loaded lxml\n{proc.stderr}"


def test_producers_are_pure_and_formats_ignore_producers():
    for f in sorted((SRC / "producers").glob("*.py")):
        bad = _violations(f, ("lxml", "saknussemm.formats"))
        assert not bad, bad
    for f in sorted((SRC / "formats").rglob("*.py")):
        bad = _violations(f, ("saknussemm.producers",))
        assert not bad, bad


#: Ce qu'un module de ``producers/`` a le droit d'importer du paquet.
#: ``core`` pour le protocole et les schémas, ``errors`` pour la taxonomie,
#: ``integrations`` pour le vocabulaire de vendeur — le prompt système et le
#: schéma de sortie JSON, qui n'existent que parce que le producteur est un
#: LLM et n'ont donc rien à faire dans le cœur.
_PRODUCERS_MAY_IMPORT = (
    "saknussemm.core",
    "saknussemm.errors",
    "saknussemm.integrations",
)


def test_the_producers_boundary_is_the_one_its_docstring_states():
    """``producers/__init__.py`` a longtemps dit « Import only
    ``saknussemm.core`` » pendant que deux de ses trois modules importaient
    ``integrations.llm``.

    La phrase a été corrigée le 2026-08-25 ; ce test est ce qui l'empêche de
    redevenir fausse. Une règle écrite que rien ne vérifie se périme au
    premier import, et celle-là s'était périmée sans que personne le voie.

    La frontière est aussi devenue lisible dans le même mouvement :
    ``VisionEditProducer`` vivait dans ``integrations/`` alors que les autres
    producteurs vivaient dans ``producers/``. Le critère annoncé — « ce qui
    existe seulement parce que le producteur est un LLM » — ne discriminait
    rien, puisqu'il vaut aussi pour ``LLMEditProducer``. Il vaut maintenant
    ce qu'il dit : ``producers/`` porte les implémentations d'``EditProducer``,
    ``integrations/`` le vocabulaire de vendeur qu'elles consomment.
    """
    offenders: dict[str, list[str]] = {}
    for f in sorted((SRC / "producers").glob("*.py")):
        reached = sorted(
            name
            for name, _ in _imports(ast.parse(f.read_text(encoding="utf-8")))
            if name.startswith("saknussemm.")
            and not name.startswith(_PRODUCERS_MAY_IMPORT)
        )
        if reached:
            offenders[f.name] = reached
    assert not offenders, (
        f"{offenders} : un producteur n'importe du paquet que `core`, "
        f"`errors` et `integrations`. Élargir cette liste est une décision "
        f"sur ce que `producers/` EST, pas un import de plus."
    )


def test_no_producer_lives_outside_the_producers_package():
    """Un producteur rangé ailleurs rend la frontière inutilisable.

    ``integrations/`` porte du vocabulaire, pas des implémentations. Le
    critère est mécanique : une classe qui expose ``produce`` remplit le
    protocole ``EditProducer`` et appartient à ``producers/``.
    """
    misplaced: dict[str, list[str]] = {}
    for f in sorted((SRC / "integrations").glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        classes = [
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and any(
                isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                and m.name == "produce"
                for m in node.body
            )
        ]
        if classes:
            misplaced[f.name] = classes
    assert not misplaced, (
        f"{misplaced} remplissent le protocole EditProducer depuis "
        f"`integrations/`. Les implémentations vivent dans `producers/` ; "
        f"`integrations/` porte ce qu'elles consomment."
    )


# ---------------------------------------------------------------------------
# An optional extra must be optional in fact, not only in the metadata: the
# module stays importable, costs nothing to anyone who does not use it, and
# is never pulled in by the pixel-light core. Written for the QE scorer,
# which left for the bench on 2026-08-16; the rule outlived it because it
# was never about that module.
# ---------------------------------------------------------------------------


def _module_level_imports(path: Path) -> set[str]:
    """Only the imports at the top level of the module body (not nested in
    functions/methods)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_vision_keeps_every_heavy_dep_function_local():
    """An optional dependency imported at module level is not optional.

    This guard was written for the QE scorer, which left for the bench on
    2026-08-16. The rule was never about that module: an extra earns the
    name only if the base install can import the package without paying
    for it, and a module-level ``import PIL`` would make ``[vision]``
    mandatory in everything but the metadata.

    Its companion below checks the same property by RUNNING an import;
    this one reads the source, so it also catches a dependency that is
    installed in the test environment and would therefore import cleanly.
    """
    vision = SRC / "producers" / "vision.py"
    module_level = _module_level_imports(vision)
    leaked = [
        h
        for h in IMAGE_LIBS
        if any(m == h or m.startswith(h + ".") for m in module_level)
    ]
    assert not leaked, (
        f"heavy deps must be lazy, not module-level in vision.py: {leaked}"
    )


def test_importing_core_quality_stays_pure():
    """The QE seam lives in the core (protocol + heuristic baseline) and
    must stay dependency-free: importing it never loads the extra."""
    code = (
        "import sys; import saknussemm.core.quality as _; "
        "heavy = ('onnxruntime', 'torch', 'transformers', 'tokenizers'); "
        "sys.exit(1 if any(m in sys.modules for m in heavy) else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"importing core.quality loaded a heavy dep\n{proc.stderr}"
    )


# ---------------------------------------------------------------------------
# I4 — pixel-blindness is a property of the IMPORT
# GRAPH, not the file tree. The static AST scan (test_edit_producer.py) is a
# cheap first line; THIS is the honest proof: importing saknussemm (the base
# install surface — core + eagerly-loaded producers + schemas) must pull no
# image library into sys.modules, even with the opt-in saknussemm[vision]
# producer sitting in the same package. Pillow arrives ONLY when a caller
# constructs the vision producer, never before.
# ---------------------------------------------------------------------------

IMAGE_LIBS = ("PIL", "cv2", "imageio", "skimage", "wand", "torchvision")


def test_importing_saknussemm_never_loads_an_image_lib():
    code = (
        "import sys; import saknussemm as _; "
        f"libs = {IMAGE_LIBS!r}; "
        "sys.exit(1 if any(m.split('.')[0] in libs for m in sys.modules) else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"importing saknussemm loaded an image lib\n{proc.stderr}"
    )


def test_importing_pipeline_never_loads_an_image_lib():
    """The engine entry point specifically — the correction path a run takes
    is pixel-free even though a vision producer plugs into its §4.1 seam."""
    code = (
        "import sys; import saknussemm.core.pipeline as _; "
        f"libs = {IMAGE_LIBS!r}; "
        "sys.exit(1 if any(m.split('.')[0] in libs for m in sys.modules) else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"importing core.pipeline loaded an image lib\n{proc.stderr}"
    )


def test_importing_vision_module_never_loads_pillow_at_import():
    """Even the vision surface itself imports Pillow LAZILY: importing the
    module (the VLM producer picking up the cropper, introspection) must not
    pay the image runtime — it arrives only when a crop is actually taken
    (mirrors the qe scorer's contract)."""
    code = (
        "import sys; import saknussemm.producers.vision as _; "
        f"libs = {IMAGE_LIBS!r}; "
        "sys.exit(1 if any(m.split('.')[0] in libs for m in sys.modules) else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"importing producers.vision loaded an image lib\n{proc.stderr}"
    )
