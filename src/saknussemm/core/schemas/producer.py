"""What a producer is asked, what it answers, and what it can do.

The payload models (§5.1) plus the provider-facing descriptors: images,
line context, proposals, model capabilities and token usage.
"""

from __future__ import annotations


from pydantic import BaseModel, ConfigDict, Field

from saknussemm.core.schemas.manifest import ChunkGranularity, Coords


# ``Provider``, ``JobStatus`` and ``JobManifest`` (with its ``images`` map)
# are server-side concepts and live in the consumer package — see
# ``app.schemas.job`` in the backend. The core does not enumerate
# LLM vendors or track a job's lifecycle.


# ---------------------------------------------------------------------------
# LLM payload models
# ---------------------------------------------------------------------------


#: Opaque page-image reference (§4.1/§5.1). The library forwards it
#: verbatim from ``run(page_images=…)`` into the payload and NEVER opens
#: it — resolving/cropping/encoding pixels is the vision producer's job
#: (invariant I4). Kept a bare ``str`` (path, URL, handle) so the core
#: carries no image machinery.
ImageRef = str


class ImageTransform(BaseModel):
    """XML-coordinate-space → image-pixel mapping.

    ALTO/PAGE geometry is expressed in the coordinate system the OCR
    engine used, which is not always the scan's native pixel grid: an
    ALTO ``MeasurementUnit`` may be ``mm10``/``inch1200`` rather than
    ``pixel``, or the page may have been downscaled before OCR. To crop a
    line/block from the image a vision producer must map ``(hpos, vpos,
    width, height)`` from XML space into pixels; this value object carries
    the axis-aligned part of that map — scale then offset, applied as
    ``px = scale * xml + offset`` on each axis.

    The core only *carries* the transform (invariant I4 — it never opens a
    pixel); the ``saknussemm[vision]`` producer applies it. Rotation
    beyond EXIF orientation (see :attr:`ImageAsset.exif_orientation`) is
    out of scope for v1: the common mismatch is a pure resolution scale.
    Identity (all defaults) means the OCR ran at the image's native
    resolution — the overwhelmingly common case.
    """

    scale_x: float = Field(default=1.0, gt=0.0)
    scale_y: float = Field(default=1.0, gt=0.0)
    offset_x: float = 0.0
    offset_y: float = 0.0


class ImageAsset(BaseModel):
    """Structured page-image descriptor (§4.1 / the vision/QE programme).

    The RECOMMENDED value for ``run(page_images=…)``: a bare
    :data:`ImageRef` (str) is still accepted, but an ``ImageAsset`` carries
    the provenance the audit trail wants — the SHA-256 of the exact bytes,
    the real decoded MIME type and pixel dimensions, the frame index inside
    a multipage container, the EXIF orientation — plus the XML→pixel
    :class:`ImageTransform` a crop needs. It rides the §4.1 envelope exactly
    where the bare ref did: the compiler copies it into
    :attr:`CorrectionRequest.image_ref` only when the producer asks
    (``wants_image``), and forwards it verbatim.

    The core stays pixel-blind (invariant I4): it NEVER opens
    :attr:`uri` to populate these fields — it only carries them. The opt-in
    ``saknussemm[vision]`` builder decodes the image and fills them in; a
    caller may also construct one by hand from metadata it already holds.
    Only :attr:`page_id` and :attr:`uri` are required; every decoded field
    is ``None`` until something that actually read the bytes sets it, so a
    metadata-poor asset degrades to "a ref that also knows its page".
    """

    #: The page this scan belongs to — matches a ``PageManifest.page_id``.
    #: When an asset is used as a ``page_images`` value, this MUST equal
    #: its mapping key (``require_page_images`` enforces it): a scan filed
    #: under the wrong page is exactly the silent wrong-image bug the
    #: per-page contract exists to prevent.
    page_id: str
    #: Opaque locator the vision producer resolves (path, URL, handle),
    #: forwarded verbatim; the core never opens it (I4) — same contract as
    #: a bare :data:`ImageRef`.
    uri: str
    #: SHA-256 of the exact image bytes, lowercase hex — the provenance
    #: anchor stamped alongside the crop hash (acceptance criterion 5).
    #: ``None`` when the caller has not hashed the bytes.
    sha256: str | None = None
    #: Decoded MIME type (``image/tiff``, ``image/jpeg``, …), determined
    #: from the bytes rather than guessed from the extension. ``None`` when
    #: unknown.
    media_type: str | None = None
    #: Decoded pixel dimensions of the frame this asset points at. These
    #: are the IMAGE's pixels — the XML page dimensions may differ (see
    #: :attr:`transform`). ``None`` when unknown.
    pixel_width: int | None = Field(default=None, gt=0)
    pixel_height: int | None = Field(default=None, gt=0)
    #: 0-based frame index inside a multi-frame container (multipage TIFF);
    #: ``0`` for a single-image file.
    frame_index: int = Field(default=0, ge=0)
    #: EXIF orientation tag (1–8) as stored in the file; the vision builder
    #: applies it when cropping. ``None`` when the file carries none.
    exif_orientation: int | None = Field(default=None, ge=1, le=8)
    #: How to map XML coordinates onto image pixels. ``None`` is read as
    #: identity (native-resolution OCR).
    transform: ImageTransform | None = None


#: What ``run(page_images=…)`` accepts per page: the historical opaque
#: :data:`ImageRef` (str) OR the richer, recommended :class:`ImageAsset`.
#: Both ride the §4.1 envelope identically; the core forwards either
#: verbatim and opens neither (I4).
PageImage = ImageRef | ImageAsset


