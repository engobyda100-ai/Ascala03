"""Plain text / markdown / json → utf-8 passthrough."""
from __future__ import annotations

from persona_synthesis.parsers.base import ParsedFile
from persona_synthesis.schema import UploadedFile


MAX_CHARS = 40_000


def parse_text(f: UploadedFile) -> ParsedFile:
    try:
        text = f.data.decode("utf-8", errors="replace")
    except Exception as e:
        return ParsedFile(name=f.name, kind="text", note=f"Decode failed: {e}")

    truncated = False
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "…"
        truncated = True

    excerpt = text[:400] + ("…" if len(text) > 400 else "")
    note = "truncated" if truncated else None
    return ParsedFile(name=f.name, kind="text", text=text, excerpt=excerpt, note=note)
