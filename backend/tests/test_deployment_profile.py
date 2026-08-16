"""Explicit deployment profiles.

'demo' is the public-Space stance (wildcard CORS tolerated, documented in
SECURITY.md). 'proxy_protected' asserts an authenticating reverse proxy sits
in front and REFUSES demo-grade defaults instead of silently running with
them — a misconfigured deployment must fail loudly at startup, not leak
quietly at runtime.

The profile was called 'institutional' until 2026-07-28 (D12). SECURITY.md's
body was always honest — no user accounts, no job ownership, no quotas, no
database, single-worker — but the NAME read as "ready for an institution",
which is exactly what that paragraph denies. `DEPLOYMENT_PROFILE` is a public
environment variable, so the old value keeps working and warns rather than
breaking a running deployment on upgrade.
"""

from __future__ import annotations

import pytest

from app.main import create_app


def test_demo_profile_is_the_default_and_tolerates_wildcard_cors(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT_PROFILE", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    create_app()  # must not raise


def test_proxy_protected_profile_refuses_wildcard_cors(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "proxy_protected")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        create_app()

    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        create_app()


def test_proxy_protected_profile_starts_with_an_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "proxy_protected")
    monkeypatch.setenv("CORS_ORIGINS", "https://lidenbrock.example.org")
    create_app()  # must not raise


def test_unknown_profile_is_rejected(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "production-ish")
    with pytest.raises(RuntimeError, match="DEPLOYMENT_PROFILE"):
        create_app()


class TestTheDeprecatedSpelling:
    """`institutional` must keep BEHAVING and start SAYING (D12).

    A renamed environment variable that simply stops being recognised turns
    an upgrade into an outage — and here it would be worse than an outage:
    an unrecognised value used to fall through to the wildcard-tolerant
    default, so a deployment that meant to refuse wildcard CORS would have
    silently accepted it. Hence an explicit alias rather than a rename.
    """

    def test_it_still_enforces_the_same_refusal(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "institutional")
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
            create_app()

    def test_it_still_starts_with_an_explicit_allowlist(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "institutional")
        monkeypatch.setenv("CORS_ORIGINS", "https://lidenbrock.example.org")
        create_app()  # must not raise

    def test_it_warns_and_names_its_replacement(self, monkeypatch, capsys):
        """Asserted on STDOUT rather than through ``caplog``: ``create_app``
        installs the app's logging configuration, which replaces the root
        handlers — and takes pytest's capture handler with them. What an
        operator sees is the JSON line on stdout, so that is what is
        checked."""
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "institutional")
        monkeypatch.setenv("CORS_ORIGINS", "https://lidenbrock.example.org")
        create_app()
        out = capsys.readouterr().out
        assert "deprecated" in out, out
        assert "proxy_protected" in out, out

    def test_the_new_spelling_warns_about_nothing(self, monkeypatch, capsys):
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "proxy_protected")
        monkeypatch.setenv("CORS_ORIGINS", "https://lidenbrock.example.org")
        create_app()
        assert "deprecated" not in capsys.readouterr().out

    def test_the_error_message_names_the_new_spelling(self, monkeypatch):
        """An operator who mistypes must be pointed at the CURRENT name, not
        at the one being retired."""
        monkeypatch.setenv("DEPLOYMENT_PROFILE", "instutional")
        with pytest.raises(RuntimeError, match="proxy_protected"):
            create_app()
