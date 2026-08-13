"""Splitting an image-bearing chunk so no single call exceeds the cap.

A vision producer crops EVERY line of the chunk it receives, so a chunk's
line count IS its image count, and providers cap that per call. This is where
the app acts on the capability the descriptor already declared.

Free functions rather than pipeline methods: the only thing they ever
needed from the engine was the producer they were handed. Splitting is a
property of a chunk and a cap, not of a run.
"""

from __future__ import annotations

from corrigenda.core.protocols import EditProducer
from corrigenda.core.reconcile import _units_visible_on_page
from corrigenda.core.schemas import ChunkRequest, HyphenRole, LineManifest
from corrigenda.errors import ConfigurationError


def _image_cap(producer: EditProducer) -> int | None:
    """The producer's per-call image ceiling, or ``None`` when it has
    none (undeclared, or the producer sends no images at all)."""
    if not getattr(producer, "wants_image", False):
        return None
    capabilities = getattr(producer, "capabilities", None)
    if capabilities is None:
        return None
    cap: int | None = getattr(capabilities, "max_images", None)
    return cap


def _split_for_image_cap(
    *,
    routed: list[tuple[ChunkRequest, EditProducer]],
    line_by_id: dict[str, LineManifest],
) -> list[tuple[ChunkRequest, EditProducer]]:
    """Split image-bearing chunks so no single call exceeds the
    producer's ``ModelCapabilities.max_images``.

    A vision producer crops EVERY line of the chunk it receives, so a
    chunk's line count IS its image count. Providers cap that per call
    (Mistral rejects a 9th image with HTTP 400 ``"Total number of
    images exceeds the maximum allowed of 8"``) — an error no retry
    and no granularity downgrade can heal, because the downgrade ladder
    reacts to malformed OUTPUT, not to a request refused outright.

    The descriptor already described the limit (`max_images`) and
    already explained it (`reason_cannot_serve`); this is where the app
    acts on it. Splitting rather than failing keeps the capability a
    routing input instead of a hard stop.

    Sibling chunks carry only the lines they correct, plus any hyphen
    partner already in the parent chunk — a unit is never severed
    (atomicity), so the pair still reaches one producer in one call and
    reconciles normally. Textual context is NOT lost by the split:
    ``prev_text``/``next_text`` are resolved against the whole page,
    not against the chunk's own membership.

    ``max_images=None`` (the default) skips all of this, so an
    undeclared cap leaves every existing run byte-identical.
    """
    out: list[tuple[ChunkRequest, EditProducer]] = []
    page_units: dict[str, set[str]] | None = None
    for chunk, producer in routed:
        cap = _image_cap(producer)
        if cap is None or len(chunk.line_ids) <= cap:
            out.append((chunk, producer))
            continue
        # Derived on the first chunk that needs it, then reused: the
        # units are a property of the page, not of the chunk, and the
        # common case (no cap declared) must not pay for them at all.
        # Visible members, not COMPLETE units: see the helper — the
        # batcher cannot "leave a unit alone", so an incomplete one has
        # to be held together rather than dissolved into singletons.
        if page_units is None:
            page_units = _units_visible_on_page(line_by_id)

        targets = set(chunk.targets())
        in_chunk = set(chunk.line_ids)
        batches: list[list[str]] = []
        current: list[str] = []
        assigned: set[str] = set()

        for line_id in chunk.line_ids:
            if line_id in assigned or line_id not in targets:
                continue
            lm = line_by_id.get(line_id)
            unit: set[str] = {line_id}
            if lm is not None and lm.hyphen_role is not HyphenRole.NONE:
                # Both members ride together — and a member that is
                # context here (target of an adjacent chunk) still
                # travels, because the reconciler needs the whole pair.
                # A unit this page can only partly see (its far member is
                # on another page, or a pointer dangles) still keeps the
                # members that ARE here in one call.
                resolved = page_units.get(line_id)
                if resolved is not None:
                    unit = (resolved & in_chunk) - assigned
            members = [lid for lid in chunk.line_ids if lid in unit]
            if len(members) > cap:
                raise ConfigurationError(
                    f"hyphen unit {sorted(members)!r} needs {len(members)} "
                    f"images in one call but the producer's max_images is "
                    f"{cap}: a unit cannot be split across calls "
                    "(atomicity). Raise max_images or route these lines "
                    "to a text producer."
                )
            if current and len(current) + len(members) > cap:
                batches.append(current)
                current = []
            current.extend(members)
            assigned |= set(members)
        if current:
            batches.append(current)

        for index, batch in enumerate(batches):
            batch_targets = [lid for lid in batch if lid in targets]
            out.append(
                (
                    chunk.model_copy(
                        update={
                            "line_ids": batch,
                            "target_line_ids": batch_targets,
                            "chunk_id": f"{chunk.chunk_id}#img{index}",
                        }
                    ),
                    producer,
                )
            )
    return out
