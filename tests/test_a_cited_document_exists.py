"""A document cited in prose must exist, not only one cited as a link.

``test_references_resolve.py`` already checks markdown **links** and the ADR
index, and it passes. It passed while `CONTRIBUTING.md` named two files as
**normative** that had never existed:

    Normative docs are the ones listed in the README's documentation map
    (README, `SPECS_LIB_V2.md`, `packages/saknussemm/docs/`, `docs/API.md`,
    `SECURITY.md`, this file).

Three problems in one sentence, and none of them was a broken link. Measured
2026-08-17: zero broken markdown links across 61 files, and **five files
citing a document that does not exist** — because the citations are
backticked prose. `docs/API.md` was never written. `SECURITY.md` did not
exist, in a repository about to publish a package. And
`packages/saknussemm/docs/` left with the flattening, along with the
`cd packages/saknussemm` the setup instructions still told a newcomer to run.

The lesson is the shape rather than the three files: a guard that reads one
syntax reports on one syntax. Prose is where a stale reference actually
lives, because prose is what nobody re-runs.
"""

from __future__ import annotations

import re

from tests._paths import PKG

#: A backticked path with a file extension — the way this repository cites a
#: document in a sentence. Extensions only, so an inline `like.this` phrase or
#: a module path does not become a false positive.
_CITED = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|toml|yaml|yml|sh))`")

#: ``(citing file, cited path): reason`` — every exception says why, because a
#: list of names nobody can justify stops being an exception list.
_ALLOWED = {
    ("docs/adr/README.md", "NNN-short-slug.md"): (
        "a filename template, not a reference: it shows how to name a new ADR"
    ),
    ("CHANGELOG.md", "docs/qe-scorer.md"): (
        "a changelog records the past. The QE scorer left for the bench on "
        "2026-08-16 and took its document; rewriting the entry would falsify "
        "the history it exists to keep"
    ),
    ("docs/PLAN.md", "docker-compose.yml"): (
        "left with the demonstration on 2026-08-16; the plan cites it as "
        "something that was, and says so on the spot"
    ),
    ("docs/PLAN.md", "docs/API.md"): (
        "cited as a document that was never created — naming the absence is "
        "the point of the line"
    ),
}

#: Frozen by policy: `docs/history/` is design history and `docs/audit/` is a
#: record of findings. Neither is ever edited to match the code — that rule is
#: in `CLAUDE.md`, and a link checker must not push against it.
_FROZEN = ("docs/history/", "docs/audit/")


def _cited_but_missing() -> dict[str, list[str]]:
    """``{citing file: [paths that resolve to nothing]}``."""
    missing: dict[str, list[str]] = {}
    for path in sorted(PKG.rglob("*.md")):
        relative = path.relative_to(PKG).as_posix()
        if any(relative.startswith(prefix) for prefix in _FROZEN):
            continue
        if ".venv" in relative or "node_modules" in relative:
            continue
        for cited in sorted(set(_CITED.findall(path.read_text(encoding="utf-8")))):
            if (relative, cited) in _ALLOWED:
                continue
            # Repository-relative, or beside the citing file, or a bare name
            # that exists somewhere — a sentence may name `pyproject.toml`
            # without spelling its directory.
            if (PKG / cited).exists() or (path.parent / cited).exists():
                continue
            if next(PKG.rglob(cited.rsplit("/", 1)[-1]), None) is not None:
                continue
            missing.setdefault(relative, []).append(cited)
    return missing


def test_every_document_cited_in_prose_exists() -> None:
    missing = _cited_but_missing()
    assert not missing, (
        f"these files cite a document that does not exist: {missing}. A "
        "citation nobody can follow is worse than no citation: it reads as "
        "evidence that something was written down. Either write the "
        "document, point at the one that carries the content, or add the pair "
        "to the allowlist with its reason."
    )


def test_the_repository_has_a_security_policy() -> None:
    """Named on its own, because publishing without one is the real gap.

    ``CONTRIBUTING.md`` called it normative and it did not exist. A package
    about to reach an index needs somewhere to send a vulnerability report,
    and the general check above would go quiet the moment someone removed the
    citation instead of writing the file.
    """
    policy = PKG / "SECURITY.md"
    assert policy.exists(), "SECURITY.md is gone"
    text = policy.read_text(encoding="utf-8")
    assert "advisories/new" in text or "security" in text.lower(), (
        "SECURITY.md does not say where to report a vulnerability, which is "
        "the one thing it exists to say."
    )


def test_the_readme_says_how_to_install() -> None:
    """Also its own check: the README had no install instruction at all.

    Only `docs/quickstart.md` carried one, and it did not mention the
    `[vision]` extra. For the first document a reader opens, "how do I get
    this" is not a detail.
    """
    readme = (PKG / "README.md").read_text(encoding="utf-8")
    assert "pip install saknussemm" in readme, (
        "the README does not say how to install the package. It is the first "
        "document anyone opens."
    )
    assert "[vision]" in readme, (
        "the README does not mention the [vision] extra, so a reader who "
        "needs the crop-and-ask producer installs a package without Pillow "
        "and finds out at import time."
    )


def test_no_document_still_points_inside_the_flattened_tree() -> None:
    """``packages/saknussemm/`` has not existed since 2026-08-16.

    Three instructions in ``CONTRIBUTING.md`` told a newcomer to `cd` into
    it, which means the local setup steps could not have been run by anyone
    for a day. Frozen history is exempt: it describes the tree as it was.
    """
    offenders: dict[str, int] = {}
    for path in sorted(PKG.rglob("*.md")):
        relative = path.relative_to(PKG).as_posix()
        if any(relative.startswith(prefix) for prefix in _FROZEN):
            continue
        hits = path.read_text(encoding="utf-8").count("cd packages/")
        if hits:
            offenders[relative] = hits
    assert not offenders, (
        f"{offenders} still tell a reader to enter a directory that was "
        "removed when the tree was flattened. An instruction that cannot be "
        "followed is not documentation."
    )


def test_the_declared_limits_stay_declared() -> None:
    """The envelope was measured; a measurement nobody publishes is private.

    Until 2026-08-17 nothing in the README, the contract or the promises said
    how much a document costs, that pages must be corrected in reading order,
    or what reentrancy requires of an injected producer. All four were
    measured facts the library kept to itself, and a consumer discovering any
    of them the hard way discovers it on their own corpus.

    Checked as prose rather than as a number: the point is that the statement
    is there for a reader, and a per-line timing assertion in CI would flake
    on a loaded runner and get deleted.
    """
    readme = (PKG / "README.md").read_text(encoding="utf-8")
    for phrase, why in (
        ("unit of work is one document", "that the corpus belongs to the caller"),
        ("lines per PAGE", "which dimension actually scales"),
        ("reading order", "that page order changes the bytes produced"),
        ("per-run state", "what reentrancy requires of an injected producer"),
    ):
        assert phrase in readme, (
            f"the README no longer says {why} — the phrase {phrase!r} is gone. "
            "Each of these was measured on 2026-08-17 and is a limit a "
            "consumer would otherwise meet on their own corpus."
        )

    spec = (PKG / "SPECS_LIB_V2.md").read_text(encoding="utf-8")
    assert "ordre de lecture des pages" in spec, (
        "the contract no longer states that page order is part of the output "
        "contract. It is the constraint that forbids parallelising pages, and "
        "the code assumes it in prose without asking for it."
    )
