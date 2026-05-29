"""Parser tests with generated fixtures (no external files needed)."""
from __future__ import annotations

import base64
import io

import pytest

from persona_synthesis.parsers.base import parse_file
from persona_synthesis.parsers.csv import parse_csv
from persona_synthesis.parsers.image import parse_image
from persona_synthesis.parsers.text import parse_text
from persona_synthesis.schema import UploadedFile


# ---------- text ----------

def test_parse_text_utf8():
    f = UploadedFile(name="notes.txt", mime="text/plain", data="Hello Ascala".encode("utf-8"))
    out = parse_text(f)
    assert out.kind == "text"
    assert "Hello" in out.text
    assert out.excerpt


def test_parse_text_truncates():
    big = ("x" * 50_000).encode("utf-8")
    out = parse_text(UploadedFile(name="big.md", mime="text/markdown", data=big))
    assert out.text.endswith("…")
    assert out.note == "truncated"


# ---------- csv ----------

def test_parse_csv_basic():
    csv_bytes = b"name,country,score\nAlice,US,9\nBob,DE,7\nCarol,FR,8\n"
    out = parse_csv(UploadedFile(name="users.csv", mime="text/csv", data=csv_bytes))
    assert out.kind == "csv"
    assert "3 rows" in out.text
    assert "Alice" in out.text
    assert "users.csv" in out.text


# ---------- image ----------

def test_parse_image_png():
    pil = pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGB", (50, 40), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    out = parse_image(UploadedFile(name="shot.png", mime="image/png", data=data))
    assert out.kind == "image"
    assert out.image_block is not None
    src = out.image_block["source"]
    assert src["type"] == "base64"
    assert src["media_type"] == "image/png"
    # Base64 decodes back to a valid PNG
    decoded = base64.b64decode(src["data"])
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


def test_parse_image_downscales_large():
    pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGB", (3000, 3000), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out = parse_image(UploadedFile(name="huge.png", mime="image/png", data=buf.getvalue()))
    assert out.image_block is not None
    # Re-decode to check dimensions went down
    decoded = base64.b64decode(out.image_block["source"]["data"])
    rt = Image.open(io.BytesIO(decoded))
    assert max(rt.size) <= 1568


# ---------- dispatch ----------

def test_parse_file_dispatches_by_mime_text():
    f = UploadedFile(name="x", mime="text/plain", data=b"abc")
    assert parse_file(f).kind == "text"


def test_parse_file_dispatches_by_extension():
    f = UploadedFile(name="x.csv", mime="application/octet-stream", data=b"a,b\n1,2\n")
    assert parse_file(f).kind == "csv"


def test_parse_file_skips_video():
    f = UploadedFile(name="walk.mp4", mime="video/mp4", data=b"\x00\x00")
    out = parse_file(f)
    assert out.kind == "video_skipped"
    assert out.note and "not supported" in out.note


def test_parse_file_pdf_dispatch_with_invalid_bytes():
    """PDF parser should return a ParsedFile with a note, not raise."""
    f = UploadedFile(name="broken.pdf", mime="application/pdf", data=b"not a pdf")
    out = parse_file(f)
    assert out.kind == "pdf"
    # Either parsed empty or noted failure — neither should raise
    assert out.note or out.text == ""
