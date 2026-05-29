"""Exceptions raised by the persona simulation pipeline."""
from __future__ import annotations

from typing import Any


class SimulationError(Exception):
    """Base class for all simulation errors."""


class BudgetExceeded(SimulationError):
    """A safety cap engaged mid-run.

    This is *not* normally raised — the runner catches budget hits and
    finalizes the report with `budget_stopped=True`. Only raised when a
    caller passes an impossibly small config (e.g. max_agents_budget=0).
    """


class GraphIncomplete(SimulationError):
    """The preprocessor produced a ScreenGraph with 0 transitions across
    multiple screens, meaning uploaded screenshots don't form a navigable flow.

    Caller should upload more screenshots (or provide a `screen_graph_override`
    via SimulationInputs).
    """


class SchemaValidationError(SimulationError):
    """LLM output failed pydantic validation on all retry attempts."""

    def __init__(self, attempts: int, last_errors: Any, raw_output: Any = None):
        self.attempts = attempts
        self.last_errors = last_errors
        self.raw_output = raw_output
        super().__init__(
            f"LLM output failed schema validation after {attempts} attempt(s): {last_errors}"
        )
