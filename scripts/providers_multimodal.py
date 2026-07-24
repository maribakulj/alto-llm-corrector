"""Multimodal clients — real VLMs behind the vision seam.

Each class implements
``corrigenda.integrations.vision.MultimodalStructuredClient`` so
``VisionEditProducer`` can drive an actual model instead of the oracle
stand-in the benchmark uses. This is TOOLING, not library API: vendor
specifics stay out of the pixel-blind core, and out of the demo backend
(whose providers are text-only). Promoting provider adapters into
``corrigenda[anthropic|mistral|…]`` is a Phase-5 roadmap item; this is the
runnable path until then.

* :class:`AnthropicMultimodalClient` — Claude, via the official SDK.
* :class:`MistralMultimodalClient` — Pixtral / multimodal Mistral models,
  via the same raw HTTP shape the demo backend's text provider uses.

**API keys are read from the environment and never accepted as a CLI
flag** (a flag lands in shell history and in the process list). They are
never printed and never written to the corrected artefacts; provider
errors additionally route through :func:`corrigenda.sanitize_error`, which
redacts the key and common secret-shaped substrings.

Two API details these adapters exist to get right:

* **Structured output** is requested natively — ``output_config.format``
  on Anthropic, ``response_format: json_schema`` on Mistral — so the reply
  parses without a forced-tool-call trick.
* **``temperature`` is REJECTED (HTTP 400) on current Claude models** —
  Opus 5, Opus 4.8/4.7, Sonnet 5, Fable/Mythos. The engine's retry ramp
  (0.0 → 0.3 → 0.5) therefore cannot be forwarded there: the adapter drops
  it for those models and says so, rather than 400-ing every retry or
  silently pretending the ramp took effect. On such a model a retry is
  byte-identical to the attempt before it — a real limitation of the
  engine's ramp, made visible instead of hidden. Mistral accepts
  ``temperature``, so the ramp applies normally there.

Requires ``pip install anthropic`` (Claude) or ``httpx`` (Mistral), and the
matching key in the environment: ``ANTHROPIC_API_KEY`` / ``MISTRAL_API_KEY``.
"""

from __future__ import annotations

import base64
import json
from typing import Any

#: Models that reject `temperature` outright (HTTP 400). Substring match on
#: the model id, mirroring the demo backend's own list — plus ``opus-5``,
#: which that list predates.
_NO_TEMPERATURE = ("opus-5", "opus-4-7", "opus-4-8", "sonnet-5", "fable", "mythos")

#: Conservative per-call output ceiling. Line corrections are short; the
#: cost of under-budgeting is a truncated JSON body and a retry storm, so
#: this is generous relative to the payload rather than tight.
_MAX_TOKENS_FLOOR = 4096
_MAX_TOKENS_PER_LINE = 256
_MAX_TOKENS_CAP = 16000


def supports_temperature(model: str) -> bool:
    """False when the model rejects ``temperature`` (400)."""
    lowered = model.lower()
    return not any(marker in lowered for marker in _NO_TEMPERATURE)


def _max_tokens_for(user_payload: dict[str, Any]) -> int:
    lines = user_payload.get("lines")
    count = len(lines) if isinstance(lines, list) else 0
    return min(_MAX_TOKENS_CAP, max(_MAX_TOKENS_FLOOR, count * _MAX_TOKENS_PER_LINE))


class AnthropicMultimodalClient:
    """A ``MultimodalStructuredClient`` backed by the Anthropic Messages API.

    Sends one message per call: the line crops as image blocks, each
    labelled with its ``line_id`` so the model can tie a picture to a line,
    followed by the OCR payload as text. The reply is constrained to the
    caller's JSON schema via ``output_config.format``.

    ``dropped_temperature`` records whether the engine's retry ramp was
    discarded (see the module docstring), so a caller can report it instead
    of assuming the ramp ran.
    """

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client
        self.dropped_temperature = False
        self.calls = 0

    def _ensure_client(self, api_key: str) -> Any:
        if self._client is None:
            from anthropic import AsyncAnthropic  # lazy: tooling-only dep

            # An explicit key wins; otherwise let the SDK resolve its own
            # credentials (env var, or an `ant auth login` profile).
            self._client = (
                AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()
            )
        return self._client

    def _content_blocks(self, user_payload: dict[str, Any], images: list) -> list:
        blocks: list[dict[str, Any]] = []
        for part in images:
            blocks.append(
                {
                    "type": "text",
                    "text": f"Image de la ligne {part.line_id} :",
                }
            )
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": part.media_type,
                        "data": base64.standard_b64encode(part.data).decode("ascii"),
                    },
                }
            )
        blocks.append(
            {
                "type": "text",
                "text": json.dumps(user_payload, ensure_ascii=False),
            }
        )
        return blocks

    async def complete_structured_multimodal(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        images: list,
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Any]:
        from corrigenda.core.schemas import Usage

        client = self._ensure_client(api_key)
        self.calls += 1

        request: dict[str, Any] = {
            "model": model,
            "max_tokens": _max_tokens_for(user_payload),
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": self._content_blocks(user_payload, images),
                }
            ],
            # The API enforces the shape, so the reply needs no repair.
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": json_schema.get("schema", json_schema),
                }
            },
        }
        if supports_temperature(model):
            request["temperature"] = temperature
        elif temperature:
            # The engine's ramp cannot apply here; record it rather than
            # letting the caller believe a hotter retry happened.
            self.dropped_temperature = True

        message = await client.messages.create(**request)

        if getattr(message, "stop_reason", None) == "refusal":
            # A safety decline is a real outcome, not a parse failure: no
            # content to read. Surfacing it as an empty result lets the
            # pipeline's validator fall the chunk back to OCR text.
            return {"lines": []}, None

        text = next(
            (b.text for b in message.content if getattr(b, "type", None) == "text"),
            "",
        )
        parsed = json.loads(text) if text else {"lines": []}

        usage_obj = getattr(message, "usage", None)
        usage = None
        if usage_obj is not None:
            usage = Usage(
                input_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                output_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                response_ids=[message.id] if getattr(message, "id", None) else [],
            )
        return parsed, usage