class LineGeometry(BaseModel):
    """Physical anchor for a line, copied verbatim by the compiler for
    vision producers (§4.1): the line ``coords`` (ALTO bbox or PAGE polygon)
    plus the page dimensions, enough to compute a unit-free relative bbox.
    The library only *copies* these fields; it touches no pixel."""

    coords: Coords
    page_width: int
    page_height: int


class LineContext(BaseModel):
    """One line worth of context sent to the LLM (OCR text + neighbours + hyphen hints)."""

    line_id: str
    prev_text: str | None = None
    ocr_text: str
    next_text: str | None = None
    # Hyphenation fields — absent when hyphen_role == NONE
    hyphenation_role: str | None = None
    hyphen_candidate: bool | None = None
    hyphen_join_with_next: bool | None = None
    hyphen_join_with_prev: bool | None = None
    backward_join_candidate: str | None = None
    forward_join_candidate: str | None = None
    # Vision envelope (§4.1) — populated by the compiler only when the
    # producer asks (``wants_geometry``); ignored by text producers.
    geometry: LineGeometry | None = None


class CorrectionRequest(BaseModel):
    task: str = "correct_ocr_lines"
    granularity: ChunkGranularity
    document_id: str
    page_id: str
    block_id: str | None = None
    lines: list[LineContext]
    # Vision envelope (§4.1) — page image, populated by the compiler only
    # when the producer asks (``wants_image``); never opened. Either the
    # historical opaque :data:`ImageRef` (str) or the richer, recommended
    # :class:`ImageAsset` (:data:`PageImage`), forwarded verbatim.
    image_ref: PageImage | None = None


class LineProposal(BaseModel):
    """One corrected line returned by the LLM — paired by ``line_id`` with its input."""

    line_id: str
    corrected_text: str


class ProposalBatch(BaseModel):
    lines: list[LineProposal]


# ---------------------------------------------------------------------------
# Provider / model info
# ---------------------------------------------------------------------------


class ModelInfo(BaseModel):
    """An LLM model description as returned by ``BaseProvider.list_models``."""

    id: str
    label: str
    supports_structured_output: bool = True
    context_window: int | None = None


class ModelCapabilities(BaseModel):
    """What a producer's model can do (the vision/QE programme, §5.2 bis).

    The declarative descriptor the Router reads to send each line only to a
    producer that can actually serve it — the mechanism by which a VLM is
    "just another producer", routed to the lines where it earns its cost
    rather than hardwired for the whole run. A producer MAY declare its own
    via a ``capabilities`` attribute (the same optional-attribute
    convention as ``metadata`` / ``requires_full_coverage``); absent means
    "undeclared, no constraint" (back-compatible).

    ``ModelInfo`` is the CATALOG face of a model (what ``list_models``
    lists, a host concern); this is the ROUTING face (what the brain
    checks per line). They overlap on ``structured_output`` / ``context``
    by design — a host can build one from the other.

    Frozen so a chosen model's capabilities are a stable fact a run can
    record. The brain is :meth:`can_serve`; it INFORMS the Router, it does
    not decide (the app decides).
    """

    model_config = ConfigDict(frozen=True)

    #: Can correct from text (OCR + neighbours). Almost always True.
    text: bool = True
    #: Can consume page images — the gate a vision producer needs.
    vision: bool = False
    #: Supports structured JSON output (the shape every LLM producer here
    #: asks for). A model without it cannot serve the structured contract.
    structured_output: bool = True
    #: Maximum images the model accepts per call; ``None`` = unbounded.
    #: A vision chunk that would send more crops than this cannot be served
    #: as one call — the Router/planner must split it (or route elsewhere).
    max_images: int | None = Field(default=None, ge=0)
    #: Context window in tokens, when known; ``None`` = unspecified.
    context: int | None = Field(default=None, gt=0)

    def reason_cannot_serve(
        self,
        *,
        needs_image: bool = False,
        needs_structured_output: bool = False,
        image_count: int = 0,
    ) -> str | None:
        """Why this model cannot serve a request, or ``None`` when it can.

        A short human-readable reason (the same string a preflight error
        or a routing log would carry), so the Router can both DECIDE
        (``can_serve``) and EXPLAIN the exclusion in one call.
        """
        if needs_image and not self.vision:
            return "model has no vision capability"
        if needs_structured_output and not self.structured_output:
            return "model does not support structured output"
        if self.max_images is not None and image_count > self.max_images:
            return f"needs {image_count} images but model caps at {self.max_images}"
        return None

    def can_serve(
        self,
        *,
        needs_image: bool = False,
        needs_structured_output: bool = False,
        image_count: int = 0,
    ) -> bool:
        """True when the model can serve the described request (see
        :meth:`reason_cannot_serve`)."""
        return (
            self.reason_cannot_serve(
                needs_image=needs_image,
                needs_structured_output=needs_structured_output,
                image_count=image_count,
            )
            is None
        )


class Usage(BaseModel):
    """Token consumption reported by a producer call (§5.1).

    Returned alongside the JSON payload by ``complete_structured`` so the
    pipeline can aggregate cost across a run and surface it on the report
    and events. A producer that cannot report tokens returns ``None``
    instead of a ``Usage``; consumers map these onto their own resource
    accounting.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    #: §11 — vendor response identifiers, when the provider surfaces one
    #: (OpenAI/Mistral/Anthropic ``id``, Gemini ``responseId``). They ride
    #: the same producer→pipeline→report path as the token counts and
    #: aggregate by concatenation (call order), so a report names every
    #: provider response that contributed to the run.
    response_ids: list[str] = Field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            response_ids=[*self.response_ids, *other.response_ids],
        )


# HTTP DTOs (ListModelsRequest/Response, CreateJobResponse,
# JobStatusResponse, SSEEvent) live in the consumer package — see
# `app.schemas.http` in the backend. Server-layer payloads stay out of the
# library: it assumes no execution environment and no transport (§15).
