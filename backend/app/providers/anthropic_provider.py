"""Anthropic provider implementation."""
from __future__ import annotations

import json
from typing import Any

import httpx

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
        # Build the schema payload (unwrap outer "name"/"strict"/"schema" if present)
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

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE}/v1/messages",
                headers=self._headers(api_key),
                json=body,
                timeout=120,
            )

            if resp.status_code in (400, 422):
                # Fallback: drop output_config, rely on system prompt
                body_fallback = {k: v for k, v in body.items() if k != "output_config"}
                resp = await client.post(
                    f"{_BASE}/v1/messages",
                    headers=self._headers(api_key),
                    json=body_fallback,
                    timeout=120,
                )

            resp.raise_for_status()
            data = resp.json()

        content = data["content"][0]["text"]
        return json.loads(content)
