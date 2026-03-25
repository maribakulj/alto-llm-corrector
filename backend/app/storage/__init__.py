"""Storage helpers: job directories and file I/O."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

_BASE_DIR = Path("/tmp/app-jobs")

_ALLOWED_EXTENSIONS = {".xml", ".alto"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def job_dir(job_id: str) -> Path:
    return _BASE_DIR / job_id


def input_dir(job_id: str) -> Path:
    return job_dir(job_id) / "input"


def output_dir(job_id: str) -> Path:
    return job_dir(job_id) / "output"


def images_dir(job_id: str) -> Path:
    return input_dir(job_id) / "images"


def init_job_dirs(job_id: str) -> None:
    input_dir(job_id).mkdir(parents=True, exist_ok=True)
    output_dir(job_id).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_uploaded_files(
    job_id: str,
    files: list[tuple[str, bytes]],
) -> tuple[dict[str, Path], dict[str, Path]]:
    """
    Persist uploaded files to input_dir(job_id).

    Handles ZIP archives: members whose extension is in _ALLOWED_EXTENSIONS
    are extracted with only their basename (no subdirectory structure).
    Image members (JPEG, PNG, TIFF) are saved to images_dir(job_id).

    Returns a tuple of:
    - alto_files: {filename → Path} for every ALTO/XML file saved
    - image_files: {lowercase_stem → Path} for every image file saved
    """
    dest = input_dir(job_id)
    dest.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    images: dict[str, Path] = {}

    for filename, content in files:
        suffix = Path(filename).suffix.lower()

        if suffix == ".zip":
            import io
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for member in zf.infolist():
                    member_path = Path(member.filename)
                    msuffix = member_path.suffix.lower()
                    if msuffix in _ALLOWED_EXTENSIONS:
                        flat_name = member_path.name
                        out_path = dest / flat_name
                        out_path.write_bytes(zf.read(member.filename))
                        saved[flat_name] = out_path
                    elif msuffix in _IMAGE_EXTENSIONS:
                        imgs = images_dir(job_id)
                        imgs.mkdir(parents=True, exist_ok=True)
                        flat_name = member_path.name
                        out_path = imgs / flat_name
                        out_path.write_bytes(zf.read(member.filename))
                        images[member_path.stem.lower()] = out_path
        elif suffix in _ALLOWED_EXTENSIONS:
            flat_name = Path(filename).name
            out_path = dest / flat_name
            out_path.write_bytes(content)
            saved[flat_name] = out_path
        # Silently ignore files with other extensions

    return saved, images


def get_image_files(job_id: str) -> dict[str, Path]:
    """Return {lowercase_stem: Path} for all images in images_dir(job_id)."""
    d = images_dir(job_id)
    if not d.exists():
        return {}
    return {
        p.stem.lower(): p
        for p in d.iterdir()
        if p.suffix.lower() in _IMAGE_EXTENSIONS
    }


def link_alto_to_images(
    pages: list[tuple[str, str]],
    saved_alto: dict[str, Path],
    saved_images: dict[str, Path],
) -> dict[str, str]:
    """
    Match ALTO pages to images.

    pages: list of (page_id, source_file) pairs from the document manifest.
    saved_alto: {filename → Path} mapping from save_uploaded_files.
    saved_images: {lowercase_stem → Path} mapping from save_uploaded_files.

    Strategy:
    1. Parse sourceImageInformation/fileName from the ALTO XML.
    2. Fall back to matching by lowercase stem of the ALTO source filename.

    Returns {page_id: image_filename} for matched pages.
    """
    from lxml import etree

    result: dict[str, str] = {}

    for page_id, source_file in pages:
        alto_path = saved_alto.get(source_file)
        if alto_path is None:
            continue

        # Strategy 1: read sourceImageInformation/fileName from ALTO XML
        image_key: str | None = None
        try:
            tree = etree.parse(str(alto_path))
            for el in tree.findall(".//{*}fileName"):
                fname = (el.text or "").strip()
                if fname:
                    image_key = Path(fname).stem.lower()
                    break
        except Exception:
            pass

        # Strategy 2: fallback to ALTO filename stem
        if not image_key or image_key not in saved_images:
            image_key = Path(source_file).stem.lower()

        if image_key in saved_images:
            result[page_id] = saved_images[image_key].name

    return result


def get_output_files(job_id: str) -> list[Path]:
    """Return all files in output_dir(job_id), sorted by name."""
    d = output_dir(job_id)
    if not d.exists():
        return []
    return sorted(d.iterdir())


def cleanup_job(job_id: str) -> None:
    """Remove the job directory tree."""
    d = job_dir(job_id)
    if d.exists():
        shutil.rmtree(d)
