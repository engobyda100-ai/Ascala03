"""In-memory run registry.

`RunState` is intentionally a plain dataclass (not Pydantic) because the
`tempdir` and `result` fields hold non-JSON-friendly types and we hand-build
the GET response JSON in `main.py`.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional


Kind = Literal["synthesis", "simulation", "report"]
Status = Literal["running", "done", "failed"]

_PREFIX = {"synthesis": "syn", "simulation": "sim", "report": "rep"}


@dataclass
class RunState:
    run_id: str
    kind: Kind
    status: Status = "running"
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    finished_at: Optional[datetime] = None
    tempdir: Optional[Path] = None


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._lock = threading.Lock()

    def new(self, kind: Kind, *, tempdir: Optional[Path] = None) -> RunState:
        run_id = f"{_PREFIX[kind]}_{uuid.uuid4().hex[:12]}"
        state = RunState(run_id=run_id, kind=kind, tempdir=tempdir)
        with self._lock:
            self._runs[run_id] = state
        return state

    def get(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            return self._runs.get(run_id)

    def mark_done(self, run_id: str, result: dict) -> None:
        with self._lock:
            r = self._runs[run_id]
            r.status = "done"
            r.result = result
            r.finished_at = datetime.now(tz=timezone.utc)

    def mark_failed(self, run_id: str, error: str) -> None:
        with self._lock:
            r = self._runs[run_id]
            r.status = "failed"
            r.error = error
            r.finished_at = datetime.now(tz=timezone.utc)

    def all_tempdirs(self) -> list[tuple[str, Path, datetime]]:
        with self._lock:
            return [
                (r.run_id, r.tempdir, r.created_at)
                for r in self._runs.values()
                if r.tempdir is not None
            ]


registry = RunRegistry()
