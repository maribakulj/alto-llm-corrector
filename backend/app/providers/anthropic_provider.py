"""Anthropic provider implementation."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.base import call_llm
from app.schemas import ModelInfo

_BASE = "https://api.anthropic.com"
_VERSION = "2023-06-01"


class AnthropicProvider:
    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": _VERSION,
            "Content-Type": "application/json",
        }

    async def list_models(self, api_key: str) -> list[ModelInfo]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/v1/models",
                headers=self._headers(api_key),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            label = m.get("display_name") or mid
            models.append(ModelInfo(id=mid, label=label))
        models.sort(key=lambda m: m.id)
        return models

    async def complete_structured(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        schema_body = json_schema.get("schema", json_schema)

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 8192,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                }
            ],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "json_schema": schema_body,
                }
            },
        }
        fallback_body = {k: v for k, v in body.items() if k != "output_config"}

        data = await call_llm(
            url=f"{_BASE}/v1/messages",
            headers=self._headers(api_key),
            body=body,
            fallback_body=fallback_body,
        )

        blocks = data.get("content")
        if not blocks or not isinstance(blocks, list):
            raise ValueError(f"Anthropic response missing 'content': {list(data.keys())}")
        text = blocks[0].get("text")
        if not text:
            raise ValueError("Anthropic response has empty text in content[0]")
        return json.loads(text)
