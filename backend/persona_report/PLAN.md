# Persona Report Module — Design Plan

## Context

Ascala has two working backend modules: `persona_synthesis/` produces 3
`PersonaGroup`s, and `persona_simulation/` turns those groups + screenshots
into a `SimulationResult` (per-agent `AgentPath`s, aggregated `GlobalMetrics`,
and `CategorizedIssues`). This new module — `persona_report/` — is the final
stage: it consumes a `SimulationResult` and produces a **structured, per-test-type
Report** that a frontend can render as six distinct views.

**Scope of THIS phase:** design only. Output is this document. Implementation
happens after approval.

**Consumer contract:** the output is DATA, not rendered HTML. The frontend
owns rendering. Every `PersonaDistribution` ships as raw dot data + axis
definitions; the frontend picks a chart library and draws.

**One honest constraint locked in:** Retention cannot be directly measured
from a single screenshot-based simulation. The Retention section reports
*retention-likelihood signals* only, each explicitly flagged as predictive.
Empty Retention is a valid output.

**Infrastructure to reuse:**
- `persona_synthesis/llm/base.py` — `LLMProvider` Protocol. Same swap seam.
- `persona_synthesis/llm/anthropic_client.py` — Claude via tool-use.
- `persona_simulation/_llm_helpers.py` — pattern: load prompt, tool-use,
  validate, retry once. Clone into `persona_report/_llm_helpers.py` (can't
  cross-import a "private" module, but the pattern is trivial).
- `tests/conftest.py` `DummyProvider` + `make_dummy` pattern — clone again
  into `persona_report/tests/conftest.py`.

**Upstream types consumed (read-only):**
`SimulationResult`, `AgentPath`, `AgentStep`, `AgentDecision`, `EmotionalState`,
`SampledAgent`, `GlobalMetrics`, `ScreenMetrics`, `CategorizedIssues`,
`CategorizedIssue`, `ScreenGraph`, `Screen`, `PersonaGroup` (via SampledAgent).

---

## 1. Module structure

```
/Users/ob/ascala/backend/persona_report/
  __init__.py                # re-export public types + generate_report()
  PLAN.md                    # this document
  schema.py                  # all pydantic models (§2)
  errors.py                  # ReportError, FixPromptFormatError
  filters.py                 # pure — per test_type: predicate over CategorizedIssues + agent filter
  stats.py                   # pure — per test_type: compute 3 key stats from filtered data
  distributions.py           # pure — one builder per chart_type; returns PersonaDistribution
  severity.py                # pure — deterministic fix severity truth table
  summaries.py               # 1 LLM call per test_type (short_summary)
  fixes.py                   # 1 LLM call per candidate fix; structural validation of fix_prompt
  exec_summary.py            # 1 optional LLM call for top-level exec summary
  generator.py               # public generate_report() — orchestrator
  run.py                     # `python -m persona_report.run` CLI
  _llm_helpers.py            # clone of persona_simulation/_llm_helpers.py
  prompts/
    test_type_summary.md     # one templated prompt, called 6× with test_type as context
    draft_fix.md             # fix-drafting prompt with good/bad examples
    exec_summary.md          # top-level cross-test-type summary
  tests/
    __init__.py
    conftest.py              # DummyProvider + fixtures + sample_simulation_result
    fixtures/
      sample_simulation_result.json   # full SimulationResult output, 9 agents, 2 clusters
      mock_test_type_summary.json
      mock_fix.json
      mock_fix_bad_format.json         # missing "Change required:" — triggers retry
      mock_exec_summary.json
    test_filters.py
    test_distributions.py
    test_severity.py
    test_fix_prompt_format.py
    test_report.py
    test_live.py
```

---

## 2. Full typed schema (`persona_report/schema.py`)

Style: pydantic v2, same as `persona_simulation/schema.py`.

