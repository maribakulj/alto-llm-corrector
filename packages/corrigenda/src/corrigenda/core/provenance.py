"""What a run records about its own inputs and dependencies (§11).

Helpers the orchestrator used to carry: which format adapter serves a
document, which dependency versions were installed, the digest of every
source file, and the assembled provenance record itself. None of them
touches run state (S2) — the record is a function of the run's inputs and
the identities it was configured with, which is exactly why it does not
need the engine to build it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from corrigenda.core.protocols import EditProducer, ProducerMetadata
from corrigenda.core.schemas import (
    DocumentManifest,
    ImageAsset,
    PageImage,
    ProducerProvenance,
    RunProvenance,
)


#: The dependencies whose installed version a run records.
_PROVENANCE_DEPENDENCIES = ("lxml", "pydantic")


def _dependency_versions() -> dict[str, str]:
    """Installed versions of the critical dependencies; a package that
    is not installed is simply absent (never an error — a core-only
    consumer legitimately runs without lxml)."""
    import importlib.metadata as _md

    versions: dict[str, str] = {}
    for package in _PROVENANCE_DEPENDENCIES:
        try:
            versions[package] = _md.version(package)
        except _md.PackageNotFoundError:
            continue
    return versions


def _digest_sources(source_files: dict[str, Path]) -> dict[str, str]:
    """``sha256:<hex>`` of every input file's bytes, as GIVEN (P3.9/P3.10).

    Computed once per run and shared by the provenance record and the
    final edit script's preconditions — the two must agree by
    construction, not by coincidence.
    """
    return {
        name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in source_files.items()
    }


def _build_run_provenance(
    *,
    producer_metadata: ProducerMetadata,
    escalation_producer: EditProducer | None,
    config_fingerprint: str,
    document_manifest: DocumentManifest,
    source_digests: dict[str, str],
    image_assets: dict[str, PageImage],
) -> RunProvenance:
    """The run's §11 provenance record (P3.9).

    Library + producer identity, policy fingerprint, per-file digests of
    the INPUT bytes (computed once per run by :func:`_digest_sources` and
    shared with the edit script's preconditions, so the two agree by
    construction), per-page image digests, and critical dependency
    versions.
    """
    from corrigenda import __version__ as _lib_version

    # copy the digest each structured ImageAsset already carries; the core
    # never opens an image (I4). Bare ImageRef strings and digest-less
    # assets contribute nothing.
    image_digests = {
        page_id: f"sha256:{asset.sha256}"
        for page_id, asset in image_assets.items()
        if isinstance(asset, ImageAsset) and asset.sha256
    }
    # record the escalation (vision) producer's identity too, from its own
    # declared metadata (the same optional-attribute convention as the
    # primary producer's). None for a single-producer run, so text-only
    # provenance is unchanged.
    escalation_prov: ProducerProvenance | None = None
    if escalation_producer is not None:
        emd = getattr(escalation_producer, "metadata", None) or ProducerMetadata()
        escalation_prov = ProducerProvenance(
            name=emd.name,
            version=emd.version,
            implementation=emd.implementation,
            configuration_fingerprint=emd.configuration_fingerprint,
        )
    return RunProvenance(
        lib_version=_lib_version,
        config_fingerprint=config_fingerprint,
        producer=ProducerProvenance(
            name=producer_metadata.name,
            version=producer_metadata.version,
            implementation=producer_metadata.implementation,
            configuration_fingerprint=producer_metadata.configuration_fingerprint,
        ),
        escalation_producer=escalation_prov,
        source_digests=source_digests,
        image_digests=image_digests,
        source_format=document_manifest.source_format,
        dependencies=_dependency_versions(),
    )
