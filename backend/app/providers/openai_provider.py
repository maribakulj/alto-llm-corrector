"""OpenAI provider implementation."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.schemas import ModelInfo

_BASE = "https://api.openai.com"

_ALLOWLIST_PREFIXES = ("gpt-4", "gpt-3.5", "o1", "o3", "o4")
_DENYLIST_PATTERNS = (
    "instruct",
    "embedding",
    "whisper",
    "tts",
    "dall-e",
    "moderation",
    "realtime",
    "audio",
)


def _keep_model(model_id: str) -> bool:
    mid = model_id.lower()
    if not any(mid.startswith(p) for p in _ALLOWLIST_PREFIXES):
        return False
    if any(d in mid for d in _DENYLIST_PATTERNS):
        return False
    return True


class OpenAIProvider:
    async def list_models(self, api_key: str) -> list[ModelInfo]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if _keep_model(mid):
                models.append(ModelInfo(id=mid, label=mid))
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
        body = {
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
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
