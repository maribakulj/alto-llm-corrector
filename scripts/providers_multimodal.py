"""Anthropic multimodal client — a real VLM behind the vision seam.

Implements ``corrigenda.integrations.vision.MultimodalStructuredClient`` so
``VisionEditProducer`` can drive an actual Claude model instead of the
oracle stand-in the benchmark uses. It is TOOLING, not library API: vendor
specifics stay out of the pixel-blind core, and out of the demo backend
(whose providers are text-only). Promoting provider adapters into
``corrigenda[anthropic|openai|…]`` is a Phase-5 roadmap item; this is the
runnable path until then.

Two API details this adapter exists to get right:

* **Structured output** uses ``output_config.format`` (a JSON schema the
  API enforces), so the reply parses without the forced-tool-call trick.
* **``temperature`` is REJECTED (HTTP 400) on current models** — Opus 5,
  Opus 4.8/4.7, Sonnet 5, Fable/Mythos. The engine's retry ramp
  (0.0 → 0.3 → 0.5) therefore cannot be forwarded: this adapter drops it
  for those models and says so on the result, rather than 400-ing every
  retry or silently pretending the ramp took effect. On such a model a
  retry is byte-identical to the attempt before it — a real limitation of
  the engine's ramp, made visible instead of hidden.

Requires ``pip install anthropic`` and an API key
(``ANTHROPIC_API_KEY``, or any credential the SDK resolves).
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


__all__ = ["AnthropicMultimodalClient", "supports_temperature"]
