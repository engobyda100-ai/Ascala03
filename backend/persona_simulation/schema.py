"""Pydantic models for the persona simulation pipeline.

Public types:
- SimulationInputs  — what the caller hands to simulate()
- SimulationResult  — what the caller gets back
- ScreenGraph       — the preprocessed map of the prototype
- PersonaGroup      — imported from persona_synthesis (read-only input type)
- SampledAgent      — a concrete individual walker sampled from a PersonaGroup
- AgentDecision     — the structured output of one agent turn
- AgentPath         — the history + terminal state of one walker
- SimulationReport  — the narrative + categorized findings
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, conlist, model_validator

# Reuse the upstream PersonaGroup and UploadedFile types — never redefine.
from persona_synthesis.schema import PersonaGroup, UploadedFile  # noqa: F401


# ──────────────────────────── Screen graph ────────────────────────────

ElementKind = Literal[
    "button", "link", "input", "checkbox", "radio",
    "toggle", "select", "tab", "card", "image", "text", "unknown",
]


class InteractiveElement(BaseModel):
    id: str                          # stable slug, e.g. "s1.btn_signup"
    kind: ElementKind
    label: str                       # copy or alt text the vision model read
    bbox_hint: Optional[str] = None  # natural-language location ("top-right")


class Screen(BaseModel):
    id: str                              # "s1", "s2"...
    source_filename: str                 # links back to the UploadedFile
    inferred_purpose: str                # one sentence
    copy: list[str] = Field(default_factory=list)
    elements: list[InteractiveElement] = Field(default_factory=list)
    duplicate_of: Optional[str] = None   # canonical screen id if this is a variant


class Transition(BaseModel):
    from_screen: str
    via_element_id: str
    to_screen: str
    confidence: int = Field(ge=1, le=5)


class UnresolvedAction(BaseModel):
    from_screen: str
    via_element_id: str
    reason: str                          # "no destination screenshot provided"


class ScreenGraph(BaseModel):
    screens: conlist(Screen, min_length=1)
    transitions: list[Transition] = Field(default_factory=list)
    unresolved: list[UnresolvedAction] = Field(default_factory=list)
    entry_screen_id: str

    @model_validator(mode="after")
    def _refs_valid(self) -> "ScreenGraph":
        ids = {s.id for s in self.screens}
        if self.entry_screen_id not in ids:
            raise ValueError(
                f"entry_screen_id {self.entry_screen_id!r} not in screens {sorted(ids)}"
            )
        for t in self.transitions:
            if t.from_screen not in ids or t.to_screen not in ids:
                raise ValueError(
                    f"transition {t.from_screen}->{t.to_screen} references unknown screen id"
                )
        for u in self.unresolved:
            if u.from_screen not in ids:
                raise ValueError(
                    f"unresolved action from {u.from_screen!r} references unknown screen id"
                )
        for s in self.screens:
            if s.duplicate_of is not None and s.duplicate_of not in ids:
                raise ValueError(
                    f"screen {s.id!r} duplicate_of={s.duplicate_of!r} references unknown screen id"
                )
        return self


# ──────────────────────────── Sampled agent ────────────────────────────

Device = Literal["mobile", "desktop", "mixed"]
LowMedHigh = Literal["low", "medium", "high"]


class SampledAgent(BaseModel):
    """A concrete individual sampled from a PersonaGroup's ranges.

    Kept intentionally denormalized: the original `group` reference is retained
    so prompts can quote its narrative without re-looking it up, while
    flattened scalars carry the sampled concrete values used for behavior.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_id: str
    parent_agent_id: Optional[str] = None
    cluster_id: str
    cluster_name: str

    # Concrete sampled values (ranges collapsed)
    age: int = Field(ge=0, le=120)
    tech_savviness: int = Field(ge=1, le=5)
    patience_threshold: LowMedHigh
    pricing_sensitivity: int = Field(ge=1, le=5)
    primary_device: Device

    group: PersonaGroup
    personalized_backstory: str
    rng_seed: int = 0


# ──────────────────────────── Per-turn decision ────────────────────────────

ActionKind = Literal["click_element", "scroll", "go_back", "give_up", "complete"]


class AlternativeAction(BaseModel):
    action: ActionKind
    target_element_id: Optional[str] = None
    reasoning: str


class EmotionalState(BaseModel):
    confusion: int = Field(ge=1, le=5)
    frustration: int = Field(ge=1, le=5)
    interest: int = Field(ge=1, le=5)
    trust: int = Field(ge=1, le=5)


class AgentDecision(BaseModel):
    action: ActionKind
    target_element_id: Optional[str] = None
    reasoning: str
    confidence: int = Field(ge=1, le=5)
    emotional_state: EmotionalState
    estimated_seconds_on_screen: int = Field(ge=0, le=600)
    observed_issues: list[str] = Field(default_factory=list)
    alternative_actions: conlist(AlternativeAction, max_length=2) = Field(default_factory=list)

    @model_validator(mode="after")
    def _click_needs_target(self) -> "AgentDecision":
        if self.action == "click_element" and not self.target_element_id:
            raise ValueError("click_element requires target_element_id")
        return self


