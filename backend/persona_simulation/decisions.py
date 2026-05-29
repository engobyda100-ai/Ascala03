"""Per-turn agent decision call.

One Claude call per (agent, turn). Returns a validated AgentDecision plus the
approximate token usage for budget accounting.
"""
from __future__ import annotations

import base64
import json
from typing import Optional

from persona_synthesis.llm.base import LLMProvider
from persona_synthesis.parsers.image import parse_image
from persona_synthesis.schema import UploadedFile

from persona_simulation._llm_helpers import call_with_retry, load_prompt
from persona_simulation.schema import (
    AgentDecision,
    AgentStep,
    SampledAgent,
    Screen,
    ScreenGraph,
)


TOOL_NAME = "emit_decision"
TOOL_DESCRIPTION = "Emit a single AgentDecision for this turn of the simulated walkthrough."

HISTORY_WINDOW_DEFAULT = 5


def _agent_profile_text(agent: SampledAgent) -> str:
    group = agent.group
    parts = [
        f"You are agent `{agent.agent_id}` in cluster `{agent.cluster_name}` ({agent.cluster_id}).",
        "",
        "Concrete sampled traits:",
        f"  - age: {agent.age}",
        f"  - tech_savviness: {agent.tech_savviness}/5",
        f"  - patience_threshold: {agent.patience_threshold}",
        f"  - pricing_sensitivity: {agent.pricing_sensitivity}/5",
        f"  - primary_device: {agent.primary_device}",
        "",
        "Cluster narrative (shared with others in your group):",
        f"  - backstory: {group.narrative.backstory}",
        f"  - typical goals: {', '.join(group.narrative.goals)}",
        f"  - typical frustrations: {', '.join(group.narrative.frustrations)}",
        "",
        "Your personalized backstory (specific to you):",
        agent.personalized_backstory,
    ]
    return "\n".join(parts)


def _screen_text(screen: Screen) -> str:
    lines = [
        f"Current screen: {screen.id} (source: {screen.source_filename})",
        f"  inferred_purpose: {screen.inferred_purpose}",
    ]
    if screen.copy:
        lines.append(f"  notable_copy: {json.dumps(screen.copy)}")
    lines.append("  interactive_elements (use these ids for click_element):")
    for e in screen.elements:
        loc = f" [{e.bbox_hint}]" if e.bbox_hint else ""
        lines.append(f"    - {e.id}  ({e.kind}){loc}: {e.label}")
    return "\n".join(lines)


def _history_text(history: list[AgentStep], k: int) -> str:
    if not history:
        return "(no prior steps — this is your first turn)"
    recent = history[-k:]
    lines = [f"Recent history (last {len(recent)} of {len(history)} steps):"]
    for step in recent:
        d = step.decision
        target = f" → {d.target_element_id}" if d.target_element_id else ""
        emo = d.emotional_state
        lines.append(
            f"  step {step.order} on {step.screen_id}: {d.action}{target}; "
            f"conf={d.confidence}, frus={emo.frustration}, conf={emo.confusion}, "
            f"int={emo.interest}, trust={emo.trust}"
        )
    return "\n".join(lines)


def _screen_image_block(screen: Screen, screenshots: dict[str, UploadedFile]) -> Optional[dict]:
    """Build a Claude image block for the screen's source file if we have it."""
    src = screenshots.get(screen.source_filename)
    if src is None:
        return None
    parsed = parse_image(src)
    return parsed.image_block


def agent_decision(
    agent: SampledAgent,
    screen: Screen,
    history: list[AgentStep],
    *,
    goal: str | None,
    graph: ScreenGraph,
    provider: LLMProvider,
    screenshots: dict[str, UploadedFile] | None = None,
    history_window: int = HISTORY_WINDOW_DEFAULT,
) -> tuple[AgentDecision, int]:
    """Run one turn. Returns (decision, tokens_used).

    `screenshots` maps source_filename → UploadedFile so the vision model can
    see the actual screen. If None, the call runs without an image (text only)
    and the model has to rely on the structured element list.
    """
    user_content: list[dict] = []

    # Image first — gives the model the strongest signal.
    if screenshots:
        img_block = _screen_image_block(screen, screenshots)
        if img_block is not None:
            user_content.append(img_block)

    profile = _agent_profile_text(agent)
    screen_desc = _screen_text(screen)
    hist = _history_text(history, k=history_window)
    goal_text = f"Product owner's stated goal: {goal}" if goal else "No stated goal — act on your own default motivation."

    # Small graph excerpt: what outgoing transitions exist from THIS screen
    # (so the agent knows which clicks would actually go somewhere).
    outbound = [
        f"    - click {t.via_element_id} → lands on {t.to_screen}"
        for t in graph.transitions if t.from_screen == screen.id
    ]
    unresolved = [
        f"    - click {u.via_element_id} → dead end ({u.reason})"
        for u in graph.unresolved if u.from_screen == screen.id
    ]
    graph_excerpt_lines = ["Known outbound paths from this screen:"]
    graph_excerpt_lines.extend(outbound or ["    (no resolved transitions)"])
    if unresolved:
        graph_excerpt_lines.append("Dead-end clicks on this screen:")
        graph_excerpt_lines.extend(unresolved)

    composite = "\n\n".join([
        profile,
        screen_desc,
        "\n".join(graph_excerpt_lines),
        hist,
        goal_text,
        "Emit your decision via the emit_decision tool now. Stay in character.",
    ])
    user_content.append({"type": "text", "text": composite})

    system = load_prompt("agent_decision.md")
    decision, tokens = call_with_retry(
        provider,
        system=system,
        user_content=user_content,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=AgentDecision,
    )
    return decision, tokens
