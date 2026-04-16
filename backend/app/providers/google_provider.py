"""Google Gemini provider implementation."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.schemas import ModelInfo

_BASE = "https://generativelanguage.googleapis.com"
_EXCLUDE_KEYWORDS = ("embed", "aqa", "attribute")


def _keep_model(model: dict[str, Any]) -> bool:
    name: str = model.get("name", "")
    short = name.split("/")[-1].lower()
    if any(kw in short for kw in _EXCLUDE_KEYWORDS):
        return False
    methods = model.get("supportedGenerationMethods", [])
    return "generateContent" in methods


class GoogleProvider:
    async def list_models(self, api_key: str) -> list[ModelInfo]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/v1beta/models",
                params={"key": api_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        models = []
        for m in data.get("models", []):
            if not _keep_model(m):
                continue
            name: str = m.get("name", "")
            # name is "models/gemini-1.5-pro" — use the short form as id
            mid = name.split("/")[-1] if "/" in name else name
            label = m.get("displayName") or mid
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
        # Unwrap outer "name"/"strict"/"schema" envelope if present
        schema_body = json_schema.get("schema", json_schema)

        body: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": json.dumps(user_payload, ensure_ascii=False)}
                    ],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": schema_body,
            },
        }

        url = f"{_BASE}/v1beta/models/{model}:generateContent"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                params={"key": api_key},
                json=body,
                timeout=120,
            )

            if resp.status_code in (400, 422):
                # Fallback: drop responseSchema
                body_fallback = {
                    **body,
                    "generationConfig": {
                        k: v
                        for k, v in body["generationConfig"].items()
                        if k != "responseSchema"
                    },
                }
                resp = await client.post(
                    url,
                    params={"key": api_key},
                    json=body_fallback,
                    timeout=120,
                )

            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates")
        if not candidates or not isinstance(candidates, list):
            raise ValueError(f"Gemini response missing 'candidates': {list(data.keys())}")
        parts = candidates[0].get("content", {}).get("parts")
        if not parts or not isinstance(parts, list):
            raise ValueError("Gemini response has no parts in candidates[0].content")
        text = parts[0].get("text")
        if not text:
            raise ValueError("Gemini response has empty text in parts[0]")
        return json.loads(text)
