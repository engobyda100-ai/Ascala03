"""Summarize parsed context files into a ContextSummary."""
from __future__ import annotations

from persona_synthesis.llm.base import LLMProvider
from persona_synthesis.parsers.base import ParsedFile
from persona_synthesis.schema import ContextSummary, ResearchRef
from persona_synthesis.summarizers._shared import call_and_validate, load_prompt


def summarize_files(
    parsed: list[ParsedFile],
    provider: LLMProvider,
    *,
    product_url: str | None = None,
) -> ContextSummary:
    """Produce a ContextSummary from parsed files.

    Text parts are concatenated with headers, image blocks are attached as
    separate content blocks so Claude Vision sees them.
    """
    if not parsed and not product_url:
        raise ValueError("summarize_files called with no files and no product_url")

    text_parts: list[str] = []
    image_blocks: list[dict] = []
    research_refs: list[ResearchRef] = []

    if product_url:
        text_parts.append(f"[Product URL]\n{product_url}")
        research_refs.append(
            ResearchRef(name=product_url, kind="url", extracted_excerpt=None, note=None)
        )

    for p in parsed:
        research_refs.append(
            ResearchRef(
                name=p.name,
                kind=p.kind if p.kind in {"pdf", "csv", "text", "image", "video_skipped", "url"} else "text",
                extracted_excerpt=p.excerpt,
                note=p.note,
            )
        )
        if p.image_block is not None:
            image_blocks.append(p.image_block)
            text_parts.append(f"[Image: {p.name}] — see attached screenshot.")
        elif p.text:
            text_parts.append(f"[File: {p.name} · {p.kind}]\n{p.text}")
        elif p.note:
            text_parts.append(f"[File: {p.name} · {p.kind}] — {p.note}")

    prompt_text = "\n\n---\n\n".join(text_parts) if text_parts else "(no extractable text)"

    user_content: list[dict] = [{"type": "text", "text": prompt_text}]
    # Image blocks go after the text so the LLM has textual framing first
    user_content.extend(image_blocks)

    system = load_prompt("summarize_files.md")
    summary = call_and_validate(provider, system=system, user_content=user_content)

    # Ensure the research refs we tracked appear on the summary (LLM may drop them).
    # Prefer LLM-provided refs; fall back to ours if it returned nothing.
    if not summary.uploaded_research:
        summary = summary.model_copy(update={"uploaded_research": research_refs})
    return summary
