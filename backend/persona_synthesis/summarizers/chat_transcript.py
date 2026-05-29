"""Summarize a chat transcript into a ContextSummary."""
from __future__ import annotations

from persona_synthesis.llm.base import LLMProvider
from persona_synthesis.schema import ChatMessage, ContextSummary
from persona_synthesis.summarizers._shared import call_and_validate, load_prompt


def _format_transcript(messages: list[ChatMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        role = "User" if m.role == "user" else ("Assistant" if m.role in {"bot", "assistant"} else m.role.capitalize())
        lines.append(f"{role}: {m.text.strip()}")
    return "\n\n".join(lines)


def summarize_chat(messages: list[ChatMessage], provider: LLMProvider) -> ContextSummary:
    if not messages:
        raise ValueError("summarize_chat called with an empty transcript")

    transcript = _format_transcript(messages)
    user_content = [
        {
            "type": "text",
            "text": f"Chat transcript between the product owner and the discovery assistant:\n\n{transcript}",
        }
    ]
    system = load_prompt("summarize_chat.md")
    return call_and_validate(provider, system=system, user_content=user_content)