```python
from typing import Any, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, conlist, model_validator

TestType = Literal[
    "accessibility", "compliance", "onboarding",
    "activation", "engagement", "retention",
]
Sentiment   = Literal["positive", "negative", "neutral"]
Severity    = Literal["urgent", "important", "medium"]
Confidence  = Literal["high", "medium", "low"]
ChartType   = Literal[
    "scatter", "dot_grid", "beeswarm",
    "grouped_dot_plot", "funnel_dot_flow",
    "dot_plot", "parallel_coordinates",
    "dot_distribution", "grouped_dot_count",
]
Scope = Literal["per_cluster", "all_clusters"]


class Stat(BaseModel):
    value: str                   # always rendered as string ("42%", "3.2s", "18/60", "s3")
    label: str
    context: Optional[str] = None   # "up from 12% in the last run"; null if first run
    sentiment: Sentiment


class AxisDef(BaseModel):
    label: str
    unit: Optional[str] = None       # "%", "s", "screens"
    min: Optional[float] = None
    max: Optional[float] = None
    categorical: Optional[list[str]] = None   # set when axis is ordinal groups


class Dot(BaseModel):
    agent_id: str
    cluster_id: str
    x: float | str
    y: Optional[float | str] = None
    meta: dict[str, Any] = Field(default_factory=dict)   # freeform per-dot context


class DotAnnotation(BaseModel):
    type: Literal["threshold", "group_label", "note", "empty_state"]
    text: str
    position: Optional[dict[str, Any]] = None   # chart-type-specific


class PersonaDistribution(BaseModel):
    id: str                     # e.g. "a11y-scatter"; unique within a TestTypeReport
    title: str
    description: str            # 1 sentence
    chart_type: ChartType
    scope: Scope
    axes: dict[str, AxisDef]    # {"x": ..., "y": ...}; y is omitted for 1D charts
    dots: list[Dot]
    annotations: list[DotAnnotation] = Field(default_factory=list)


class FixEvidence(BaseModel):
    affected_clusters: list[str]
    affected_screens: list[str]
    agent_count: int = Field(ge=0)
    representative_quotes: conlist(str, min_length=0, max_length=3)


class Fix(BaseModel):
    severity: Severity
    title: str                      # imperative, short
    summary: str                    # 2–3 sentences
    evidence: FixEvidence
    fix_prompt: str                 # paste-into-vibe-coding tool; format enforced
    estimated_impact: str           # "Would reduce pricing drop-off by ~30%"
    related_issue_ids: list[str] = Field(default_factory=list)


class TestTypeReport(BaseModel):
    test_type: TestType
    short_summary: str              # 2–4 sentences, plain English
    key_stats: conlist(Stat, min_length=3, max_length=3)
    persona_distributions: conlist(PersonaDistribution, min_length=1, max_length=3)
    recommended_fixes: list[Fix] = Field(default_factory=list)
    data_confidence: Confidence
    # For retention: carries a prominent predictive-only note inside short_summary


class ReportMeta(BaseModel):
    simulation_run_id: Optional[str] = None
    generated_at: datetime
    total_llm_calls: int = 0
    tokens_used_total: int = 0
    budgets_engaged: list[str] = Field(default_factory=list)
    schema_version: Literal["1.0"] = "1.0"


class Report(BaseModel):
    test_type_reports: conlist(TestTypeReport, min_length=6, max_length=6)
    executive_summary: Optional[str] = None   # only if caller opted in
    meta: ReportMeta
```

---

## 3. Data flow

```
SimulationResult
    │
    ▼
filters.select_for(test_type, sim_result)
    → FilteredSlice { relevant_issues, relevant_paths, relevant_screens,
                      cluster_counts, touchpoint_count }
    │
    ▼  (per test type, independently — no cross-test-type coupling)
    │
    ├─▶ stats.compute(slice, test_type)            → [Stat, Stat, Stat]
    │
    ├─▶ distributions.build(slice, test_type)      → [PersonaDistribution, ...]
    │
    ├─▶ severity.classify_candidates(slice, issues) → list[(CategorizedIssue, Severity)]
    │
    ├─▶ summaries.generate(slice, stats, test_type, provider)
    │                                               → short_summary (1 LLM call)
    │
    └─▶ fixes.draft_for_each(classified, slice, provider)
                                                    → [Fix, ...] (1 LLM call per candidate;
                                                       severity is deterministic, NOT LLM)
    │
    ▼
assemble TestTypeReport × 6
    │
    ▼
data_confidence = touchpoint_count_based(test_type)
    │
    ▼
optional: exec_summary.generate(test_type_reports, provider)  (1 LLM call, gated on flag)
    │
    ▼
Report { test_type_reports, executive_summary, meta }
```

