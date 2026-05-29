"""Parser dispatch: route an UploadedFile to the right parser by mime/extension."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from persona_synthesis.schema import UploadedFile


@dataclass
class ParsedFile:
    """Normalized result of parsing a single uploaded file.

    - `text` — extracted text (may be empty)
    - `image_block` — a Claude-compatible image block dict if this is an image,
      else None
    - `kind` — one of pdf|csv|text|image|video_skipped|unknown (maps to ResearchRef.kind)
    - `excerpt` — short preview for the ContextSummary's uploaded_research entry
    - `note` — human-readable note (e.g. "video skipped", "parse failed: ...")
    """
    name: str
    kind: str
    text: str = ""
    image_block: Optional[dict] = None
    excerpt: Optional[str] = None
    note: Optional[str] = None


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def parse_file(f: UploadedFile) -> ParsedFile:
    """Dispatch on mime-type first, then extension."""
    mime = (f.mime or "").lower()
    ext = _ext(f.name)

    # lazy imports to avoid circular + keep parsers optional
    if mime == "application/pdf" or ext == "pdf":
        from persona_synthesis.parsers.pdf import parse_pdf
        return parse_pdf(f)
    if mime == "text/csv" or ext == "csv":
        from persona_synthesis.parsers.csv import parse_csv
        return parse_csv(f)
    if mime.startswith("image/") or ext in {"png", "jpg", "jpeg", "gif", "webp"}:
        from persona_synthesis.parsers.image import parse_image
        return parse_image(f)
    if mime.startswith("video/") or ext in {"mp4", "mov", "webm", "avi", "mkv"}:
        return ParsedFile(
            name=f.name,
            kind="video_skipped",
            note="Video parsing not supported in this release; file acknowledged but content not processed.",
        )
    if mime.startswith("text/") or ext in {"txt", "md", "markdown", "json", "yaml", "yml"}:
        from persona_synthesis.parsers.text import parse_text
        return parse_text(f)

    # Fallback: try as text; if that fails, record as unknown
    try:
        from persona_synthesis.parsers.text import parse_text
        return parse_text(f)
    except Exception as e:  # pragma: no cover
        return ParsedFile(
            name=f.name,
            kind="unknown",
            note=f"No parser matched ({mime=}, {ext=}); and utf-8 decode failed: {e}",
        )
