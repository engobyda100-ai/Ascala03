"""Image → Claude-compatible base64 image block.

The image goes into the Claude message as a content block:
  {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}
"""
from __future__ import annotations

import base64
import io

from persona_synthesis.parsers.base import ParsedFile
from persona_synthesis.schema import UploadedFile


# Claude supports up to 5MB per image; keep things well under that after resize.
MAX_DIMENSION = 1568  # Claude's recommended long-edge for quality+cost balance


def parse_image(f: UploadedFile) -> ParsedFile:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return ParsedFile(name=f.name, kind="image", note="Pillow not installed")

    try:
        img = Image.open(io.BytesIO(f.data))
        img.load()
    except Exception as e:
        return ParsedFile(name=f.name, kind="image", note=f"Image decode failed: {e}")

    fmt = (img.format or "PNG").upper()
    # Normalize unusual formats and ensure RGB (Claude accepts PNG/JPEG/GIF/WEBP)
    if fmt not in {"PNG", "JPEG", "GIF", "WEBP"}:
        fmt = "PNG"

    # Downscale if too large
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > MAX_DIMENSION:
        scale = MAX_DIMENSION / long_edge
        img = img.resize((int(w * scale), int(h * scale)))

    if fmt == "JPEG" and img.mode not in {"RGB", "L"}:
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}[fmt]
    block = {
        "type": "image",
        "source": {"type": "base64", "media_type": mime, "data": b64},
    }
    excerpt = f"{w}×{h} {fmt} screenshot"
    return ParsedFile(
        name=f.name,
        kind="image",
        text="",  # visual content reaches the model via the image block
        image_block=block,
        excerpt=excerpt,
    )
