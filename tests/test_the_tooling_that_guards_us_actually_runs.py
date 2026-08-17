"""A guard that never executes is worse than an absent one.

An absent guard is a known gap. A guard that runs and passes is evidence.
A guard that **silently declines to run** is neither: it occupies the place
where evidence should be, and its green tick is the same green tick.

Three of them were found asleep on 2026-08-17, all in the tooling rather
than in the library:

1. ``tests/test_packaging_excludes_corpora.py`` opens with
   ``pytest.importorskip("build")``. ``build`` was in no declared extra, so
   both of its checks were **SKIPPED in every CI run** — including the one
   that keeps a 43 MB corpus out of the sdist. Measured: with exactly the
   packages CI installs, ``SKIPPED [1] …:190`` and ``SKIPPED [1] …:208``.
2. ``.pre-commit-config.yaml`` had a repo entry whose ``hooks:`` key was
   empty (``hooks = None`` after parsing). pre-commit validates the
   **whole** file before running anything, so **not one hook ran** — not
   ruff, not the >1 MB file guard that the file's own comment advertises.
3. ``scripts/release-saknussemm.sh`` still pointed at
   ``packages/saknussemm``, gone since the tree was flattened, so it died
   on its third useful statement — while ``test_release_tooling.py``
   verified its version regexes and passed.

The third is the one worth remembering: **the test checked the script's
text and never that it could start.** All three share that shape, which is
why they are one file rather than three.

This file is the sibling of
``test_no_test_skips_because_a_committed_fixture_is_missing``: same
failure mode, different cause — there a missing file, here a missing
dependency or a malformed config.
"""

from __future__ import annotations

import re
import tomllib

import yaml

from tests._paths import PKG

#: Module name → the distribution that provides it, for the handful of
#: cases where they differ. Anything not here is assumed to match.
_DISTRIBUTION_OF = {"PIL": "pillow", "yaml": "pyyaml"}

#: What CI installs — kept as the literal extras rather than parsed out of
#: the workflow, because the point is to compare two independent statements
#: and a single parsed source would compare one to itself.
_EXTRAS_CI_INSTALLS = ("test", "vision")


def _declared_distributions() -> set[str]:
    """Every distribution a CI test job has available, by name."""
    with (PKG / "pyproject.toml").open("rb") as fh:
        project = tomllib.load(fh)["project"]
    requirements = list(project["dependencies"])
    for extra in _EXTRAS_CI_INSTALLS:
        requirements += project["optional-dependencies"][extra]
    names = set()
    for requirement in requirements:
        name = re.split(r"[<>=!~;\[ ]", requirement, maxsplit=1)[0]
        names.add(name.strip().lower())
    return names


def test_every_importorskip_names_something_ci_installs() -> None:
    """Otherwise the module it protects is decoration.

    The check is on the *declaration*, not on whether the import happens to
    work in the current interpreter: a developer with a stray ``build`` in
    their venv sees the tests run, and CI does not.
    """
    declared = _declared_distributions()
    unavailable: dict[str, str] = {}
    for path in sorted((PKG / "tests").rglob("test_*.py")):
        for module in re.findall(
            r'importorskip\(\s*"([A-Za-z0-9_.]+)"', path.read_text()
        ):
            distribution = _DISTRIBUTION_OF.get(module, module).lower()
            if distribution not in declared:
                unavailable[f"{path.name}:{module}"] = distribution
    assert not unavailable, (
        f"these modules are importorskip'd but no declared extra provides "
        f"them: {unavailable}. CI installs {list(_EXTRAS_CI_INSTALLS)}, so "
        "each of these modules is a whole test file that reports one quiet "
        "skip forever. Add the distribution to the extra, or drop the "
        "importorskip and let the test fail honestly."
    )


def test_every_pre_commit_repo_declares_at_least_one_hook() -> None:
    """An empty ``hooks:`` disables the ENTIRE file, not just its own entry.

    pre-commit validates the whole config before executing anything, so one
    malformed block silences every other hook. That is why this asserts per
    repo and reports all of them: a reader seeing one name would fix it and
    assume the rest had been running.
    """
    config = yaml.safe_load((PKG / ".pre-commit-config.yaml").read_text())
    empty = [
        repo.get("repo", "?")
        for repo in config.get("repos", [])
        if not repo.get("hooks")
    ]
    assert not empty, (
        f"{empty} declare no hooks. pre-commit refuses the whole file on "
        "this, so NOTHING runs — including the >1MB file guard this config "
        "advertises in its own comments. Remove the block or give it hooks."
    )


def test_no_pre_commit_hook_targets_a_path_that_no_longer_exists() -> None:
    """A hook matching nothing is indistinguishable from a hook that passed.

    Measured: a ``prettier`` hook kept targeting ``frontend/src/`` for a
    day after the demo left the repository, reporting success on every
    commit by matching no file at all.
    """
    config = yaml.safe_load((PKG / ".pre-commit-config.yaml").read_text())
    dead: dict[str, str] = {}
    for repo in config.get("repos", []):
        for hook in repo.get("hooks") or []:
            pattern = hook.get("files")
            if not pattern:
                continue
            # The leading literal directory of an anchored pattern is the
            # only part worth checking, and the only part that goes stale.
            match = re.match(r"\^\(?([A-Za-z0-9_.-]+)", pattern)
            if match and not (PKG / match.group(1)).exists():
                dead[hook.get("id", "?")] = pattern
    assert not dead, (
        f"these hooks target directories that do not exist: {dead}. They "
        "match nothing and pass every time, which reads exactly like a "
        "hook that checked something."
    )


def test_the_release_script_paths_exist() -> None:
    """Its regexes were verified; that it can start was not.

    Checking the shell variable rather than running the script: running it
    would tag and publish. This is the cheap half that was missing, and it
    is the half that failed.
    """
    script = (PKG / "scripts" / "release-saknussemm.sh").read_text()
    for relative in re.findall(r"\$\{REPO_ROOT\}/([A-Za-z0-9_./-]+)", script):
        assert (PKG / relative).exists(), (
            f"the release script resolves {relative!r} under the repository "
            "root and it does not exist — the tree was flattened on "
            "2026-08-16. The script dies before its first useful command, "
            "and a test that reads its text cannot tell."
        )
