"""Ascala persona synthesis backend."""

from persona_synthesis.schema import (
    ChatMessage,
    ContextSummary,
    PersonaGroup,
    SynthesisInputs,
    SynthesisResult,
    UploadedFile,
)
from persona_synthesis.synthesize import synthesize_personas
from persona_synthesis.errors import SynthesisError, SchemaValidationError

__all__ = [
    "synthesize_personas",
    "SynthesisInputs",
    "SynthesisResult",
    "ContextSummary",
    "PersonaGroup",
    "ChatMessage",
    "UploadedFile",
    "SynthesisError",
    "SchemaValidationError",
]