---

## 4. Per-test-type design

Each test type locks in:
- **filter predicate** — which `CategorizedIssue`s and `AgentPath`s are relevant
- **3 key stats** — computed deterministically
- **2–3 distributions** — raw dot data, pure code (no LLM)

### 4.1 Accessibility

**Filter predicate** (`filters.select_accessibility`):
- Issues: `CategorizedIssue.category == "accessibility"`
- Agent signals: any agent whose `sampled.group.testing_postures.accessibility`
  has `vision != "full"` OR `motor != "full"` OR `hearing != "full"` OR
  `screen_reader_likelihood >= 30`, OR who observed an a11y-keyword string
  in `AgentDecision.observed_issues` (keywords: `focus`, `contrast`, `screen reader`,
  `keyboard`, `alt text`, `a11y`, `accessibility`).
- Screens: every screen referenced in the above issues' `affected_screens`.

**Touchpoint count** = `len(relevant_paths) × avg(len(path.steps))` for paths
that pass the a11y filter.

**Key stats**:

| # | value | label | sentiment |
|---|---|---|---|
| 1 | `f"{pct(a11y_flaggers)}%"` where `a11y_flaggers` = agents with ≥1 a11y issue | "agents who flagged an accessibility issue" | negative if >15%, else neutral |
| 2 | `screen_id_with_most_a11y_issues` | "most-flagged screen" | negative if flag count ≥ 3, else neutral |
| 3 | `f"{n_affected_clusters}/{total_clusters}"` | "clusters affected" | negative if ≥ half, else neutral |

**Distributions** (pick all 3 from the brief — they're each different signal shapes):

1. `scatter`, scope=`all_clusters`
    - axes: `x` = "accessibility need level" (0–5), `y` = "friction score" (0–10)
    - derivation: `a11y_need = 0 + (vision!="full") + (motor!="full") + (hearing!="full") + round(screen_reader_likelihood/25)`; `friction = avg(confusion + frustration) across all steps` scaled to 0–10
    - dots: one per agent, `meta` includes `terminal_state`

2. `dot_grid`, scope=`per_cluster`
    - axes: `x` = "screen", `y` = "agent"
    - dots: one per (screen, agent) pair; `meta.severity` = {`none`, `low`, `medium`, `high`, `critical`} from matching a11y issue severity
    - annotations: "empty_state" note per cluster with no agents

3. `beeswarm`, scope=`all_clusters`
    - axes: `x` = "n_a11y_issues_flagged_by_agent" (0–10+), grouped by cluster_id along y
    - dots: one per agent

**data_confidence**: based on relevant-agent-touchpoint count per §5.

### 4.2 Compliance

**Filter predicate** (`filters.select_compliance`):
- Issues: `category == "compliance"`
- Agent signals: `sampled.group.testing_postures.compliance.regulations` excluding `["none"]`
  OR `sampled.group.testing_postures.compliance.data_sensitivity in {"medium","high"}`
  OR `sampled.group.testing_postures.compliance.enterprise_procurement == True`
- Screens: heuristic — screens whose `inferred_purpose` matches any of
  `privacy`, `consent`, `cookie`, `terms`, `data`, `payment`, `signup`, `account`.

**Key stats**:

| # | value | label | sentiment |
|---|---|---|---|
| 1 | `f"{pct(flaggers)}%"` agents flagging a compliance issue | "agents who flagged a compliance concern" | negative if >10%, else neutral |
| 2 | `n_high_exposure_bailed` (regulations≠["none"] AND terminal∈{give_up, dead_end}) | "high-exposure agents who bailed" | negative if ≥1, else positive |
| 3 | `f"{n_touchpoints_w_drops}/{n_compliance_touchpoints}"` | "compliance touchpoints with drop-off" | negative if any, else positive |

**Distributions** (2 of 2 from the brief):

1. `grouped_dot_plot`, scope=`all_clusters`
    - axes: `x` = categorical `["GDPR","CCPA","HIPAA","SOC2","PCI","none"]`
    - dots: one per agent; `meta.flagged_compliance_issue: bool`
    - groups computed from `sampled.group.testing_postures.compliance.regulations`

2. `funnel_dot_flow`, scope=`all_clusters`
    - axes: `x` = categorical compliance touchpoint screens (auto-detected by purpose match)
    - dots: one per agent per touchpoint they reached; `y` position = row (proceeded/bailed)
    - annotations: `threshold` line marking expected conversion between touchpoints

### 4.3 Onboarding

**Filter predicate** (`filters.select_onboarding`):
- Issues: `category == "onboarding"`
- Agent signals: every agent's first `min(5, len(path.steps))` steps (onboarding
  window). Adjustable constant.
