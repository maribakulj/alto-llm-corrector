"""ModelCapabilities + require_capabilities (the vision/QE programme, §5.2 bis).

The declarative routing descriptor the Router reads to send each line only
to a producer that can serve it, and the start-up consistency gate the
engine owns for its single producer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from saknussemm.core.protocols import require_capabilities
from saknussemm.core.schemas import ModelCapabilities
from saknussemm.errors import ConfigurationError


def test_defaults_are_a_text_model():
    caps = ModelCapabilities()
    assert caps.text is True
    assert caps.vision is False
    assert caps.structured_output is True
    assert caps.max_images is None
    assert caps.context is None


def test_is_frozen():
    caps = ModelCapabilities()
    with pytest.raises(ValidationError):
        caps.vision = True  # type: ignore[misc]


def test_can_serve_vision_gate():
    text = ModelCapabilities(vision=False)
    vlm = ModelCapabilities(vision=True)
    assert not text.can_serve(needs_image=True)
    assert "vision" in (text.reason_cannot_serve(needs_image=True) or "")
    assert vlm.can_serve(needs_image=True)
    # A vision request without images is fine for either.
    assert text.can_serve(needs_image=False)


def test_can_serve_structured_output_gate():
    plain = ModelCapabilities(structured_output=False)
    assert not plain.can_serve(needs_structured_output=True)
    assert "structured" in (
        plain.reason_cannot_serve(needs_structured_output=True) or ""
    )
    assert ModelCapabilities().can_serve(needs_structured_output=True)


def test_can_serve_max_images_cap():
    capped = ModelCapabilities(vision=True, max_images=2)
    assert capped.can_serve(needs_image=True, image_count=2)
    assert not capped.can_serve(needs_image=True, image_count=3)
    reason = capped.reason_cannot_serve(needs_image=True, image_count=3)
    assert reason is not None and "3" in reason and "2" in reason
    # None = unbounded.
    assert ModelCapabilities(vision=True).can_serve(needs_image=True, image_count=999)


# ---------------------------------------------------------------------------
# require_capabilities — the engine's start-up consistency gate
# ---------------------------------------------------------------------------


class _Undeclared:
    wants_image = True  # but declares no capabilities → unconstrained


class _TextProducer:
    wants_image = False
    capabilities = ModelCapabilities(vision=False)


class _ConsistentVision:
    wants_image = True
    capabilities = ModelCapabilities(vision=True)


class _MisdeclaredVision:
    wants_image = True
    capabilities = ModelCapabilities(vision=False)  # contradicts wants_image


def test_require_capabilities_allows_undeclared():
    require_capabilities(_Undeclared())  # no raise — back-compatible


def test_require_capabilities_allows_consistent():
    require_capabilities(_TextProducer())
    require_capabilities(_ConsistentVision())


def test_require_capabilities_rejects_wants_image_without_vision():
    with pytest.raises(ConfigurationError, match="vision"):
        require_capabilities(_MisdeclaredVision())
