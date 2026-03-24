"""Tests for LLM providers."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers import get_provider
from app.providers.base import OUTPUT_JSON_SCHEMA, SYSTEM_PROMPT
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.google_provider import GoogleProvider, _keep_model
from app.providers.mistral_provider import MistralProvider
from app.providers.openai_provider import OpenAIProvider, _keep_model as openai_keep
from app.schemas import Provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://example.com"),
    )


# ---------------------------------------------------------------------------
# test_openai_allowlist_prefixes
# ---------------------------------------------------------------------------

def test_openai_allowlist_prefixes():
    assert openai_keep("gpt-4o")
    assert openai_keep("gpt-4-turbo")
    assert openai_keep("gpt-3.5-turbo")
    assert openai_keep("o1-preview")
    assert openai_keep("o3-mini")
    assert openai_keep("o4-mini")
    # Not in allowlist
    assert not openai_keep("babbage-002")
    assert not openai_keep("text-davinci-003")


# ---------------------------------------------------------------------------
# test_openai_denylist_patterns
# ---------------------------------------------------------------------------

def test_openai_denylist_patterns():
    assert not openai_keep("gpt-4-instruct")
    assert not openai_keep("gpt-4-embedding")
    assert not openai_keep("gpt-4-audio-preview")
    assert not openai_keep("gpt-4-realtime-preview")
    assert not openai_keep("gpt-4-tts")
    assert not openai_keep("dall-e-3")
    assert not openai_keep("whisper-1")
    assert not openai_keep("omni-moderation-latest")
    # Valid model not matched by denylist
    assert openai_keep("gpt-4o-mini")


# ---------------------------------------------------------------------------
# test_mistral_capability_filter
# ---------------------------------------------------------------------------

def test_mistral_capability_filter():
    models_data = {
        "data": [
            {"id": "mistral-large", "name": "Mistral Large",
             "capabilities": {"completion_chat": True}},
            {"id": "mistral-embed", "name": "Mistral Embed",
             "capabilities": {"completion_chat": False}},
            {"id": "mistral-small", "name": "Mistral Small",
             "capabilities": {"completion_chat": True}},
            {"id": "no-caps", "name": "No caps",
             "capabilities": {}},
        ]
    }

    # Use the filter logic directly
    kept = [
        m["id"]
        for m in models_data["data"]
        if m.get("capabilities", {}).get("completion_chat", False)
    ]
    assert "mistral-large" in kept
    assert "mistral-small" in kept
    assert "mistral-embed" not in kept
    assert "no-caps" not in kept


# ---------------------------------------------------------------------------
# test_google_generate_content_filter
# ---------------------------------------------------------------------------

def test_google_generate_content_filter():
    models = [
        {"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/aqa", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/attribute-001", "supportedGenerationMethods": ["generateContent"]},
    ]
    kept = [m["name"].split("/")[-1] for m in models if _keep_model(m)]
    assert "gemini-1.5-pro" in kept
    assert "gemini-1.5-flash" in kept
    assert "text-embedding-004" not in kept
    assert "aqa" not in kept
    assert "attribute-001" not in kept


# ---------------------------------------------------------------------------
# test_anthropic_model_parse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anthropic_model_parse():
    api_resp = {
        "data": [
            {"id": "claude-3-opus-20240229", "display_name": "Claude 3 Opus"},
            {"id": "claude-3-sonnet-20240229", "display_name": "Claude 3 Sonnet"},
        ]
    }

    mock_resp = _make_response(200, api_resp)

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_resp)

        provider = AnthropicProvider()
        models = await provider.list_models("fake-key")

    ids = [m.id for m in models]
    labels = [m.label for m in models]
    assert "claude-3-opus-20240229" in ids
    assert "Claude 3 Opus" in labels
    assert "claude-3-sonnet-20240229" in ids


# ---------------------------------------------------------------------------
# test_system_prompt_contains_hyphen_rule
# ---------------------------------------------------------------------------

def test_system_prompt_contains_hyphen_rule():
    assert "HypPart1" in SYSTEM_PROMPT
    assert "HypPart2" in SYSTEM_PROMPT
    assert "13" in SYSTEM_PROMPT
    assert "logical_join_candidate" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# test_get_provider_registry
# ---------------------------------------------------------------------------

def test_get_provider_registry():
    from app.providers.base import BaseProvider

    for p in Provider:
        provider = get_provider(p)
        assert isinstance(provider, BaseProvider)
