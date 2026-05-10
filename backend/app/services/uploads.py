import io
import secrets
from pathlib import Path

import aiofiles
from PIL import Image, UnidentifiedImageError

from app.config import get_settings

ALLOWED_FORMATS = {"PNG", "JPEG", "SVG"}
MAX_BYTES = 2 * 1024 * 1024  # 2 MB


class InvalidImageError(ValueError):
    """Raised when an uploaded file isn't a recognizable image or violates constraints."""


def _ensure_uploads_dir() -> Path:
    path = Path(get_settings().uploads_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_logo(content: bytes, original_name: str) -> str:
    """Validate and save a logo file. Returns the stored filename."""
    if len(content) > MAX_BYTES:
        raise InvalidImageError(f"Image exceeds {MAX_BYTES // 1024 // 1024} MB limit")

    suffix = Path(original_name).suffix.lower()
    if suffix == ".svg":
        # Trust the suffix for SVG; we don't have an XML validator wired in.
        ext = "svg"
    else:
        try:
            img = Image.open(io.BytesIO(content))
            img.verify()
        except (UnidentifiedImageError, Exception) as exc:
            raise InvalidImageError("Uploaded file is not a recognizable image") from exc
        if img.format not in ALLOWED_FORMATS - {"SVG"}:
            raise InvalidImageError(f"Unsupported image format: {img.format}")
        ext = img.format.lower()

    filename = f"logo-{secrets.token_hex(8)}.{ext}"
    target = _ensure_uploads_dir() / filename

    async with aiofiles.open(target, "wb") as f:
        await f.write(content)

    return filename


def delete_logo(filename: str) -> None:
    """Remove a previously saved logo. Silent if file missing."""
    target = Path(get_settings().uploads_path) / filename
    if target.exists():
        target.unlink()
