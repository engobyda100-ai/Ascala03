"""Pydantic schema for the report module.

Public types:
- Report                 — top-level output
- TestTypeReport         — one of 6 sections, each renderable as its own view
- Stat, AxisDef, Dot, DotAnnotation, PersonaDistribution
- Fix, FixEvidence
- ReportMeta
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, conlist


# ──────────────────────────── Enums (Literal types) ────────────────────────────

TestType = Literal[
    "accessibility", "compliance", "onboarding",
    "activation", "engagement", "retention",
]
Sentiment = Literal["positive", "negative", "neutral"]
Severity = Literal["urgent", "important", "medium"]
Confidence = Literal["high", "medium", "low"]
ChartType = Literal[
    "scatter", "dot_grid", "beeswarm",
    "grouped_dot_plot", "funnel_dot_flow",
    "dot_plot", "parallel_coordinates",
    "dot_distribution", "grouped_dot_count",
]
Scope = Literal["per_cluster", "all_clusters"]


# ──────────────────────────── Stat / axis / dot ────────────────────────────

class Stat(BaseModel):
    value: str          # always rendered as string ("42%", "3.2s", "18/60", "s3")
    label: str
    context: Optional[str] = None      # e.g. "up from 12% in the last run"
    sentiment: Sentiment


class AxisDef(BaseModel):
    label: str
    unit: Optional[str] = None         # "%", "s", "screens"
    min: Optional[float] = None
    max: Optional[float] = None
    categorical: Optional[list[str]] = None    # set when axis is ordinal groups


class Dot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_id: str
    cluster_id: str
    x: Union[float, int, str]
    y: Optional[Union[float, int, str]] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class DotAnnotation(BaseModel):
    type: Literal["threshold", "group_label", "note", "empty_state"]
    text: str
    position: Optional[dict[str, Any]] = None   # chart-type-specific


class PersonaDistribution(BaseModel):
    id: str                # unique within a TestTypeReport
    title: str
    description: str       # 1 sentence
    chart_type: ChartType
    scope: Scope
    axes: dict[str, AxisDef]   # {"x": ...} or {"x": ..., "y": ...}
    dots: list[Dot] = Field(default_factory=list)
    annotations: list[DotAnnotation] = Field(default_factory=list)


# ──────────────────────────── Fixes ────────────────────────────

class FixEvidence(BaseModel):
    affected_clusters: list[str] = Field(default_factory=list)
    affected_screens: list[str] = Field(default_factory=list)
    agent_count: int = Field(ge=0, default=0)
    representative_quotes: conlist(str, min_length=0, max_length=3) = Field(default_factory=list)


# ──────────────────────────── Counterfactual impact ────────────────────────────

CounterfactualMethod = Literal["sibling-path", "insufficient-data"]


class CounterfactualImpact(BaseModel):
    """Predicted completion-rate lift if this fix were applied.

    Grounded in observed sibling paths (alternative actions taken at fork
    points). When sample size is too small, predicted_lift_pct is None and
    method is "insufficient-data" — never fabricate a number.
    """
    predicted_lift_pct: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    predicted_lift_range: Optional[conlist(float, min_length=2, max_length=2)] = None
    sample_size: int = Field(ge=0, default=0)
    confidence: Confidence
    affected_personas: list[str] = Field(default_factory=list)
    method: CounterfactualMethod = "insufficient-data"
    sibling_completion_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    baseline_completion_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class Fix(BaseModel):
    severity: Severity
    title: str
    summary: str
    evidence: FixEvidence
    fix_prompt: str            # paste-into-vibe-coding tool; format-validated
    estimated_impact: str
    related_issue_ids: list[str] = Field(default_factory=list)
    counterfactual_impact: Optional[CounterfactualImpact] = None


# ──────────────────────────── Emotional trajectory ────────────────────────────

Emotion = Literal["confusion", "frustration", "interest", "trust"]


class EmotionalAverage(BaseModel):
    confusion: float = Field(ge=1.0, le=5.0)
    frustration: float = Field(ge=1.0, le=5.0)
    interest: float = Field(ge=1.0, le=5.0)
    trust: float = Field(ge=1.0, le=5.0)


class TrajectoryCell(BaseModel):
    cluster_id: str
    screen_id: str
    screen_index: int = Field(ge=0)
    emotions: EmotionalAverage
    sample_size: int = Field(ge=1)


class Trajectory(BaseModel):
    """Per-(cluster, screen) emotional averages, ordered by visit sequence.

    `screens` is the canonical screen order used for X-axis layout; not all
    cells exist for every (cluster, screen) — render missing as gaps.
    """
    screens: list[str] = Field(default_factory=list)
    clusters: list[str] = Field(default_factory=list)
    cells: list[TrajectoryCell] = Field(default_factory=list)


# ──────────────────────────── What-if scenarios ────────────────────────────

ScenarioName = Literal["status_quo", "quick_win", "redesign"]


class Scenario(BaseModel):
    name: ScenarioName
    label: str
    description: str
    fixes_applied: list[str] = Field(default_factory=list)  # fix titles or related_issue_ids
    residual_issue_counts: Optional[dict[str, int]] = None
    baseline_completion_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    predicted_completion_rate_low: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    predicted_completion_rate_high: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    predicted_lift_low: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    predicted_lift_high: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    primary_benefit_cluster: Optional[str] = None
    effort_estimate: str


# ──────────────────────────── Outcome context (per test) ────────────────────────────

class OutcomeContext(BaseModel):
    test_type_metric: str           # e.g. "onboarding completion rate"
    baseline_outcome: str           # e.g. "46% complete onboarding"
    overall_completion_rate: float = Field(ge=0.0, le=1.0)
    completion_rate_by_cluster: dict[str, float] = Field(default_factory=dict)
    worst_affected_cluster: Optional[str] = None
    worst_affected_cluster_rate: Optional[float] = None
    best_performing_cluster: Optional[str] = None
    best_performing_cluster_rate: Optional[float] = None
    gap_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    business_implication: str


# ──────────────────────────── Per test-type + top-level ────────────────────────────

class TestTypeReport(BaseModel):
    test_type: TestType
    short_summary: str                                       # 2–4 sentences
    key_stats: conlist(Stat, min_length=3, max_length=3)
    persona_distributions: conlist(PersonaDistribution, min_length=1, max_length=3)
    recommended_fixes: list[Fix] = Field(default_factory=list)
    data_confidence: Confidence
    trajectory: Optional[Trajectory] = None
    scenarios: list[Scenario] = Field(default_factory=list)
    retention_signals: list[str] = Field(default_factory=list)
    outcome_context: Optional[OutcomeContext] = None


class ReportMeta(BaseModel):
    simulation_run_id: Optional[str] = None
    generated_at: datetime
    total_llm_calls: int = 0
    tokens_used_total: int = 0
    budgets_engaged: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    schema_version: Literal["1.0"] = "1.0"


class ExecutiveSummary(BaseModel):
    overall_completion_rate: float = Field(ge=0.0, le=1.0)
    completion_rate_by_cluster: dict[str, float] = Field(default_factory=dict)
    worst_affected_cluster: Optional[str] = None
    worst_affected_cluster_rate: Optional[float] = None
    best_performing_cluster: Optional[str] = None
    best_performing_cluster_rate: Optional[float] = None
    cluster_gap_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    top_blockers_across_tests: list[str] = Field(default_factory=list)
    business_summary: Optional[str] = None


class Report(BaseModel):
    test_type_reports: conlist("TestTypeReport", min_length=6, max_length=6)
    executive_summary: Optional[str] = None
    summary: Optional[ExecutiveSummary] = None
    meta: ReportMeta