class MistralMultimodalClient:
    """A ``MultimodalStructuredClient`` backed by Mistral's chat API.

    Same raw-HTTP shape the demo backend's text provider uses
    (``POST /v1/chat/completions``), extended with the vision content
    blocks a multimodal Mistral model (Pixtral, and the multimodal
    ``mistral-*`` tiers) accepts: images ride as ``image_url`` blocks
    carrying a ``data:`` URI.

    Structured output asks for ``response_format: json_schema`` and falls
    back to ``json_object`` when the model rejects the stricter form —
    the same two-step the backend already relies on for text.

    The key is passed in from the caller's environment and only ever
    travels in the ``Authorization`` header; it is never logged, never
    included in the request body, and never written to an artefact.
    """

    #: Model IDs are NOT hardcoded beyond this default — Mistral's catalog
    #: moves, and guessing an ID yields a 404. ``list_models`` (below)
    #: queries the live catalog with the caller's own key.
    DEFAULT_MODEL = "pixtral-12b-2409"

    _BASE = "https://api.mistral.ai"

    def __init__(self, *, transport: Any | None = None, timeout: float = 120.0) -> None:
        self._transport = transport
        self._timeout = timeout
        self.dropped_temperature = False
        self.calls = 0

    async def list_models(self, api_key: str) -> list[str]:
        """Live model IDs for this key — so a caller can pick a real
        multimodal model instead of trusting a hardcoded guess."""
        import httpx

        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport
        ) as http:
            resp = await http.get(
                f"{self._BASE}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [m["id"] for m in data.get("data", []) if "id" in m]

    def _content_blocks(self, user_payload: dict[str, Any], images: list) -> list:
        blocks: list[dict[str, Any]] = []
        for part in images:
            blocks.append(
                {"type": "text", "text": f"Image de la ligne {part.line_id} :"}
            )
            encoded = base64.standard_b64encode(part.data).decode("ascii")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": f"data:{part.media_type};base64,{encoded}",
                }
            )
        blocks.append(
            {"type": "text", "text": json.dumps(user_payload, ensure_ascii=False)}
        )
        return blocks

    async def complete_structured_multimodal(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        images: list,
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Any]:
        import httpx

        from corrigenda.core.schemas import Usage

        self.calls += 1
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": _max_tokens_for(user_payload),
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": self._content_blocks(user_payload, images),
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": json_schema},
        }
        if supports_temperature(model):
            body["temperature"] = temperature
        elif temperature:
            self.dropped_temperature = True

        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport
        ) as http:
            resp = await http.post(
                f"{self._BASE}/v1/chat/completions", json=body, headers=headers
            )
            if resp.status_code == 400:
                # Model rejected the strict schema — retry with the looser
                # json_object mode, exactly as the backend's text path does.
                loose = {**body, "response_format": {"type": "json_object"}}
                resp = await http.post(
                    f"{self._BASE}/v1/chat/completions", json=loose, headers=headers
                )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        text = choices[0]["message"]["content"] if choices else ""
        parsed = json.loads(text) if text else {"lines": []}

        raw_usage = data.get("usage") or {}
        usage = None
        if raw_usage:
            usage = Usage(
                input_tokens=int(raw_usage.get("prompt_tokens", 0) or 0),
                output_tokens=int(raw_usage.get("completion_tokens", 0) or 0),
                response_ids=[data["id"]] if data.get("id") else [],
            )
        return parsed, usage


__all__ = [
    "AnthropicMultimodalClient",
    "MistralMultimodalClient",
    "supports_temperature",
]
