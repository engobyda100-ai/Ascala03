"""Preprocess uploaded screenshots into a navigable ScreenGraph.

One multimodal Claude call: system prompt + N screenshots as image blocks +
optional goal text. Uses tool-use to force structured output.
"""
from __future__ import annotations

from pydantic import BaseModel

from persona_synthesis.llm.base import LLMProvider
from persona_synthesis.parsers.image import parse_image
from persona_synthesis.schema import UploadedFile

from persona_simulation._llm_helpers import call_with_retry, load_prompt
from persona_simulation.errors import GraphIncomplete
from persona_simulation.schema import ScreenGraph


TOOL_NAME = "emit_screen_graph"
TOOL_DESCRIPTION = "Emit a structured ScreenGraph for the uploaded prototype screenshots."


class _ScreenGraphToolOutput(BaseModel):
    """Wraps ScreenGraph directly — the model's input_schema."""
    __pydantic_fields_set__ = ScreenGraph.model_fields


def build_screen_graph(
    screenshots: list[UploadedFile],
    *,
    goal: str | None = None,
    provider: LLMProvider,
) -> ScreenGraph:
    """Produce a ScreenGraph from the uploaded screenshots.

    Raises:
        ValueError: no screenshots given.
        GraphIncomplete: multiple screens produced but zero transitions.
        SchemaValidationError: LLM output failed validation twice.
    """
    if not screenshots:
        raise ValueError("build_screen_graph requires at least one screenshot")

    parsed = [parse_image(s) for s in screenshots]
    image_blocks: list[dict] = []
    filename_list: list[str] = []
    for p in parsed:
        if p.image_block is not None:
            image_blocks.append(p.image_block)
            filename_list.append(p.name)

    if not image_blocks:
        raise ValueError(
            "No parsable images found among screenshots (all failed to decode)"
        )

    intro_lines = [
        "You've been given the following uploaded screenshots in order:",
    ]
    for i, name in enumerate(filename_list, start=1):
        intro_lines.append(f"  - s{i} ({name})")
    if goal:
        intro_lines.append("")
        intro_lines.append(f"Product owner's stated goal for this prototype: {goal}")

    user_content: list[dict] = [{"type": "text", "text": "\n".join(intro_lines)}]
    user_content.extend(image_blocks)
    user_content.append({
        "type": "text",
        "text": "Emit the ScreenGraph now via the emit_screen_graph tool. "
                "Use s1, s2, s3... in upload order for screen ids.",
    })

    system = load_prompt("build_screen_graph.md")
    graph, _tokens = call_with_retry(
        provider,
        system=system,
        user_content=user_content,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=ScreenGraph,
    )

    # Spec: fail loud if multiple screens produced zero transitions.
    if len(graph.screens) > 1 and len(graph.transitions) == 0:
        raise GraphIncomplete(
            f"Screen graph has {len(graph.screens)} screens but 0 transitions. "
            "Upload more connected screenshots, or pass `screen_graph_override`."
        )
    return graph
