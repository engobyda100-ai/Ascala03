"""Draft a Fix from a single CategorizedIssue (one LLM call), then validate.

Validation is structural: the fix_prompt must contain the four required
sections in order. On format failure, retry once with a stricter prompt.
Second failure → FixPromptFormatError (caller decides whether to drop the
Fix or surface the error).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Iterable

from pydantic import BaseModel, Field, ValidationError

from persona_simulation.schema import (
    AgentPath,
    CategorizedIssue,
    SimulationResult,
)
from persona_synthesis.llm.base import LLMProvider

from persona_report._llm_helpers import call_provider, call_with_retry, load_prompt
from persona_report.counterfactuals import compute_counterfactual_impact
from persona_report.errors import FixPromptFormatError
from persona_report.schema import (
    Fix,
    FixEvidence,
    Severity,
)


TOOL_NAME = "emit_fix"
TOOL_DESCRIPTION = "Emit a Fix derived from a single CategorizedIssue."


# ──────────────────────────── Fix-prompt format check ────────────────────────────

IMPERATIVE_VERBS = (
    "add", "remove", "replace", "enlarge", "move", "rename", "reorder",
    "demote", "promote", "collapse", "expand", "surface", "hide", "fix",
    "gate", "debounce", "validate", "disable", "enable",
)

VERB_GROUP = "|".join(IMPERATIVE_VERBS)

SECTION_REGEXES = [
    ("section_1_intro", re.compile(r"(?im)^on the [a-z0-9_\-\.]+ screen \(")),
    ("section_2_evidence", re.compile(r"(?im)evidence:\s*\d+\s*/\s*\d+\s+agents")),
    ("section_3_change", re.compile(rf"(?im)change required:\s*({VERB_GROUP})\b")),
    ("section_4_visual", re.compile(r"(?im)visual/interaction direction:\s*\S+")),
]


def check_fix_prompt(prompt: str) -> list[str]:
    """Return list of missing section names; empty list = passes."""
    missing: list[str] = []
    for name, regex in SECTION_REGEXES:
        if not regex.search(prompt):
            missing.append(name)
    return missing


# ──────────────────────────── LLM tool output ────────────────────────────

class _FixDraftOutput(BaseModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    fix_prompt: str = Field(min_length=1)
    estimated_impact: str = Field(min_length=1)


# ──────────────────────────── Evidence assembly ────────────────────────────

def _agents_matching_issue(
    issue: CategorizedIssue, sim: SimulationResult
) -> list[AgentPath]:
    """Agents whose paths touched any affected screen OR whose observed_issues
    overlap with the issue's evidence strings.
    """
    affected_screens = set(issue.affected_screens)
    evidence_set = {e.strip().lower() for e in issue.evidence if e.strip()}
    out: list[AgentPath] = []
    for p in sim.paths:
        touched_screen = any(s in affected_screens for s in p.screens_visited)
        observed_match = False
        if evidence_set:
            for step in p.steps:
                for obs in step.decision.observed_issues:
                    if obs.strip().lower() in evidence_set:
                        observed_match = True
                        break
                if observed_match:
                    break
        if touched_screen or observed_match:
            out.append(p)
    return out


def _representative_quotes(
    issue: CategorizedIssue, agents: list[AgentPath]
) -> list[str]:
    """Up to 3 short quotes from agent reasoning that mention the issue's
    keywords or land on the affected screens.
    """
    affected_screens = set(issue.affected_screens)
    out: list[str] = []
    seen: set[str] = set()
    for p in agents:
        for step in p.steps:
            if step.screen_id not in affected_screens and not step.decision.observed_issues:
                continue
            quote = step.decision.reasoning.strip()
            if not quote or quote.lower() in seen:
                continue
            if len(quote) > 200:
                quote = quote[:197] + "…"
            out.append(quote)
            seen.add(quote.lower())
            if len(out) >= 3:
                return out
    return out


def _build_evidence(
    issue: CategorizedIssue, sim: SimulationResult
) -> tuple[FixEvidence, list[AgentPath]]:
    agents = _agents_matching_issue(issue, sim)
    affected_clusters = sorted({p.agent.cluster_id for p in agents})
    quotes = _representative_quotes(issue, agents)
    evidence = FixEvidence(
        affected_clusters=affected_clusters,
        affected_screens=list(issue.affected_screens),
        agent_count=len(agents),
        representative_quotes=quotes,
    )
    return evidence, agents


# ──────────────────────────── Cache ────────────────────────────

class FixCache:
    """In-memory cache keyed on (test_type, issue_id, summary_hash).

    The "issue_id" can be the issue summary itself when no upstream id exists.
    Scoped to a single generate_report() call.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], Fix] = {}

    @staticmethod
    def _hash(s: str) -> str:
        return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]

    def get(self, test_type: str, issue_id: str, summary: str) -> Fix | None:
        return self._cache.get((test_type, issue_id, self._hash(summary)))

    def put(self, test_type: str, issue_id: str, summary: str, fix: Fix) -> None:
        self._cache[(test_type, issue_id, self._hash(summary))] = fix