- Screens: screens visited within that window AND any screen whose purpose
  matches `signup`, `welcome`, `verify`, `workspace`, `invite`, `setup`, `onboard`.

**Key stats**:

| # | value | label | sentiment |
|---|---|---|---|
| 1 | `f"{pct(completed_onboarding)}%"` — pct reaching any `terminal=="complete"` within window | "completed onboarding window" | positive if >60%, neutral 30–60%, negative <30% |
| 2 | `median_seconds_to_first_value` — median cumulative `estimated_seconds_on_screen` before reaching a "core" screen (purpose matches `dashboard`, `home`, `workspace`, `feed`) | "median time to first value" | negative if >300s, neutral 90–300s, positive <90s |
| 3 | `biggest_drop_off_step_index` (index where drop-off % is maximum across the onboarding window) | "biggest drop-off step" | negative if the max drop >30%, else neutral |

**Distributions** (3 from the brief):

1. `funnel_dot_flow`, scope=`per_cluster`
    - axes: `x` = categorical onboarding step indices (`step_1`..`step_N`)
    - dots: one per agent per reached step; `y` position = row (proceeded / dropped)

2. `scatter`, scope=`all_clusters`
    - axes: `x` = "tech_savviness" (1–5), `y` = "time_to_first_value" (seconds, clamped at 600)
    - dots: one per agent; `meta.terminal_state`

3. `beeswarm`, scope=`per_cluster`
    - axes: `x` = "onboarding completion score" (0–100 = visited_screens_in_window / len(onboarding_window_screens) × 100)
    - dots: one per agent

### 4.4 Activation

**Filter predicate** (`filters.select_activation`):
- Issues: `category == "activation"`
- Agent signals: all agents (activation rate is a property of the whole
  sample, not a subset).
- Screens: any screen whose `inferred_purpose` matches `dashboard`, `home`,
  `main`, `core`, `workspace`, `feed`, `results`.

**Key stats**:

| # | value | label | sentiment |
|---|---|---|---|
| 1 | `f"{pct(activated)}%"` activated = `terminal=="complete"` OR reached ≥1 core screen | "activation rate" | positive if >60%, neutral 30–60%, negative <30% |
| 2 | `median_time_to_aha_seconds` — across activated agents, cumulative seconds at the first core-screen visit | "median time to aha moment" | negative if >240s, neutral 60–240s, positive <60s |
| 3 | `pct(motivated_but_bounced)` — cluster-level motivation_level=="high" AND terminal∈{give_up, dead_end} | "high-motivation agents who bounced" | negative if >10%, else neutral |

**Distributions** (2 from the brief):

1. `dot_plot`, scope=`all_clusters`
    - axes: `x` = "motivation level" (low/medium/high — from cluster-level activation posture)
    - dots: one per agent; `meta.activation_outcome` in `{activated, partial, bounced}` where `partial` = reached ≥1 core screen but did not `complete`
    - colored by outcome in the frontend

