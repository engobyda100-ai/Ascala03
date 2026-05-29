"""Exceptions raised by the persona synthesis pipeline."""
from __future__ import annotations

from typing import Any


class SynthesisError(Exception):
    """Base class for all pipeline errors."""


class SchemaValidationError(SynthesisError):
    """LLM output failed pydantic validation on all retry attempts.

    Surfaces to FastAPI as HTTP 502 with the details in the error body.
    """

    def __init__(self, attempts: int, last_errors: Any, raw_output: Any = None):
        self.attempts = attempts
        self.last_errors = last_errors
        self.raw_output = raw_output
        super().__init__(
            f"LLM output failed schema validation after {attempts} attempt(s): {last_errors}"
        )


class ProviderError(SynthesisError):
    """The LLM provider itself failed (network, auth, rate limit)."""
