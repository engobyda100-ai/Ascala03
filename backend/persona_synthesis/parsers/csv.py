"""CSV → head + dtypes summary via pandas."""
from __future__ import annotations

import io

from persona_synthesis.parsers.base import ParsedFile
from persona_synthesis.schema import UploadedFile


MAX_PREVIEW_ROWS = 15


def parse_csv(f: UploadedFile) -> ParsedFile:
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        return ParsedFile(name=f.name, kind="csv", note="pandas not installed")

    try:
        df = pd.read_csv(io.BytesIO(f.data))
    except Exception as e:
        return ParsedFile(name=f.name, kind="csv", note=f"CSV parse failed: {e}")

    n_rows, n_cols = df.shape
    dtypes = ", ".join(f"{c}: {df[c].dtype}" for c in df.columns)
    head = df.head(MAX_PREVIEW_ROWS).to_csv(index=False)
    text = (
        f"CSV: {f.name}\n"
        f"Shape: {n_rows} rows × {n_cols} cols\n"
        f"Columns: {dtypes}\n"
        f"First {min(MAX_PREVIEW_ROWS, n_rows)} rows:\n{head}"
    )
    excerpt = f"{n_rows}×{n_cols} CSV, cols: {', '.join(df.columns[:6])}"
    return ParsedFile(name=f.name, kind="csv", text=text, excerpt=excerpt)
