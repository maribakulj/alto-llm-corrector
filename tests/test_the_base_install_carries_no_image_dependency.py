"""The base install pulls in Pydantic and lxml, and nothing else.

`I4` is the invariant this project states most often — the core is blind to
pixels — and it has three levels. Two were guarded: the core imports no
image library (an AST scan), and the `[vision]` extra imports Pillow lazily
(a scan plus a real subprocess import).

**The middle level had nothing.** No test read ``[project].dependencies``.
The one that looked like it did compared a run's provenance to
``_PROVENANCE_DEPENDENCIES``, a tuple hardcoded in the source next to the
code that uses it — so it asserted that the tuple equals itself. Adding
``pillow`` to the runtime dependencies would have left the whole suite
green while making an extra mandatory for everyone.

That was the easiest promise in the contract to break in silence, on the
invariant the project leans on hardest. Found on 2026-08-16 by listing what
the contract promises and asking, of each, what guards it — rather than by
reading the tests and asking what they cover.
"""

from __future__ import annotations

import tomllib

from tests._paths import PKG

#: What the base install is allowed to require, by name. Widening this is a
#: decision about what `pip install saknussemm` costs a consumer, and it
#: belongs in the same commit as the reason.
_ALLOWED_RUNTIME_DEPENDENCIES = {"pydantic", "lxml"}

#: An image library reaching `dependencies` is the specific failure `I4`
#: level 2 forbids; named separately so the message can say so.
_IMAGE_LIBRARIES = {"pillow", "opencv-python", "imageio", "scikit-image", "wand"}


def _declared_runtime_dependencies() -> dict[str, str]:
    """``{distribution name: the full requirement string}``.

    The name is everything before the first version specifier, extra
    marker or environment marker — enough to recognise a distribution
    without reimplementing PEP 508.
    """
    with (PKG / "pyproject.toml").open("rb") as fh:
        declared = tomllib.load(fh)["project"]["dependencies"]
    out: dict[str, str] = {}
    for requirement in declared:
        name = requirement.split(";")[0]
        for separator in ("[", "<", ">", "=", "!", "~", " "):
            name = name.split(separator)[0]
        out[name.strip().lower()] = requirement
    return out


def test_the_declaration_is_readable_and_not_empty() -> None:
    """Green by vacuity would look exactly like green.

    If `dependencies` disappears or is renamed, the checks below would pass
    on an empty mapping and report that nothing forbidden is declared.
    """
    declared = _declared_runtime_dependencies()
    assert declared, "no [project].dependencies found — the scan has nothing to check"


def test_the_base_install_requires_only_pydantic_and_lxml() -> None:
    declared = _declared_runtime_dependencies()
    unexpected = set(declared) - _ALLOWED_RUNTIME_DEPENDENCIES
    assert not unexpected, (
        f"the base install would now pull in {sorted(unexpected)}. "
        f"`pip install saknussemm` is meant to cost a consumer Pydantic and "
        f"lxml and nothing else; anything heavier belongs behind an extra. "
        f"If this is deliberate, widen the allowlist in this file and say "
        f"why in the same commit."
    )


def test_no_image_library_reaches_the_base_install() -> None:
    """`I4` level 2, stated as its own failure so the message names it."""
    declared = _declared_runtime_dependencies()
    images = sorted(set(declared) & _IMAGE_LIBRARIES)
    assert not images, (
        f"{images} is a runtime dependency. The core is blind to pixels and "
        f"the base install carries no image library — that is what makes "
        f"`[vision]` an extra rather than a fiction. It belongs in "
        f"`[project.optional-dependencies].vision`, imported lazily inside "
        f"the functions that decode."
    )


def test_the_vision_extra_is_where_the_image_library_actually_is() -> None:
    """The mirror image: an extra that declares nothing is not an extra.

    Without this, moving Pillow out of the extra *and* out of the base
    install would satisfy every assertion above while breaking the feature.
    """
    with (PKG / "pyproject.toml").open("rb") as fh:
        extras = tomllib.load(fh)["project"]["optional-dependencies"]
    assert "vision" in extras, "the [vision] extra is gone"
    joined = " ".join(extras["vision"]).lower()
    assert any(lib in joined for lib in _IMAGE_LIBRARIES), (
        f"[vision] declares {extras['vision']}, which contains no image "
        f"library. The extra is what pays for pixels; if it pays for "
        f"nothing, the base install is doing the work and I4 level 2 is "
        f"broken in the other direction."
    )
