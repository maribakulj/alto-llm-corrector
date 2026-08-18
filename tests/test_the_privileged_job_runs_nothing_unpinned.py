"""A job that can mint a publishing credential may run nothing unpinned.

`id-token: write` puts ``ACTIONS_ID_TOKEN_REQUEST_URL`` and its token in the
environment of **every step of that job, from the first**. Any code running
there can mint an OIDC token of audience ``pypi`` and send it elsewhere; the
upload that follows carries a valid PEP 740 attestation, because the
attestation says *this workflow signed it* — and that would be true.

Found on 2026-08-17: the permission was granted at **workflow** level, so
the single job held it while executing three things resolved from PyPI at
publish time —

1. ``pip install cyclonedx-bom``, no version and no hash;
2. ``pip install dist/*.whl``, which resolves ``pydantic`` and ``lxml`` fresh;
3. the smoke test, which **imports** what step 2 just resolved.

The wheel being published was already immutable, so this was never about
tampering with the package. It was about how much code shared a process with
the one credential that can publish under this name.

The remedy is structural rather than a version pin: two jobs, one that
decides whether to publish and can mint nothing, one that can mint and runs
nothing but pinned actions and ``gh`` — which is preinstalled, not installed.

**And the privileged job fetches the distributions from the verified CI run
itself, not from the unprivileged one.** That closes the path the split
alone leaves open: tooling compromised in the preparing job could rewrite
the wheel before handing it over, and its checksums with it, being the same
job. A run id is all that crosses.

This file pins the shape, because the shape is what protects: a future step
that adds one ``pip install`` to the wrong job would restore the whole
problem without looking like a change of policy.
"""

from __future__ import annotations

import re

import yaml

from tests._paths import PKG

_WORKFLOWS = PKG / ".github" / "workflows"

#: Commands that execute code this repository has not pinned. ``gh`` and
#: ``sha256sum`` are on the runner image; a pinned ``uses:`` is a SHA and is
#: therefore not in this list.
_RESOLVES_CODE = re.compile(
    r"\b(pip install|pipx|npm (?:install|ci)|curl [^\n|]*\|\s*(?:ba)?sh|uv pip install)\b"
)


def _jobs_that_may_mint_a_token() -> dict[str, dict]:
    """``{"<file>:<job>": job}`` for every job holding ``id-token: write``.

    A job-level ``permissions`` block REPLACES the workflow-level one, so a
    job that declares its own does not inherit the token — and one that
    declares none inherits whatever the workflow granted.
    """
    privileged: dict[str, dict] = {}
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        workflow_permissions = document.get("permissions") or {}
        for name, job in (document.get("jobs") or {}).items():
            permissions = job.get("permissions", workflow_permissions)
            if isinstance(permissions, dict) and permissions.get("id-token") == "write":
                privileged[f"{path.name}:{name}"] = job
    return privileged


def test_at_least_one_job_can_publish() -> None:
    """Green by vacuity would look exactly like green.

    If the permission is renamed or the workflow is removed, every check
    below passes over an empty mapping and reports that nothing unpinned
    runs anywhere.
    """
    assert _jobs_that_may_mint_a_token(), (
        "no job declares `id-token: write`, so this file is checking nothing. "
        "Either Trusted Publishing was removed — say so in the CHANGELOG — or "
        "the permission moved and this scan no longer finds it."
    )


def test_no_privileged_job_installs_anything() -> None:
    offenders: dict[str, list[str]] = {}
    for label, job in _jobs_that_may_mint_a_token().items():
        for step in job.get("steps", []):
            script = step.get("run") or ""
            for match in _RESOLVES_CODE.findall(script):
                offenders.setdefault(label, []).append(match)
    assert not offenders, (
        f"these jobs can mint a PyPI credential and also execute code they "
        f"did not pin: {offenders}. Move the step to a job without "
        "`id-token: write` — that is what `prepare-release` is for — or pin "
        "the dependency by hash. A credential is only as protected as the "
        "least trusted thing sharing its process."
    )


def test_the_privileged_job_pins_every_action_it_uses() -> None:
    """A tag is a moving target; only a SHA is a decision."""
    unpinned: dict[str, list[str]] = {}
    for label, job in _jobs_that_may_mint_a_token().items():
        for step in job.get("steps", []):
            uses = step.get("uses")
            if uses and not re.search(r"@[0-9a-f]{40}$", uses):
                unpinned.setdefault(label, []).append(uses)
    assert not unpinned, (
        f"these actions are used by a job that can publish and are not pinned "
        f"to a 40-character SHA: {unpinned}. `@v4` is whatever `v4` points at "
        "on the day the workflow runs."
    )


def test_the_privileged_job_does_not_check_the_repository_out() -> None:
    """``actions/checkout`` leaves a git credential in ``.git/config``.

    Not the largest of the risks, and free to avoid: the publishing job
    needs no working tree, because it fetches the distributions from the CI
    run. Keeping it checkout-free means one fewer secret in the process that
    holds the publishing credential.
    """
    checking_out = [
        label
        for label, job in _jobs_that_may_mint_a_token().items()
        if any("actions/checkout" in (step.get("uses") or "") for step in job["steps"])
    ]
    assert not checking_out, (
        f"{checking_out} check the repository out while holding "
        "`id-token: write`. If a working tree is genuinely needed, pass "
        "`persist-credentials: false` and say why here."
    )
