"""Mistral provider implementation."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.schemas import ModelInfo

_BASE = "https://api.mistral.ai"


class MistralProvider:
    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
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
            caps = m.get("capabilities", {})
            if not caps.get("completion_chat", False):
                continue
            mid = m.get("id", "")
            label = m.get("name") or mid
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
        body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": json_schema,
            },
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE}/v1/chat/completions",
                headers=self._headers(api_key),
                json=body,
                timeout=120,
            )

            if resp.status_code in (400, 422):
                # Fallback: json_object instead of json_schema
                body_fallback = {**body, "response_format": {"type": "json_object"}}
                resp = await client.post(
                    f"{_BASE}/v1/chat/completions",
                    headers=self._headers(api_key),
                    json=body_fallback,
                    timeout=120,
                )

            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
