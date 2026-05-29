"""PDF → text via pypdf."""
from __future__ import annotations

import io

from persona_synthesis.parsers.base import ParsedFile
from persona_synthesis.schema import UploadedFile


MAX_CHARS_PER_PDF = 40_000  # hard cap to keep prompt size bounded


def parse_pdf(f: UploadedFile) -> ParsedFile:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return ParsedFile(name=f.name, kind="pdf", note="pypdf not installed")

    try:
        reader = PdfReader(io.BytesIO(f.data))
        chunks: list[str] = []
        remaining = MAX_CHARS_PER_PDF
        for page in reader.pages:
            if remaining <= 0:
                break
            t = (page.extract_text() or "").strip()
            if not t:
                continue
            if len(t) > remaining:
                t = t[:remaining] + "…"
            chunks.append(t)
            remaining -= len(t)
        text = "\n\n".join(chunks)
    except Exception as e:
        return ParsedFile(name=f.name, kind="pdf", note=f"PDF parse failed: {e}")

    excerpt = text[:400] + ("…" if len(text) > 400 else "")
    return ParsedFile(name=f.name, kind="pdf", text=text, excerpt=excerpt)
