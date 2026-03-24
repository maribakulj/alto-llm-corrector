"""Provider registry."""
from __future__ import annotations

from app.schemas import Provider
from app.providers.base import BaseProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.mistral_provider import MistralProvider
from app.providers.google_provider import GoogleProvider

_REGISTRY: dict[Provider, BaseProvider] = {
    Provider.OPENAI: OpenAIProvider(),
    Provider.ANTHROPIC: AnthropicProvider(),
    Provider.MISTRAL: MistralProvider(),
    Provider.GOOGLE: GoogleProvider(),
}


def get_provider(provider: Provider) -> BaseProvider:
    return _REGISTRY[provider]


__all__ = [
    "BaseProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "MistralProvider",
    "GoogleProvider",
    "get_provider",
]
