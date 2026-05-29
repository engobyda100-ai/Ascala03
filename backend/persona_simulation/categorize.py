"""Cluster observed issues into the 5 test categories via one LLM call."""
from __future__ import annotations

import json

from persona_synthesis.llm.base import LLMProvider

from persona_simulation._llm_helpers import call_with_retry, load_prompt
from persona_simulation.schema import CategorizedIssues


TOOL_NAME = "emit_categorized_issues"
TOOL_DESCRIPTION = "Emit CategorizedIssues bucketing the raw observed issues into the 5 test categories."


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it.strip())
    return out


def categorize_issues(
    observed: list[str],
    *,
    provider: LLMProvider,
) -> CategorizedIssues:
    """Take the raw observed_issue strings aggregated from all agents and
    return a structured CategorizedIssues bundle.

    If the input list is empty (no issues surfaced in the run), return an
    empty CategorizedIssues without making an LLM call.
    """
    deduped = _dedupe_preserving_order(observed)
    if not deduped:
        return CategorizedIssues(issues=[])

    user_content = [{
        "type": "text",
        "text": (
            "Raw observed issues from simulated agents (deduped):\n\n"
            f"```json\n{json.dumps(deduped, indent=2)}\n```\n\n"
            "Emit the CategorizedIssues now via the emit_categorized_issues tool."
        ),
    }]
    system = load_prompt("categorize_issues.md")
    out, _tokens = call_with_retry(
        provider,
        system=system,
        user_content=user_content,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=CategorizedIssues,
    )
    return out
