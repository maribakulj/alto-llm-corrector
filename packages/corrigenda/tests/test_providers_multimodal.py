"""Multimodal clients (scripts/providers_multimodal.py).

Offline: a stub SDK (Anthropic) and a mock transport (Mistral) stand in for
the network, so the request each adapter BUILDS is asserted without a call
or an API key. What matters here is the wire shape — image blocks,
structured-output config, the temperature gate that keeps current Claude
models from 400-ing, and the invariant that a key never leaves the
Authorization header.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "providers_multimodal.py"

_spec = importlib.util.spec_from_file_location("providers_multimodal", _SCRIPT)
assert _spec and _spec.loader
pm = importlib.util.module_from_spec(_spec)
sys.modules["providers_multimodal"] = pm
_spec.loader.exec_module(pm)

from corrigenda.integrations.vision import ImagePart  # noqa: E402


class _StubSDK:
    """Captures the request and returns a canned structured reply."""

    def __init__(self, reply: dict | None = None, stop_reason: str = "end_turn"):
        self.seen: dict = {}
        self._reply = reply if reply is not None else {"lines": []}
        self._stop_reason = stop_reason
        outer = self

        class _Messages:
            async def create(self, **kwargs):
                outer.seen = kwargs
                return outer._message()

        self.messages = _Messages()

    def _message(self):
        reply_json = json.dumps(self._reply)
        stop = self._stop_reason

        class _Block:
            type = "text"
            text = reply_json

        class _Usage:
            input_tokens = 11
            output_tokens = 5

        class _Message:
            id = "msg_stub"
            stop_reason = stop
            usage = _Usage()
            content = [_Block()]

        return _Message()


def _call(client, *, model="claude-opus-5", temperature=0.0, images=None, payload=None):
    return asyncio.run(
        client.complete_structured_multimodal(
            api_key="key",
            model=model,
            system_prompt="sys",
            user_payload=payload
            or {"lines": [{"line_id": "l1", "ocr_text": "Bonjovr"}]},
            images=images if images is not None else [_part("l1")],
            json_schema={"name": "x", "schema": {"type": "object"}},
            temperature=temperature,
        )
    )


def _part(line_id: str, data: bytes = b"\x89PNG-fake") -> ImagePart:
    return ImagePart(
        line_id=line_id, media_type="image/png", data=data, sha256="ab" * 32
    )


# ---------------------------------------------------------------------------
# The temperature gate — the reason this adapter exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-sonnet-5",
        "claude-fable-5",
        "claude-mythos-5",
    ],
)
def test_models_that_reject_temperature(model):
    assert pm.supports_temperature(model) is False


@pytest.mark.parametrize("model", ["claude-haiku-4-5", "claude-sonnet-4-5"])
def test_models_that_accept_temperature(model):
    assert pm.supports_temperature(model) is True


def test_temperature_is_dropped_for_rejecting_models():
    """Forwarding it would 400 every retry of the engine's ramp."""
    sdk = _StubSDK()
    client = pm.AnthropicMultimodalClient(client=sdk)
    _call(client, model="claude-opus-5", temperature=0.3)
    assert "temperature" not in sdk.seen
    # The dropped ramp is recorded, not silently swallowed.
    assert client.dropped_temperature is True


def test_temperature_is_forwarded_when_supported():
    sdk = _StubSDK()
    client = pm.AnthropicMultimodalClient(client=sdk)
    _call(client, model="claude-haiku-4-5", temperature=0.3)
    assert sdk.seen["temperature"] == 0.3
    assert client.dropped_temperature is False


def test_zero_temperature_is_not_reported_as_dropped():
    """attempt 1 is 0.0 — nothing was lost, so don't claim it was."""
    sdk = _StubSDK()
    client = pm.AnthropicMultimodalClient(client=sdk)
    _call(client, model="claude-opus-5", temperature=0.0)
    assert client.dropped_temperature is False


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


def test_crops_travel_as_base64_image_blocks_labelled_by_line():
    sdk = _StubSDK()
    client = pm.AnthropicMultimodalClient(client=sdk)
    _call(client, images=[_part("l1", b"AAA"), _part("l2", b"BBB")])

    blocks = sdk.seen["messages"][0]["content"]
    images = [b for b in blocks if b["type"] == "image"]
    assert len(images) == 2
    assert base64.standard_b64decode(images[0]["source"]["data"]) == b"AAA"
    assert images[0]["source"]["media_type"] == "image/png"
    # Each crop is labelled with its line_id so the model can tie picture
    # to line, and the OCR payload is the final block.
    labels = [b["text"] for b in blocks if b["type"] == "text"]
    assert any("l1" in t for t in labels) and any("l2" in t for t in labels)
    assert json.loads(blocks[-1]["text"])["lines"][0]["line_id"] == "l1"


def test_uses_structured_output_not_a_forced_tool_call():
    sdk = _StubSDK()
    client = pm.AnthropicMultimodalClient(client=sdk)
    _call(client)
    fmt = sdk.seen["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"] == {"type": "object"}  # unwrapped from the envelope
    assert "tools" not in sdk.seen


