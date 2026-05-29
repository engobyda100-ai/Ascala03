"""Exceptions for the persona_report module."""
from __future__ import annotations

from typing import Any


class ReportError(Exception):
    """Base class for report-generation errors."""


class SchemaValidationError(ReportError):
    """An LLM output failed pydantic validation on all retry attempts."""

    def __init__(self, attempts: int, last_errors: Any, raw_output: Any = None):
        self.attempts = attempts
        self.last_errors = last_errors
        self.raw_output = raw_output
        super().__init__(
            f"LLM output failed schema validation after {attempts} attempt(s): {last_errors}"
        )


class FixPromptFormatError(ReportError):
    """A fix_prompt failed structural validation after the retry attempt.

    Non-fatal: the runner catches this, drops the offending fix, and records
    a meta-warning on the final Report.
    """

    def __init__(self, issue_id: str, raw_prompt: str, missing_parts: list[str]):
        self.issue_id = issue_id
        self.raw_prompt = raw_prompt
        self.missing_parts = missing_parts
        super().__init__(
            f"fix_prompt for issue {issue_id!r} missing parts: {missing_parts}"
        )