2. `parallel_coordinates`, scope=`per_cluster`
    - axes: dict with 4 keys `reached_aha`, `used_core_feature`, `configured_setting`, `invited_teammate` — each ordinal 0/1
    - dots: one per agent (but rendered as a line by the frontend); `meta` carries the 4 values
    - Detection (heuristic string match on screen purpose + step decision labels):
      - `reached_aha` = terminal=="complete" OR visited a core screen
      - `used_core_feature` = visited a core screen for >1 step
      - `configured_setting` = any click with label matching `settings|profile|preferences|config`
      - `invited_teammate` = any click with label matching `invite|add.*member|team`

### 4.5 Engagement

**Filter predicate** (`filters.select_engagement`):
- Issues: `category == "engagement_retention"` AND issue `summary` mentions
  engagement keywords (`return`, `come back` are retention; exclude those)
- Agent signals: all agents whose path length ≥ 3 steps
- Screens: all screens visited by ≥1 relevant agent

**Key stats**:

| # | value | label | sentiment |
|---|---|---|---|
| 1 | `f"{avg_unique_screens_per_agent:.1f}"` | "average unique screens visited" | positive if >60% of screens, else neutral |
| 2 | `f"{avg_interest_score:.1f}/5"` — mean `interest` across all decisions | "average interest score" | positive if ≥4, neutral 3–4, negative <3 |
| 3 | `f"{pct(deep_explorers)}%"` — agents visiting ≥50% of screens | "deep explorers" | positive if >40%, else neutral |

**Distributions** (2 from the brief):

1. `beeswarm`, scope=`per_cluster`
    - axes: `x` = "unique screens visited" (int)
    - dots: one per agent

2. `scatter`, scope=`all_clusters`
    - axes: `x` = "session depth" (len(steps)), `y` = "avg interest score" (1–5)
    - dots: one per agent; colored by cluster

### 4.6 Retention (signals only — flagged predictive)

**Filter predicate** (`filters.select_retention`):
- Issues: `category == "engagement_retention"` AND summary mentions `return`, `come back`, `churn`
- Agent signals: every agent's `AgentDecision.reasoning` text scanned for return-intent keywords
- Screens: any screen where a habit marker was clicked (labels matching
  `save`, `bookmark`, `subscribe`, `notify|alerts|updates`, `download`, `follow`,
  `watch list`, `favorite`)

**Return-likelihood scoring** (deterministic, regex-based, scored 0–5):
- 5: reasoning contains `definitely`, `can't wait`, `bookmarking`, `adding to`
- 4: `will come back`, `looking forward`, `plan to`
- 3: `might`, `maybe`, `could see myself`
- 2: `unlikely`, `probably not`
- 1: `won't`, `never`, `done with this`, `moving on`
- 0: no return-related reasoning detected

Each agent gets ONE score: the max across all their step reasonings.

**Key stats**:

| # | value | label | sentiment |
|---|---|---|---|
| 1 | `f"{pct(agents_with_signal)}%"` — `return_likelihood > 0` | "agents with return-intent signal" | positive if >50%, neutral 20–50%, negative <20% |
| 2 | `n_habit_markers_touched` — total clicks on habit-marker-labeled elements | "habit-marker clicks" | positive if >0, else neutral |
| 3 | `f"{pct(switching_cost_mentions)}%"` — agents whose reasoning mentions `migrate|switch|move from|current tool|already using` | "switching-cost mentions" | neutral (higher = more friction, lower = weaker signal; context-dependent) |

**Distributions** (2 from the brief):

1. `dot_distribution`, scope=`per_cluster`
    - axes: `x` = "expressed return likelihood" (0–5)
    - dots: one per agent
    - annotations: `note` = "predictive signal, not measured retention"

2. `grouped_dot_count`, scope=`all_clusters`
    - axes: `x` = categorical `["habit_marker_touched", "switching_cost_expressed", "neither"]`
    - dots: one per agent; group determined deterministically
    - annotations: same predictive-only note