def test_max_tokens_scales_with_line_count():
    sdk = _StubSDK()
    client = pm.AnthropicMultimodalClient(client=sdk)
    many = {"lines": [{"line_id": f"l{i}", "ocr_text": "x"} for i in range(60)]}
    _call(client, payload=many, images=[])
    assert sdk.seen["max_tokens"] > pm._MAX_TOKENS_FLOOR
    assert sdk.seen["max_tokens"] <= pm._MAX_TOKENS_CAP


# ---------------------------------------------------------------------------
# Response handling
# ---------------------------------------------------------------------------


def test_parses_reply_and_usage():
    sdk = _StubSDK({"lines": [{"line_id": "l1", "corrected_text": "Bonjour"}]})
    client = pm.AnthropicMultimodalClient(client=sdk)
    parsed, usage = _call(client)
    assert parsed["lines"][0]["corrected_text"] == "Bonjour"
    assert usage.input_tokens == 11 and usage.output_tokens == 5
    assert usage.response_ids == ["msg_stub"]


def test_refusal_returns_no_lines_rather_than_crashing():
    """A safety decline is a real outcome with no content to read; an empty
    result lets the pipeline fall the chunk back to OCR text."""
    sdk = _StubSDK({"lines": []}, stop_reason="refusal")
    client = pm.AnthropicMultimodalClient(client=sdk)
    parsed, usage = _call(client)
    assert parsed == {"lines": []}
    assert usage is None


# ---------------------------------------------------------------------------
# Mistral (Pixtral) — same seam, different wire shape
# ---------------------------------------------------------------------------

httpx = pytest.importorskip("httpx")

_OK_BODY = {
    "id": "cmpl-1",
    "usage": {"prompt_tokens": 50, "completion_tokens": 9},
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {"lines": [{"line_id": "l1", "corrected_text": "Bonjour"}]}
                )
            }
        }
    ],
}


def _mistral(handler):
    return pm.MistralMultimodalClient(transport=httpx.MockTransport(handler))


def _call_mistral(client, *, model="pixtral-12b-2409", temperature=0.0, api_key="K"):
    return asyncio.run(
        client.complete_structured_multimodal(
            api_key=api_key,
            model=model,
            system_prompt="sys",
            user_payload={"lines": [{"line_id": "l1", "ocr_text": "Bonjovr"}]},
            images=[_part("l1", b"\x89PNG!")],
            json_schema={"name": "x", "schema": {"type": "object"}},
            temperature=temperature,
        )
    )


def test_mistral_key_rides_only_the_auth_header():
    """The key must never reach the request BODY (bodies get logged and
    echoed far more casually than headers)."""
    seen: dict = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=_OK_BODY)

    _call_mistral(_mistral(handler), api_key="SECRET-abc123")
    assert seen["auth"] == "Bearer SECRET-abc123"
    assert "SECRET-abc123" not in seen["body"]


def test_mistral_sends_images_as_data_uri_blocks():
    seen: dict = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_OK_BODY)

    _call_mistral(_mistral(handler))
    blocks = seen["body"]["messages"][1]["content"]
    image = next(b for b in blocks if b["type"] == "image_url")
    prefix = "data:image/png;base64,"
    assert image["image_url"].startswith(prefix)
    assert base64.standard_b64decode(image["image_url"][len(prefix) :]) == b"\x89PNG!"
    # System prompt is its own message, OCR payload is the last text block.
    assert seen["body"]["messages"][0]["role"] == "system"
    assert json.loads(blocks[-1]["text"])["lines"][0]["line_id"] == "l1"


def test_mistral_forwards_temperature():
    """Unlike current Claude models, Mistral accepts it — so the engine's
    retry ramp actually applies here."""
    seen: dict = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_OK_BODY)

    client = _mistral(handler)
    _call_mistral(client, temperature=0.3)
    assert seen["body"]["temperature"] == 0.3
    assert client.dropped_temperature is False


def test_mistral_falls_back_to_json_object_on_400():
    """A model that rejects the strict schema still gets a usable request —
    the same two-step the demo backend's text path uses."""
    attempts: list[str] = []

    def handler(request):
        body = json.loads(request.content)
        attempts.append(body["response_format"]["type"])
        if len(attempts) == 1:
            return httpx.Response(400, json={"message": "schema unsupported"})
        return httpx.Response(200, json=_OK_BODY)

    parsed, _ = _call_mistral(_mistral(handler))
    assert attempts == ["json_schema", "json_object"]
    assert parsed["lines"][0]["corrected_text"] == "Bonjour"


def test_mistral_parses_usage():
    parsed, usage = _call_mistral(
        _mistral(lambda r: httpx.Response(200, json=_OK_BODY))
    )
    assert parsed["lines"][0]["corrected_text"] == "Bonjour"
    assert usage.input_tokens == 50 and usage.output_tokens == 9
    assert usage.response_ids == ["cmpl-1"]


def test_mistral_lists_live_models():
    """Model IDs are discovered with the caller's own key, not guessed."""

    def handler(request):
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200, json={"data": [{"id": "pixtral-12b-2409"}, {"id": "mistral-small"}]}
        )

    ids = asyncio.run(_mistral(handler).list_models("K"))
    assert ids == ["pixtral-12b-2409", "mistral-small"]