# ──────────────────────────── History / paths ────────────────────────────

TerminalState = Literal[
    "complete", "give_up", "dead_end", "max_steps_reached", "budget_stopped"
]


class AgentStep(BaseModel):
    order: int
    screen_id: str
    decision: AgentDecision
    was_fork_point: bool = False
    elapsed_seconds_total: int = 0


class AgentPath(BaseModel):
    agent: SampledAgent
    steps: list[AgentStep] = Field(default_factory=list)
    terminal_state: TerminalState
    screens_visited: list[str] = Field(default_factory=list)
    fork_points: list[int] = Field(default_factory=list)
    cumulative_seconds: int = 0
    tokens_used: int = 0


# ──────────────────────────── Metrics ────────────────────────────

class ActionDistribution(BaseModel):
    click_element: int = 0
    scroll: int = 0
    go_back: int = 0
    give_up: int = 0
    complete: int = 0


class ScreenMetrics(BaseModel):
    screen_id: str
    arrivals: int = 0
    departures: dict[str, int] = Field(default_factory=dict)  # keys: "continued" | TerminalState
    avg_emotional_state_on_arrival: EmotionalState
    avg_seconds: float = 0.0
    action_distribution: ActionDistribution = Field(default_factory=ActionDistribution)
    issues: list[str] = Field(default_factory=list)


class DropOffPoint(BaseModel):
    step_index: int = Field(ge=0)
    remaining_pct: float = Field(ge=0.0, le=100.0)


class GlobalMetrics(BaseModel):
    total_agents: int = 0
    completion_rate_overall: float = Field(ge=0.0, le=1.0, default=0.0)
    completion_rate_by_cluster: dict[str, float] = Field(default_factory=dict)
    drop_off_curve: list[DropOffPoint] = Field(default_factory=list)
    tokens_used_total: int = 0
    top_friction_screens: list[str] = Field(default_factory=list)
    per_screen: list[ScreenMetrics] = Field(default_factory=list)


# ──────────────────────────── Issues + report ────────────────────────────

TestCategory = Literal[
    "accessibility", "compliance", "onboarding", "activation", "engagement_retention"
]
Severity = Literal["low", "medium", "high", "critical"]


class CategorizedIssue(BaseModel):
    summary: str
    category: TestCategory
    severity: Severity
    evidence: list[str] = Field(default_factory=list)
    affected_screens: list[str] = Field(default_factory=list)


class CategorizedIssues(BaseModel):
    issues: list[CategorizedIssue] = Field(default_factory=list)


class ClusterFinding(BaseModel):
    cluster_id: str
    cluster_name: str
    summary: str
    completion_rate: float = Field(ge=0.0, le=1.0)
    key_friction: list[str] = Field(default_factory=list)


class SimulationReport(BaseModel):
    executive_summary: str
    cluster_findings: conlist(ClusterFinding, min_length=1)
    top_friction_points: list[str] = Field(default_factory=list)
    findings_by_category: dict[str, list[str]] = Field(default_factory=dict)
    recommended_next_tests: list[str] = Field(default_factory=list)
    metrics: GlobalMetrics
    categorized_issues: CategorizedIssues


# ──────────────────────────── Config + IO ────────────────────────────

class SimulationConfig(BaseModel):
    max_agents_budget: int = Field(default=150, ge=1)
    max_agents_per_cluster: int = Field(default=60, ge=1)
    max_depth: int = Field(default=25, ge=1)
    max_concurrent_llm_calls: int = Field(default=8, ge=1)
    hard_spend_cap_tokens: int = Field(default=5_000_000, ge=1)
    n_seed_per_group: int = Field(default=1, ge=1)
    history_window_k: int = Field(default=5, ge=1)
    give_up_frustration_streak: int = Field(default=2, ge=1)
    forks_per_decision: int = Field(default=2, ge=0)
    rng_seed: int = 0


class ForkSpec(BaseModel):
    parent_agent_id: str
    take_alternative_index: int = Field(ge=0, le=1)


class SimulationInputs(BaseModel):
    groups: conlist(PersonaGroup, min_length=3, max_length=3)
    screenshots: list[UploadedFile] = Field(default_factory=list)
    goal: Optional[str] = None
    screen_graph_override: Optional[ScreenGraph] = None


class SimulationResult(BaseModel):
    screen_graph: ScreenGraph
    paths: list[AgentPath] = Field(default_factory=list)
    report: SimulationReport
    budget_stopped: bool = False
    budgets_engaged: list[str] = Field(default_factory=list)
