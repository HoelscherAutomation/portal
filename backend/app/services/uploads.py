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
        validate_svg(content)
        ext = "svg"
    else:
        try:
            img = Image.open(io.BytesIO(content))
            fmt = img.format  # capture BEFORE verify() invalidates the object
            img.verify()
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
            raise InvalidImageError("Uploaded file is not a recognizable image") from exc
        if fmt is None or fmt not in ALLOWED_FORMATS - {"SVG"}:
            raise InvalidImageError(f"Unsupported image format: {fmt}")
        ext = fmt.lower()

    filename = f"logo-{secrets.token_hex(8)}.{ext}"
    target = _ensure_uploads_dir() / filename

    async with aiofiles.open(target, "wb") as f:
        await f.write(content)

    return filename


def delete_logo(filename: str) -> None:
    """Remove a previously saved logo. Silent if file missing."""
    uploads_root = Path(get_settings().uploads_path).resolve()
    target = (uploads_root / filename).resolve()
    if target.parent != uploads_root:
        # Defensive: refuse to follow paths outside the uploads directory.
        raise ValueError(f"Refusing to delete file outside uploads directory: {filename}")
    target.unlink(missing_ok=True)


def validate_svg(content: bytes) -> None:
    """Validate SVG content: parseable XML, root is <svg>, no script or event handlers.

    Raises InvalidImageError on rejection.
    """
    from defusedxml import ElementTree as ET

    try:
        tree = ET.fromstring(content)
    except ET.ParseError as exc:
        raise InvalidImageError("SVG is not valid XML") from exc

    # Strip namespace from local tag name for comparison.
    def local(tag: str) -> str:
        return tag.split("}", 1)[-1].lower()

    if local(tree.tag) != "svg":
        raise InvalidImageError("File is not an SVG (root element must be <svg>)")

    # Walk all elements; reject script tags and on* event handler attributes.
    for elem in tree.iter():
        if local(elem.tag) == "script":
            raise InvalidImageError("SVG contains <script> elements")
        for attr_name, attr_value in elem.attrib.items():
            attr_lower = attr_name.lower().split("}", 1)[-1]
            if attr_lower.startswith("on"):
                raise InvalidImageError(f"SVG contains event handler attribute: {attr_name}")
            value_lower = attr_value.lower()
            if "javascript:" in value_lower:
                raise InvalidImageError(f"SVG contains javascript: URI in attribute: {attr_name}")
            if "data:" in value_lower:
                raise InvalidImageError(f"SVG contains data: URI in attribute: {attr_name}")
