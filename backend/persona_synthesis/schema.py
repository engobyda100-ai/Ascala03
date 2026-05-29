"""Pydantic models for the persona synthesis pipeline.

Public types:
- SynthesisInputs  — what the caller hands to synthesize_personas
- SynthesisResult  — what the caller gets back
- PersonaGroup     — one behavioral cluster (3 per bundle)
- PersonaBundle    — the validated set of 3 groups with share-sum invariant
- ContextSummary   — normalized representation of the inputs (traceability)
"""
from __future__ import annotations

from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, conlist, model_validator


# ──────────────────────────── Inputs ────────────────────────────

class UploadedFile(BaseModel):
    """Raw file handed to the pipeline. `data` holds bytes."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    mime: str = "application/octet-stream"
    data: bytes


class ChatMessage(BaseModel):
    role: Literal["user", "bot", "assistant", "system"]
    text: str


class SynthesisInputs(BaseModel):
    files: list[UploadedFile] = Field(default_factory=list)
    chat_messages: list[ChatMessage] = Field(default_factory=list)
    product_url: Optional[str] = None


# ──────────────────────────── Context Summary ────────────────────────────

class ResearchRef(BaseModel):
    name: str
    kind: Literal["pdf", "csv", "text", "image", "video_skipped", "url"]
    extracted_excerpt: Optional[str] = None
    note: Optional[str] = None


PricingModel = Literal["free", "freemium", "subscription", "one_time", "enterprise", "unknown"]
ComplexityLevel = Literal["simple", "moderate", "complex"]


class ContextSummary(BaseModel):
    app_category: str
    stated_audience: Optional[str] = None
    pricing_model: PricingModel
    apparent_complexity: ComplexityLevel
    geography_signals: list[str] = Field(default_factory=list)
    industry_signals: list[str] = Field(default_factory=list)
    uploaded_research: list[ResearchRef] = Field(default_factory=list)
    raw_notes: str = ""


# ──────────────────────────── PersonaGroup sub-schemas ────────────────────────────

RoleSeniority = Literal["junior", "mid", "senior", "lead", "exec", "founder", "n/a"]
CompanySize = Literal["solo", "2-10", "11-50", "51-200", "201-1000", "1000+", "n/a"]
Device = Literal["mobile", "desktop", "mixed"]


class Demographics(BaseModel):
    age_range: str
    education_level: str
    occupation: str
    role_seniority: RoleSeniority
    company_size: CompanySize
    industry: Optional[str] = None
    geography: list[str]
    primary_device: Device
    language: str


LowMedHigh = Literal["low", "medium", "high"]


class Cognitive(BaseModel):
    tech_savviness: int = Field(ge=1, le=5)
    patience_threshold: LowMedHigh
    risk_tolerance: LowMedHigh
    decision_style: Literal["analytical", "intuitive", "mixed"]
    learning_style: Literal["docs", "tinker", "video", "mixed"]
    prior_saas_experience: Literal["none", "light", "moderate", "heavy"]


class Economic(BaseModel):
    pricing_sensitivity: int = Field(ge=1, le=5)
    budget_authority: Literal["self_serve", "team_approval", "procurement"]
    trial_vs_roi: Literal["trial_first", "needs_roi_upfront", "mixed"]


class AccessibilityPosture(BaseModel):
    assistive_tech: list[str] = Field(default_factory=list)
    vision: Literal["full", "low", "blind", "n/a"]
    motor: Literal["full", "limited", "n/a"]
    hearing: Literal["full", "hoh", "deaf", "n/a"]
    screen_reader_likelihood: int = Field(ge=0, le=100)
    dexterity_factors: Optional[str] = None


Regulation = Literal["GDPR", "CCPA", "HIPAA", "SOC2", "PCI", "none"]


class CompliancePosture(BaseModel):
    regulations: list[Regulation]
    data_sensitivity: LowMedHigh
    enterprise_procurement: bool


class OnboardingPosture(BaseModel):
    time_to_value_tolerance_minutes: int = Field(ge=0)
    docs_vs_support: Literal["docs", "support", "either"]
    self_serve_capability: LowMedHigh


class ActivationPosture(BaseModel):
    motivation_level: LowMedHigh
    problem_urgency: LowMedHigh
    aha_shape: str


class EngagementRetentionPosture(BaseModel):
    expected_frequency: Literal["daily", "weekly", "monthly", "ad_hoc"]
    habit_formation_likelihood: LowMedHigh
    switching_cost_tolerance: LowMedHigh
    support_seeking: Literal["self", "peer", "vendor"]


class TestingPostures(BaseModel):
    accessibility: AccessibilityPosture
    compliance: CompliancePosture
    onboarding: OnboardingPosture
    activation: ActivationPosture
    engagement_retention: EngagementRetentionPosture


class Narrative(BaseModel):
    backstory: str
    goals: list[str]
    frustrations: list[str]


class PersonaGroup(BaseModel):
    id: str
    name: str
    estimated_share_pct: float = Field(ge=0, le=100)
    demographics: Demographics
    cognitive: Cognitive
    economic: Economic
    testing_postures: TestingPostures
    narrative: Narrative


class PersonaBundle(BaseModel):
    groups: conlist(PersonaGroup, min_length=3, max_length=3)

    @model_validator(mode="after")
    def _shares_sum_to_100(self) -> "PersonaBundle":
        s = sum(g.estimated_share_pct for g in self.groups)
        if not 98 <= s <= 102:
            raise ValueError(
                f"estimated_share_pct across the 3 groups sums to {s:.2f}; must be ~100 (98–102)"
            )
        return self


# ──────────────────────────── Result + streaming ────────────────────────────

class SynthesisResult(BaseModel):
    groups: list[PersonaGroup]
    context_summary: ContextSummary


class StreamEvent(BaseModel):
    """Events emitted during streaming synthesis."""
    kind: Literal["summary_done", "token", "group_parsed", "done", "error"]
    data: Any = None