# ──────────────────────────── Drafting ────────────────────────────

def _user_content_for(
    issue: CategorizedIssue,
    severity: Severity,
    evidence: FixEvidence,
    sim: SimulationResult,
) -> list[dict]:
    # Map screen ids → filenames so the prompt can use both
    screen_files = {s.id: s.source_filename for s in sim.screen_graph.screens}
    affected_files = {sid: screen_files.get(sid, "?") for sid in issue.affected_screens}
    cluster_names = {
        p.agent.cluster_id: p.agent.cluster_name for p in sim.paths
    }
    cluster_counts: dict[str, int] = defaultdict(int)
    for p in sim.paths:
        cluster_counts[p.agent.cluster_id] += 1

    user_text = (
        "Categorized issue:\n"
        f"```json\n{json.dumps(issue.model_dump(), indent=2)}\n```\n\n"
        f"Severity (already determined deterministically — DO NOT change): {severity}\n\n"
        "Computed evidence (use these numbers and clusters in the fix_prompt; "
        "the ratio in the Evidence section MUST match):\n"
        f"```json\n{json.dumps(evidence.model_dump(), indent=2)}\n```\n\n"
        "Cluster sizes:\n"
        f"```json\n{json.dumps(dict(cluster_counts), indent=2)}\n```\n\n"
        "Cluster id → name mapping:\n"
        f"```json\n{json.dumps(cluster_names, indent=2)}\n```\n\n"
        "Affected screen id → filename mapping:\n"
        f"```json\n{json.dumps(affected_files, indent=2)}\n```\n\n"
        "Emit the fix via the emit_fix tool now. Fix prompt MUST follow the 4-section "
        "format from the system prompt EXACTLY."
    )
    return [{"type": "text", "text": user_text}]