**Short_summary must prominently include a predictive-only disclaimer.**
The prompt explicitly instructs the LLM to say so. If the simulation
produced zero retention signals, short_summary says that plainly and
`recommended_fixes` is empty — no fabrication.

---

## 5. `data_confidence` rule (per test type)

Computed from **touchpoint count** = relevant agent touches (see each
filter's definition):

- `high`   — touchpoints ≥ 30
- `medium` — 10 ≤ touchpoints < 30
- `low`    — touchpoints < 10

For Retention specifically: the threshold is on number of agents with a
non-zero `return_likelihood` score (not total agent touchpoints), so it
often lands in `low` or `medium`. That is expected and correct.

---

## 6. Deterministic severity truth table (`severity.py`)

Applied to each candidate fix in the listed order; first match wins.

| # | Condition | Severity |
|---|---|---|
| 1 | `category == "compliance"` AND exists agent with `testing_postures.compliance.regulations != ["none"]` who has `terminal_state in {give_up, dead_end}` at any `affected_screen` | **urgent** |
| 2 | `category == "accessibility"` AND the matching `CategorizedIssue.severity == "critical"` | **urgent** |
| 3 | In any affected cluster, `pct(cluster_agents_with_terminal in {give_up, dead_end} at affected_screens) > 20%` | **urgent** |
| 4 | In any single cluster, `pct(agents_with avg(confusion+frustration) ≥ 4 at affected_screens) > 50%` | **important** |
| 5 | `pct(all_agents_with observed_issues overlapping this_issue.evidence) ≥ 30%` | **important** |
| 6 | default | **medium** |

Every rule evaluates directly against the `SimulationResult` — no LLM.
Unit tests in §8 cover every branch.

Candidate fixes originate from `CategorizedIssues.issues` (one candidate
per issue), deduped by issue summary. Cap at 16 candidates per test type
before severity classification to contain LLM call count
(urgent priority wins slots, then important, then medium — aligned with
the brief's 4/6/6 quota).

---

## 7. Fix prompt format (`fixes.py`)

### Required template

Every `fix_prompt` generated MUST contain, in order:

1. `On the <SCREEN_ID> screen (<SCREEN_FILENAME>), <CONCRETE_PROBLEM_STATEMENT>.`
2. `Evidence: <N>/<TOTAL> agents in the <CLUSTER_NAME> cluster <CONCRETE_STAT>.`
3. `Change required: <IMPERATIVE_VERB> <SPECIFIC_UI_ELEMENT> <DIRECTION>.`
4. `Visual/interaction direction: <PIXEL_OR_COPY_OR_BEHAVIOR_DETAIL>.`

### Structural check (`test_fix_prompt_format.py` + runtime validation)

A generated fix_prompt passes iff regex (case-insensitive, multiline):
- `(?i)^on the [a-z0-9_]+ screen \(` — section 1 intro
- `(?i)evidence:\s*\d+\s*/\s*\d+\s+agents` — section 2 with real numbers
- `(?i)change required:\s*(add|remove|replace|enlarge|move|rename|reorder|demote|promote|collapse|expand|surface|hide|fix|gate|debounce|validate|disable|enable)\b` — imperative verb
- `(?i)visual/interaction direction:\s*\S+` — section 4 non-empty

On format failure: retry once with a stricter follow-up prompt that includes
the regex and the failing output. Second failure → `FixPromptFormatError`
(non-fatal: the Fix is dropped from the report, logged into meta warnings).

### Worked examples (ship with the `draft_fix.md` prompt)

**URGENT**

```
On the s3 screen (checkout-step-2.png), the Continue button does not
advance the flow — 9 of 12 agents in the Price-sensitive founder cluster
abandoned here after clicking with no visible response.

Evidence: 9/12 agents in the Price-sensitive founder cluster had
terminal_state=give_up on this screen; reasoning traces cite "nothing
happened" and "dead button."

Change required: Add loading state + error handling to the Continue button.
If the backend call fails, surface an inline error; if it succeeds, advance
to step 3 of the checkout.

Visual/interaction direction: Button enters disabled state with a spinner
on click; errors appear in red below the button, not in a modal.
```

**IMPORTANT**

```
On the s1 screen (landing.png), the primary and secondary CTAs compete for
attention — 8 of 15 agents in the Curious newcomer cluster paused for 20+
seconds before choosing between them.

Evidence: 8/15 agents in the Curious newcomer cluster had confusion ≥ 4
on this screen; 3 agents chose Log in first and later bounced.

Change required: Demote the Log in link so Sign up is unambiguously primary.

Visual/interaction direction: Move Log in to the top-right header as plain
text; enlarge Sign up and center it below the hero copy.
```

**MEDIUM**

```
On the s4 screen (dashboard.png), the template gallery is buried behind a
small card — 4 of 60 agents discovered it within their first 2 minutes.

Evidence: 4/60 agents across all clusters visited the gallery within the
onboarding window; 3 of them mentioned "found it by accident" in their
reasoning.

Change required: Promote the template gallery to a persistent left-rail
entry and surface it in the dashboard empty state.

Visual/interaction direction: Card should include a thumbnail preview and
a "Start from a template" CTA; gallery link remains in the nav even after
first use.
```

All three examples pass the regex check above.

---

## 8. Test plan

All tests use a cloned `DummyProvider` + `make_dummy` fixture. A full
`SimulationResult` fixture (`sample_simulation_result.json`) holds 9 agents
(3 per cluster, 3 clusters) walking through a 4-screen prototype. Different
tests compose filtered views of that single fixture to cover cases.

**`test_filters.py`** (6 tests — one per test type)
- Each verifies the filter predicate selects the expected issues + agent
  subset from `sample_simulation_result.json`. Assertions check exact
  `issue_id` list + exact `agent_id` list.

**`test_distributions.py`** (9 tests — one per chart_type + 2 edge cases)
- scatter: axes defined, every dot has x and y, dot count = relevant agents
- dot_grid: rows × columns matches (screens × agents in cluster)
- beeswarm: 1D axes (only x present)
- grouped_dot_plot: x is categorical; dots distributed across groups
- funnel_dot_flow: dots for each touchpoint; proceed/bail y-row reflected
- dot_plot: dots sorted by x axis correctly
- parallel_coordinates: 4 axes defined; every dot has all 4 meta values
- dot_distribution: 1D; x values within 0–5
- grouped_dot_count: dots across 3 categorical groups
- empty-cluster handling: per_cluster dists with zero agents in a cluster
  emit `empty_state` annotation (see §10(b))
- empty-distribution handling: zero relevant agents overall → `dots=[]` +
  `empty_state` annotation (see §10(a))

**`test_severity.py`** (7 tests — full truth table coverage)
- compliance + regulatory-exposure + bailed → urgent
- accessibility + simulation-severity=critical → urgent
- cluster drop-off > 20% → urgent
- majority-cluster confusion+frustration ≥ 4 → important
- ≥ 30% all-agent overlap → important
- none of above → medium
- rule precedence: a scenario matching both rule 3 AND rule 4 returns urgent (earlier wins)

**`test_fix_prompt_format.py`** (4 tests)
- Valid fix_prompt passes regex
- Missing "Change required:" → retry triggered
- Missing evidence numbers → retry triggered
- Second failure → `FixPromptFormatError` logged, Fix dropped, meta warning recorded

**`test_report.py`** (6 tests — end-to-end with mock LLM)
- Full 6 test-type output → schema validates
- Retention with no signals → empty fixes + predictive disclaimer in short_summary
- Compliance with no exposure → data_confidence="low"
- `generate_report(..., include_executive_summary=True)` → exec_summary present
- `generate_report(..., include_executive_summary=False)` → exec_summary None
- Fix severity matches the deterministic truth table on fixture data

**`test_live.py`** — `@pytest.mark.live`, skipped by default. One real
Claude run on the minimal simulation fixture; costs ~$0.10.

---

## 9. CLI (`run.py`)

```
python -m persona_report.run \
    --simulation path/to/sim.json \
    --output path/to/report.json \
    [--exec-summary] [--mock] [--mock-fixtures DIR]
```

Flags:
- `--simulation` (required): JSON file of a `SimulationResult`
- `--output` (default stdout): where to write the `Report` JSON
- `--exec-summary` (default off): include the optional cross-test-type
  exec summary call
- `--mock`: use bundled fixture responses, no network
- `--mock-fixtures DIR`: override fixture dir (default `persona_report/tests/fixtures`)

Exits: 0 on success; 2 on input-loading error; 3 on schema-validation
error; 4 on provider error.

---

## 10. Open questions — concrete answers

**(a) Empty distributions (zero relevant agents overall).**
Emit the `PersonaDistribution` with `dots=[]` plus an `annotations` entry:
```json
{ "type": "empty_state", "text": "No agents matched this distribution — see short_summary for context." }
```
Don't omit the distribution. Reason: frontend layout is pinned to
`len(persona_distributions)` per test type; omitting creates layout shift.
Empty-state annotations are a frontend render-as-placeholder signal.

**(b) Per-cluster distributions with one cluster empty.**
Render the cluster's distribution frame with `dots=[]` and an
`empty_state` annotation on THAT cluster only. Other clusters render
normally. Don't omit — per_cluster layouts are usually side-by-side and
a missing cluster breaks the visual comparison.

**(c) Executive summary call location.**
**Inside this module, opt-in via `generate_report(include_executive_summary=True)`.**
Reasons:
- It needs access to the finished `TestTypeReport`s; forcing the caller
  to marshal that across a module boundary is clunky.
- The prompt lives alongside the other prompts (`prompts/exec_summary.md`).
- Opt-in preserves cost control — some callers won't want the extra call.

**(d) Fix prompt caching.**
**In-memory only, keyed on `(test_type, issue_id, issue_summary_hash)`**,
scoped to a single `generate_report()` call. Re-runs across different
processes don't share cache. Disk persistence (Redis / sqlite) is a
future optimization if Ascala builds a long-running report service.
Rationale: the cost of re-drafting ~20–80 fix prompts per run is
bounded, and avoiding process-level caching keeps deployment simple.

---

## 11. Verification (once implemented)

- `pytest persona_report/tests/` — all offline, no API key needed.
- `python -m persona_report.run --simulation persona_report/tests/fixtures/sample_simulation_result.json --output /tmp/report.json --mock` — end-to-end offline; writes a valid `Report` JSON; the 6 `TestTypeReport`s each have 3 stats + 2–3 distributions; retention explicitly flagged predictive.
- `pytest -m live` — one real Claude call on the minimal fixture.
- Schema round-trip: `Report.model_validate_json(json.dumps(result.model_dump()))` must not raise.

---

## 12. Deliberate non-goals (for this phase)

- No FastAPI endpoint wiring. The module is consumed programmatically
  and via CLI. `app.py` addition is a follow-up task.
- No frontend integration (frontend is a consumer and a separate effort).
- No persisted run database — fix prompt cache is in-memory per run.
- No multi-simulation aggregation ("compare this run to the last run").
  The `Stat.context` field makes room for it in the schema (e.g., "up
  from 12% in the last run"), but the comparison source is caller-provided
  in this phase; we just pass it through.
- No internationalization of summaries — English only for now.

---

## 13. Cost estimate

Per `generate_report()` call (model: claude-sonnet-4-6, tool-use):

| Call type | Count | ~input tok | ~output tok | subtotal |
|---|---:|---:|---:|---:|
| test_type_summary | 6 | 2,500 | 400 | ~17,400 |
| draft_fix | 20 (typical; bounded at 36/tt × 6 = 216 worst case) | 1,800 | 500 | ~46,000 |
| exec_summary (optional) | 0 or 1 | 4,000 | 800 | 0 or ~4,800 |
| **Typical total** | | | | **~63–68k tokens** |
| **Worst-case total** | | | | **~520k tokens** |

Significantly cheaper than simulation. No hard cap needed; the caller's
Anthropic-side rate limits are the natural ceiling.
