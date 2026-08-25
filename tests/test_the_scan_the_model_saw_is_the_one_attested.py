"""The image a crop comes from must be the one the report attests.

``build_image_asset`` reads a file, hashes it, and puts the digest on the
asset. ``RunProvenance.image_digests`` then promises something specific:
that the digest, together with the per-line coordinates and the producer's
configuration fingerprint, **makes every crop reproducible** without
storing one hash per crop.

``crop_region`` reopened ``asset.uri`` and never checked it. So the promise
held only if nothing touched the file in between — and its docstring said
"pure and deterministic: identical inputs yield an identical sha256", of a
function whose input was a *path*.

Measured on 2026-08-17, swapping the file between the two calls:

    asset.sha256 (recorded in the report) : e8b42963fb4dbae2
    file actually opened by crop_region   : ec6297512ddb3c8d
    crop before / after the swap          : 4e32a320… / dc9c1fc8…

The report attested one scan while the model saw another. Nothing in the
artefact could distinguish the two, which is the whole difficulty: a wrong
crop does not look wrong, it looks like a different page.

**And the same call was reading the file once per line.** The producer
crops every line of a chunk, so a forty-line chunk read the same scan forty
times and verified it none. Reading once per chunk is what makes verifying
it cheap enough to be unconditional.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from saknussemm.core.schemas import Coords
from saknussemm.errors import ConfigurationError
from saknussemm.producers.vision import (
    build_image_asset,
    crop_region,
    verified_image_bytes,
)

_COORDS = Coords(hpos=10, vpos=10, width=60, height=20)


def _draw(path: Path, colour: tuple[int, int, int]) -> None:
    """A distinct solid image, so two files are never byte-identical."""
    from PIL import Image

    Image.new("RGB", (200, 100), colour).save(path, format="PNG")


def _asset_and_path() -> tuple[object, Path]:
    directory = Path(tempfile.mkdtemp())
    path = directory / "scan.png"
    _draw(path, (10, 20, 30))
    return build_image_asset("P1", path), path


def test_the_asset_really_carries_a_digest() -> None:
    """Without one there is nothing to verify, and every case below passes."""
    asset, path = _asset_and_path()
    assert asset.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()  # type: ignore[attr-defined]


def test_a_replaced_scan_is_refused_rather_than_cropped() -> None:
    asset, path = _asset_and_path()
    crop_region(asset, _COORDS)  # type: ignore[arg-type]

    _draw(path, (200, 100, 50))  # a different scan at the same path

    with pytest.raises(ConfigurationError, match="sha256"):
        crop_region(asset, _COORDS)  # type: ignore[arg-type]


def test_an_untouched_scan_still_crops(  # noqa: D401
) -> None:
    """The control: the refusal must be about the swap, not about cropping.

    And it asserts the crop is *stable*, which is the property the report
    actually promises — not merely that no exception was raised.
    """
    asset, _ = _asset_and_path()
    first = crop_region(asset, _COORDS)  # type: ignore[arg-type]
    second = crop_region(asset, _COORDS)  # type: ignore[arg-type]
    assert first.sha256 == second.sha256


def test_an_asset_without_a_digest_is_read_as_it_is() -> None:
    """The scope: the digest is optional, so its absence is not a failure.

    A caller may legitimately hold an asset built without hashing. Refusing
    there would turn a documented shape into an error, and the breakage
    would read as a stricter guard.
    """
    asset, path = _asset_and_path()
    unhashed = asset.model_copy(update={"sha256": None})  # type: ignore[attr-defined]
    _draw(path, (0, 0, 0))
    assert crop_region(unhashed, _COORDS).sha256  # type: ignore[arg-type]


def test_bytes_the_caller_already_holds_are_used_as_given() -> None:
    """``source_bytes`` is the seam that makes one read serve a whole chunk.

    It is also a different claim: the caller vouches for what they hold,
    where :func:`verified_image_bytes` vouches for a file. Cropping from
    those bytes must therefore not re-read the path — pinned here by
    deleting the file first.
    """
    asset, path = _asset_and_path()
    held = verified_image_bytes(asset)  # type: ignore[arg-type]
    path.unlink()
    assert crop_region(asset, _COORDS, source_bytes=held).sha256  # type: ignore[arg-type]