def draft_fix(
    issue: CategorizedIssue,
    severity: Severity,
    sim: SimulationResult,
    *,
    provider: LLMProvider,
    test_type: str,
    cache: FixCache | None = None,
) -> tuple[Fix, int]:
    """Draft one Fix. Returns (fix, tokens_used).

    Raises FixPromptFormatError if the format check fails twice.
    """
    cache = cache or FixCache()
    issue_id = issue.summary  # no upstream id; use summary as key
    cached = cache.get(test_type, issue_id, issue.summary)
    if cached is not None:
        return cached, 0

    evidence, _agents = _build_evidence(issue, sim)
    counterfactual = compute_counterfactual_impact(_agents, sim)
    system = load_prompt("draft_fix.md")
    user_content = _user_content_for(issue, severity, evidence, sim)

    # First attempt
    _, draft, tokens = call_provider(
        provider,
        system=system,
        user_content=user_content,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=_FixDraftOutput,
    )

    missing = check_fix_prompt(draft.fix_prompt)
    if missing:
        # Retry once with explicit format reminder
        retry_system = (
            system
            + "\n\n---\nRETRY ADDENDUM\n"
            f"Your previous fix_prompt was missing required sections: {missing}.\n"
            "The fix_prompt MUST contain these four sections in order:\n"
            "  1. On the <SCREEN_ID> screen (<SCREEN_FILENAME>), <PROBLEM>.\n"
            "  2. Evidence: <N>/<TOTAL> agents in the <CLUSTER_NAME> cluster <STAT>.\n"
            "  3. Change required: <IMPERATIVE_VERB> <ELEMENT> <DIRECTION>.\n"
            "  4. Visual/interaction direction: <DETAIL>.\n"
            f"Imperative verbs allowed: {', '.join(IMPERATIVE_VERBS)}.\n"
            "Re-emit the fix with the correct format."
        )
        _, draft2, tokens2 = call_provider(
            provider,
            system=retry_system,
            user_content=user_content,
            tool_name=TOOL_NAME,
            tool_description=TOOL_DESCRIPTION,
            output_model=_FixDraftOutput,
        )
        tokens += tokens2
        missing2 = check_fix_prompt(draft2.fix_prompt)
        if missing2:
            raise FixPromptFormatError(
                issue_id=issue_id,
                raw_prompt=draft2.fix_prompt,
                missing_parts=missing2,
            )
        draft = draft2

    fix = Fix(
        severity=severity,
        title=draft.title,
        summary=draft.summary,
        evidence=evidence,
        fix_prompt=draft.fix_prompt,
        estimated_impact=draft.estimated_impact,
        related_issue_ids=[issue_id],
        counterfactual_impact=counterfactual,
    )
    cache.put(test_type, issue_id, issue.summary, fix)
    return fix, tokens


# ──────────────────────────── Bulk drafting with quota ────────────────────────────

# Per test type, the brief caps fixes at: 4 urgent / 6 important / 6 medium.
QUOTA_PER_SEVERITY: dict[Severity, int] = {
    "urgent": 4,
    "important": 6,
    "medium": 6,
}


def _select_within_quota(
    classified: list[tuple[CategorizedIssue, Severity]]
) -> list[tuple[CategorizedIssue, Severity]]:
    """Apply per-severity quotas, urgent first."""
    by_sev: dict[Severity, list[CategorizedIssue]] = defaultdict(list)
    for issue, sev in classified:
        by_sev[sev].append(issue)
    selected: list[tuple[CategorizedIssue, Severity]] = []
    for sev in ("urgent", "important", "medium"):
        cap = QUOTA_PER_SEVERITY[sev]  # type: ignore[index]
        selected.extend((i, sev) for i in by_sev[sev][:cap])  # type: ignore[misc]
    return selected


def draft_fixes_for_test_type(
    classified: list[tuple[CategorizedIssue, Severity]],
    sim: SimulationResult,
    *,
    test_type: str,
    provider: LLMProvider,
    cache: FixCache | None = None,
) -> tuple[list[Fix], int, list[str]]:
    """Returns (fixes, tokens_used, warnings).

    Failed format checks become warnings (the offending Fix is dropped).
    """
    cache = cache or FixCache()
    selected = _select_within_quota(classified)
    fixes: list[Fix] = []
    tokens_total = 0
    warnings: list[str] = []
    for issue, sev in selected:
        try:
            fix, tokens = draft_fix(
                issue, sev, sim, provider=provider, test_type=test_type, cache=cache,
            )
            fixes.append(fix)
            tokens_total += tokens
        except FixPromptFormatError as e:
            warnings.append(
                f"[{test_type}] dropped fix for issue {e.issue_id!r}: "
                f"missing {e.missing_parts}"
            )
    return fixes, tokens_total, warnings
