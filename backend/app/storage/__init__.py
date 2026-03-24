"""Storage helpers: job directories and file I/O."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

_BASE_DIR = Path("/tmp/app-jobs")

_ALLOWED_EXTENSIONS = {".xml", ".alto"}


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def job_dir(job_id: str) -> Path:
    return _BASE_DIR / job_id


def input_dir(job_id: str) -> Path:
    return job_dir(job_id) / "input"


def output_dir(job_id: str) -> Path:
    return job_dir(job_id) / "output"


def init_job_dirs(job_id: str) -> None:
    input_dir(job_id).mkdir(parents=True, exist_ok=True)
    output_dir(job_id).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_uploaded_files(
    job_id: str,
    files: list[tuple[str, bytes]],
) -> dict[str, Path]:
    """
    Persist uploaded files to input_dir(job_id).

    Handles ZIP archives: members whose extension is in _ALLOWED_EXTENSIONS
    are extracted with only their basename (no subdirectory structure).

    Returns a mapping of filename → absolute Path for every saved file.
    """
    dest = input_dir(job_id)
    dest.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}

    for filename, content in files:
        suffix = Path(filename).suffix.lower()

        if suffix == ".zip":
            # Extract whitelisted files from ZIP
            import io
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for member in zf.infolist():
                    member_path = Path(member.filename)
                    if member_path.suffix.lower() in _ALLOWED_EXTENSIONS:
                        flat_name = member_path.name
                        out_path = dest / flat_name
                        out_path.write_bytes(zf.read(member.filename))
                        saved[flat_name] = out_path
        elif suffix in _ALLOWED_EXTENSIONS:
            flat_name = Path(filename).name
            out_path = dest / flat_name
            out_path.write_bytes(content)
            saved[flat_name] = out_path
        # Silently ignore files with other extensions

    return saved


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
