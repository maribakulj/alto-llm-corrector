"""§3 import-rule contract — the module graph is law, not convention.

Rules enforced:
  1. ``lidenbrock.core`` (and ``errors``) never import lxml, formats or
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

FORBIDDEN_IN_CORE = ("lxml", "lidenbrock.formats", "lidenbrock.producers")


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
            if name.startswith(("lidenbrock.formats", "lidenbrock.producers"))
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
#: ``lidenbrock/__init__`` imports ``core.pipeline`` imports ``core.rendering``
#: imports ``lidenbrock`` — broken only by the imports being function-local.
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

    Not a violation of the §3 rule — ``lidenbrock`` is not ``formats`` or
    ``producers`` — which is exactly why nothing was watching it. Decided
    open, so it is pinned open: the point is that "we know about it" and
    "it cannot grow" are different properties, and only the second one
    survives a busy month.
    """
    found: dict[str, set[str]] = {}
    for f in _core_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "lidenbrock":
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
        "import lidenbrock.core.pipeline, lidenbrock.core.schemas, "
        "lidenbrock.core.guards, lidenbrock.core.validator, "
        "lidenbrock.core.hyphenation, lidenbrock.core.planner, "
        "lidenbrock.core.protocols, lidenbrock.errors; "
        "sys.exit(1 if 'lxml' in sys.modules else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, f"importing core loaded lxml\n{proc.stderr}"


def test_producers_are_pure_and_formats_ignore_producers():
    for f in sorted((SRC / "producers").glob("*.py")):
        bad = _violations(f, ("lxml", "lidenbrock.formats"))
        assert not bad, bad
    for f in sorted((SRC / "formats").rglob("*.py")):
        bad = _violations(f, ("lidenbrock.producers",))
        assert not bad, bad


# ---------------------------------------------------------------------------
# lidenbrock[qe] — the D'AlemBERT scorer's heavy deps (onnxruntime/tokenizers/
# numpy, and never torch/transformers at runtime) must be LAZY: importable
# module, zero import cost for anyone who does not construct the scorer, and
# never pulled in by the pixel-light core.
# ---------------------------------------------------------------------------

QE_HEAVY = ("onnxruntime", "tokenizers", "numpy", "torch", "transformers")


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


def test_qe_scorer_keeps_every_heavy_dep_function_local():
    qe = SRC / "integrations" / "qe.py"
    module_level = _module_level_imports(qe)
    leaked = [
        h
        for h in QE_HEAVY
        if any(m == h or m.startswith(h + ".") for m in module_level)
    ]
    assert not leaked, f"heavy deps must be lazy, not module-level in qe.py: {leaked}"


def test_importing_qe_module_never_loads_the_heavy_runtime():
    """Importing the module (introspection, protocol checks) must not load
    onnxruntime/torch/transformers — those arrive only when a scorer is
    constructed and first used."""
    code = (
        "import sys; import lidenbrock.integrations.qe as _; "
        "heavy = ('onnxruntime', 'torch', 'transformers', 'tokenizers'); "
        "sys.exit(1 if any(m in sys.modules for m in heavy) else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, f"importing qe.py loaded a heavy dep\n{proc.stderr}"


def test_importing_core_quality_stays_pure():
    """The QE seam lives in the core (protocol + heuristic baseline) and
    must stay dependency-free: importing it never loads the extra."""
    code = (
        "import sys; import lidenbrock.core.quality as _; "
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
# cheap first line; THIS is the honest proof: importing lidenbrock (the base
# install surface — core + eagerly-loaded producers + schemas) must pull no
# image library into sys.modules, even with the opt-in lidenbrock[vision]
# producer sitting in the same package. Pillow arrives ONLY when a caller
# constructs the vision producer, never before.
# ---------------------------------------------------------------------------

IMAGE_LIBS = ("PIL", "cv2", "imageio", "skimage", "wand", "torchvision")


def test_importing_lidenbrock_never_loads_an_image_lib():
    code = (
        "import sys; import lidenbrock as _; "
        f"libs = {IMAGE_LIBS!r}; "
        "sys.exit(1 if any(m.split('.')[0] in libs for m in sys.modules) else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"importing lidenbrock loaded an image lib\n{proc.stderr}"
    )


def test_importing_pipeline_never_loads_an_image_lib():
    """The engine entry point specifically — the correction path a run takes
    is pixel-free even though a vision producer plugs into its §4.1 seam."""
    code = (
        "import sys; import lidenbrock.core.pipeline as _; "
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
        "import sys; import lidenbrock.integrations.vision as _; "
        f"libs = {IMAGE_LIBS!r}; "
        "sys.exit(1 if any(m.split('.')[0] in libs for m in sys.modules) else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"importing integrations.vision loaded an image lib\n{proc.stderr}"
    )
