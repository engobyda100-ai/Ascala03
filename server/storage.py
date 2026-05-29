"""Tempdir-per-run helpers + a 24h cleanup sweeper.

Tempdirs hold uploaded bytes for the lifetime of one run. Workers delete
them on success/failure; the sweeper handles crashes by purging anything
older than 24 hours.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.runs import registry


SWEEP_INTERVAL_S = 5 * 60        # 5 minutes
TEMPDIR_TTL = timedelta(hours=24)


def make_tempdir(run_id: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"{run_id}_"))


def cleanup_tempdir(path: Path | None) -> None:
    if path is None:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass  # best-effort


async def sweeper_loop() -> None:
    """Background task: every SWEEP_INTERVAL_S, delete tempdirs > 24h old."""
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_S)
        cutoff = datetime.now(tz=timezone.utc) - TEMPDIR_TTL
        for _run_id, path, created_at in registry.all_tempdirs():
            if created_at < cutoff and path.exists():
                cleanup_tempdir(path)
